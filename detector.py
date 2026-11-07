import logging
import threading
import time
from datetime import datetime
import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
import config, db, storage

log = logging.getLogger("worker")


class Inspector:
    """Your f3_detect_only.py logic (YOLO + buzzer), grouped into time windows.
    Every WINDOW_SEC produces ONE record: DEFECT if any frame had a defect, else GOOD."""

    def __init__(self):
        from ultralytics import YOLO
        self.model = YOLO(str(config.MODEL_PATH))
        self.buzzer = None
        if not config.LAPTOP:
            from gpiozero import Buzzer
            self.buzzer = Buzzer(config.BUZZER_PIN)
        self._reset()

    def _reset(self):
        self.t0, self.d_conf, self.d_img, self.d_name = None, 0.0, None, None
        self.frames = self.empty_frames = 0

    def analyze(self, frame):
        res = self.model(frame, conf=config.CONF, imgsz=config.IMGSZ, verbose=False)[0]
        names = [self.model.names[int(b.cls[0])].strip().lower() for b in res.boxes]
        empty_here = bool(config.EMPTY_WORDS) and bool(names) and all(
            any(w in n for w in config.EMPTY_WORDS) for n in names)
        if empty_here:
            annotated = frame                    # nothing on the belt: show nothing at all
            self.empty_frames += 1
        else:
            annotated = res.plot()               # the model's own boxes and labels only
        self.frames += 1
        for box, name in zip(res.boxes, names):
            if any(w in name for w in config.DEFECT_WORDS):
                if self.buzzer:
                    self.buzzer.beep(on_time=0.05, off_time=0, n=1, background=True)
                if float(box.conf[0]) > self.d_conf:
                    self.d_conf, self.d_img, self.d_name = float(box.conf[0]), annotated, name
        now = time.time()
        if self.t0 is None:
            self.t0 = now
        if now - self.t0 < config.WINDOW_SEC:
            return annotated, None
        if self.d_img is not None:
            result = {"status": "DEFECT", "defect_type": self.d_name,
                      "confidence": self.d_conf, "image": self.d_img}
        elif config.EMPTY_WORDS and self.empty_frames >= config.EMPTY_SKIP_FRAC * self.frames:
            result = None                       # nothing on the belt: not counted as good or bad
        else:
            result = {"status": "GOOD", "defect_type": None, "confidence": None, "image": annotated}
        self._reset()
        return annotated, result

    def close(self):
        if self.buzzer:
            self.buzzer.off()


class Worker(QThread):
    """Camera is always live. Detection + saving only happen between begin() and end()."""
    frame = pyqtSignal(QImage)
    warning = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.alive = True
        self.run_id = None
        self.insp = None          # set when the model has loaded

    def begin(self, run_id):
        self.run_id = run_id

    def end(self):
        self.run_id = None

    def _load_model(self):
        self.warning.emit("Loading model...")
        try:
            self.insp = Inspector()
            log.info("Model ready")
            self.warning.emit("STOPPED")
        except Exception as e:
            log.exception("Model failed to load")
            self.warning.emit(f"Model failed: {e}")

    def run(self):
        try:
            if config.LAPTOP:
                cap = cv2.VideoCapture(config.CAMERA_INDEX)
                if not cap.isOpened():
                    raise RuntimeError("webcam not found")
                grab, stop_cam = (lambda: cap.read()[1]), cap.release
            else:
                from picamera2 import Picamera2
                cam = Picamera2()
                cam.configure(cam.create_video_configuration(main={"size": config.CAMERA_SIZE}))
                cam.start()
                grab = lambda: cv2.cvtColor(cam.capture_array(), cv2.COLOR_RGBA2BGR)
                stop_cam = cam.stop
        except Exception as e:
            log.error("Camera failed: %s", e)
            self.warning.emit(f"Camera failed: {e}")
            return
        log.info("Camera started")
        threading.Thread(target=self._load_model, daemon=True).start()   # camera stays live meanwhile
        while self.alive:
            try:
                img = grab()
                if img is None:
                    self.msleep(100)
                    continue
                rid = self.run_id
                insp = self.insp
                shown, result = insp.analyze(img) if (rid is not None and insp) else (img, None)
                if result and rid is not None:
                    ts = datetime.now()
                    path = storage.save_image(result["image"], result["status"], ts)
                    db.add_inspection(rid, ts, result["status"],
                                      result["defect_type"], result["confidence"], path)
                rgb = cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)
                h, w, _ = rgb.shape
                self.frame.emit(QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy())
            except Exception:
                log.exception("Frame processing failed")
                self.msleep(1000)
        stop_cam()
        if self.insp:
            self.insp.close()
