"""Check a model before using it.
Usage:  python3 check_model.py [path/to/model.pt] [--laptop]
Prints the model's class names, then reads the camera and prints what it detects.
Annotated pictures are saved in model_check/. Press Ctrl+C to stop and see a summary."""
import collections
import os
import sys
import cv2
import config
from ultralytics import YOLO

args = [a for a in sys.argv[1:] if not a.startswith("--")]
model = YOLO(args[0] if args else str(config.MODEL_PATH))
print("Model classes:", model.names)

if config.LAPTOP:
    cap = cv2.VideoCapture(config.CAMERA_INDEX)
    grab = lambda: cap.read()[1]
else:
    from picamera2 import Picamera2
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(main={"size": config.CAMERA_SIZE}))
    cam.start()
    grab = lambda: cv2.cvtColor(cam.capture_array(), cv2.COLOR_RGBA2BGR)

os.makedirs("model_check", exist_ok=True)
seen, n = collections.Counter(), 0
try:
    while True:
        frame = grab()
        if frame is None:
            continue
        res = model(frame, conf=config.CONF, imgsz=config.IMGSZ, verbose=False)[0]
        found = [f"{model.names[int(b.cls[0])]} {float(b.conf[0]):.2f}" for b in res.boxes]
        seen.update(model.names[int(b.cls[0])] for b in res.boxes)
        n += 1
        if n % 5 == 0:
            print(f"frame {n}: {', '.join(found) or 'nothing detected'}")
        if n % 30 == 0:
            cv2.imwrite(f"model_check/frame_{n:05d}.jpg", res.plot())
except KeyboardInterrupt:
    pass
print(f"\nFrames: {n} | detections per class: {dict(seen)}")
