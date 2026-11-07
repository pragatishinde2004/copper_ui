import logging
import signal
import sys
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
import applog
import config
from ui import MainWindow

applog.setup()
app = QApplication(sys.argv)
w = MainWindow()
w.show() if ("--dev" in sys.argv or config.LAPTOP) else w.showFullScreen()
app.aboutToQuit.connect(w.cleanup)
def on_signal(signum, _):
    w.shutdown_reason = f"Signal {signal.Signals(signum).name} received (system shutdown, service stop or Ctrl+C)"
    app.quit()


for s in (signal.SIGTERM, signal.SIGINT, getattr(signal, "SIGHUP", signal.SIGTERM)):
    signal.signal(s, on_signal)
tick = QTimer()
tick.timeout.connect(lambda: None)                         # lets Python handle signals
tick.start(500)
logging.getLogger("main").info("App started")
sys.exit(app.exec_())
