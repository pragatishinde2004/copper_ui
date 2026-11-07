import logging
import os
import subprocess
from datetime import date, timedelta
from PyQt5.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PyQt5.QtWidgets import (QWidget, QDialog, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QMessageBox, QApplication)
import applog, config, db, health, storage
from detector import Worker

log = logging.getLogger("ui")
BTN = "font-size:26px;font-weight:bold;padding:18px;border-radius:12px;color:white;background:%s;"


def btn(color):
    """Button style; a disabled button turns grey so workers can see it is inactive."""
    return "QPushButton{%s}QPushButton:disabled{background:#B4B2A9;color:#5F5E5A;}" % (BTN % color)



class BarChart(QWidget):
    """One blue bar per day. Clicking a bar emits that day's date."""
    barClicked = pyqtSignal(object)
    BLUE = QColor("#185FA5")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.days, self.counts, self.cols = [], [], []
        self.setMinimumHeight(280)
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, days, counts):
        self.days, self.counts = days, counts
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        text = self.palette().color(QPalette.WindowText)
        font = p.font()
        font.setPointSize(12)
        p.setFont(font)
        w, h, left, top, bottom = self.width(), self.height(), 50, 30, 50
        ch = h - top - bottom
        top_val = max(4, -(-max(self.counts, default=0) // 4) * 4)     # round up to a multiple of 4
        for i in range(5):                                              # grid lines + y labels
            y = top + ch - ch * i / 4
            p.setPen(QPen(QColor("#D3D1C7"), 1))
            p.drawLine(left, int(y), w - 10, int(y))
            p.setPen(text)
            p.drawText(QRectF(0, y - 12, left - 8, 24), Qt.AlignRight | Qt.AlignVCenter,
                       str(top_val * i // 4))
        slot = (w - left - 10) / max(len(self.days), 1)
        self.cols = []
        for i, (d, c) in enumerate(zip(self.days, self.counts)):
            bw = slot * 0.55
            x = left + slot * i + (slot - bw) / 2
            bh = ch * c / top_val
            self.cols.append(QRectF(left + slot * i, top, slot, ch))    # whole column is clickable
            if c:
                p.setPen(Qt.NoPen)
                p.setBrush(self.BLUE)
                p.drawRoundedRect(QRectF(x, top + ch - bh, bw, bh), 6, 6)
            p.setPen(text)
            p.drawText(QRectF(x - 20, top + ch - bh - 26, bw + 40, 24), Qt.AlignCenter, str(c))
            p.drawText(QRectF(left + slot * i, h - bottom + 6, slot, 40),
                       Qt.AlignHCenter | Qt.AlignTop, f"{d:%a}\n{d:%d %b}")

    def mousePressEvent(self, e):
        for d, r in zip(self.days, self.cols):
            if r.contains(e.localPos()):
                self.barClicked.emit(d)
                return


class ImageDialog(QDialog):
    """Pop-up with random defect images captured on one day. 'Show other images' picks new ones."""

    def __init__(self, day, parent=None):
        super().__init__(parent)
        self.day = day
        self.setWindowTitle(f"Defects on {day:%d %b %Y}")
        lay = QVBoxLayout(self)
        title = QLabel(f"Defect images - {day:%A, %d %b %Y}")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px;font-weight:bold;")
        lay.addWidget(title)
        self.row = QHBoxLayout()
        lay.addLayout(self.row)
        buttons = QHBoxLayout()
        other = QPushButton("Show other images")
        other.setStyleSheet(btn("#185FA5"))
        other.clicked.connect(self.load)
        close = QPushButton("Close")
        close.setStyleSheet(btn("#5F5E5A"))
        close.clicked.connect(self.accept)
        buttons.addWidget(other)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.load()

    def load(self):
        while self.row.count():                            # remove the previous images
            w = self.row.takeAt(0).widget()
            if w:
                w.deleteLater()
        try:
            paths = db.defect_images(self.day, config.POPUP_IMAGES * 3)   # spare ones in case a file is missing
        except Exception:
            paths = []
        shown = 0
        for rel in paths:
            pm = QPixmap(str(config.DATA_DIR / rel))
            if pm.isNull():
                continue
            lbl = QLabel()
            lbl.setPixmap(pm.scaled(440, 330, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.row.addWidget(lbl)
            shown += 1
            if shown == config.POPUP_IMAGES:
                break
        if not shown:
            none = QLabel("No defect images saved for this date")
            none.setAlignment(Qt.AlignCenter)
            none.setStyleSheet("font-size:20px;padding:40px;")
            self.row.addWidget(none)


class Dashboard(QDialog):
    """Weekly (Monday-Sunday) defect bar chart with previous / next week buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.offset = 0                                   # weeks back from this week
        lay = QVBoxLayout(self)
        title = QLabel("Defects per day")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:30px;font-weight:bold;")
        lay.addWidget(title)
        nav = QHBoxLayout()
        self.prev_btn, self.next_btn = QPushButton("< Previous week"), QPushButton("Next week >")
        self.range_lbl = QLabel(alignment=Qt.AlignCenter)
        self.range_lbl.setStyleSheet("font-size:22px;")
        for b in (self.prev_btn, self.next_btn):
            b.setStyleSheet(btn("#185FA5"))
        self.prev_btn.clicked.connect(lambda: self.shift(1))
        self.next_btn.clicked.connect(lambda: self.shift(-1))
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.range_lbl, 1)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)
        self.chart = BarChart()
        self.chart.barClicked.connect(lambda d: ImageDialog(d, self).exec_())
        lay.addWidget(self.chart, 1)
        hint = QLabel("Tap a bar to see the defect images of that day")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)
        back = QPushButton("BACK")
        back.setStyleSheet(btn("#5F5E5A"))
        back.clicked.connect(self.accept)
        lay.addWidget(back)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        self.refresh()

    def shift(self, weeks):
        self.offset = max(0, self.offset + weeks)
        self.refresh()

    def refresh(self):
        start = date.today() - timedelta(days=date.today().weekday()) - timedelta(weeks=self.offset)
        end = start + timedelta(days=6)
        try:
            counts = db.defects_by_day(start, end)
        except Exception:
            counts = [0] * 7
        self.chart.set_data([start + timedelta(days=i) for i in range(7)], counts)
        self.range_lbl.setText(f"{start:%d %b} - {end:%d %b %Y}")
        self.next_btn.setEnabled(self.offset > 0)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.run_id = None
        self.video = QLabel(alignment=Qt.AlignCenter)
        self.video.setMinimumSize(640, 360)
        self.video.setStyleSheet("background:black;")
        self.status = QLabel("STOPPED", alignment=Qt.AlignCenter)
        self.status.setStyleSheet("font-size:26px;font-weight:bold;color:#c62828;")
        self.warn = QLabel(alignment=Qt.AlignCenter)
        self.warn.setStyleSheet("background:#ffb300;font-size:22px;font-weight:bold;padding:10px;")
        self.warn.hide()

        self.b_start = QPushButton("START")
        self.b_stop = QPushButton("STOP")
        b_dash = QPushButton("DASHBOARD")
        b_off = QPushButton("SHUTDOWN")
        for b, color in [(self.b_start, "#2e7d32"), (self.b_stop, "#c62828"),
                         (b_dash, "#1565c0"), (b_off, "#455a64")]:
            b.setStyleSheet(btn(color))
        self.b_stop.setEnabled(False)
        self.b_start.clicked.connect(self.start)
        self.b_stop.clicked.connect(self.stop)
        b_dash.clicked.connect(self.open_dashboard)
        b_off.clicked.connect(self.shutdown)

        row = QHBoxLayout()
        for b in (self.b_start, self.b_stop, b_dash, b_off):
            row.addWidget(b)
        lay = QVBoxLayout(self)
        for w in (self.warn, self.video, self.status):
            lay.addWidget(w)
        lay.setStretch(1, 1)
        lay.addLayout(row)

        self.worker = Worker()
        self.worker.frame.connect(self.on_frame)
        self.worker.warning.connect(self.status.setText)
        self.worker.start()
        self.monitor = health.Monitor()
        self.beats, self.last_warns, self.closing = 0, [], False
        self.shutdown_reason = None
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.health_check)
        self.health_timer.start(10000)
        self.health_check()

    def on_frame(self, img):
        self.video.setPixmap(QPixmap.fromImage(img).scaled(
            self.video.size(), Qt.KeepAspectRatio, Qt.FastTransformation))

    def health_check(self):
        warns, crit = self.monitor.check()
        if warns:
            self.warn.setText("   |   ".join(warns))
            self.warn.show()
        else:
            self.warn.hide()
        if warns != self.last_warns:
            for w in warns:
                log.warning(w)
            self.last_warns = warns
        self.beats += 1
        if self.beats % 60 == 1:                  # about every 10 minutes
            log.info(health.summary())
        if crit and not self.closing and not config.LAPTOP:
            self.safe_shutdown(crit)

    def start(self):
        if self.worker.insp is None:
            QMessageBox.warning(self, "Model", "The detection model is not loaded.\n"
                                "Check that models/final.pt exists. Details are in logs/inspector.log")
            return
        if not storage.usb_ok():
            QMessageBox.warning(self, "USB drive", "USB drive not found. Insert it and try again.")
            return
        self.run_id = db.start_run()
        log.info("Run %s started", self.run_id)
        self.worker.begin(self.run_id)
        self.status.setText("RUNNING")
        self.status.setStyleSheet("font-size:26px;font-weight:bold;color:#2e7d32;")
        self.b_start.setEnabled(False)
        self.b_stop.setEnabled(True)

    def stop(self):
        self.worker.end()
        if self.run_id:
            log.info("Run %s stopped", self.run_id)
            db.end_run(self.run_id)
            self.run_id = None
        self.status.setText("STOPPED")
        self.status.setStyleSheet("font-size:26px;font-weight:bold;color:#c62828;")
        self.b_start.setEnabled(True)
        self.b_stop.setEnabled(False)
        QApplication.instance().quit()

    def open_dashboard(self):
        dlg = Dashboard(self)
        dlg.showFullScreen()
        dlg.exec_()

    def shutdown(self):
        if QMessageBox.question(self, "Shutdown", "Shut down the Raspberry Pi?") == QMessageBox.Yes:
            self.safe_shutdown("Shutdown button pressed")

    def cleanup(self):
        """Stop everything in the right order so no file is left half-written."""
        if self.closing:
            return
        self.closing = True
        reason = self.shutdown_reason or "Application closed (no reason given)"
        log.critical("Shutting down. Reason: %s", reason)
        applog.mark_shutdown(reason)
        self.stop()
        self.worker.alive = False
        self.worker.wait(5000)
        db.close()
        log.info("Cleanup done")

    def safe_shutdown(self, reason):
        self.shutdown_reason = reason
        self.cleanup()
        if config.LAPTOP:
            log.info("Laptop mode: not powering off")
            return
        os.sync()
        subprocess.run(["sudo", "shutdown", "-h", "now"])

    def closeEvent(self, e):
        self.shutdown_reason = self.shutdown_reason or "Window closed"
        self.cleanup()
        e.accept()
