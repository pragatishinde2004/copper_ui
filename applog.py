import datetime
import logging
import sys
from logging.handlers import RotatingFileHandler
import config


def setup():
    """Log file: 5 MB x 10 rotating files (max ~50 MB), plus console output."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(config.LOG_DIR / "inspector.log", maxBytes=5_000_000, backupCount=10)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[fh, logging.StreamHandler()])

    def hook(t, v, tb):
        logging.getLogger("crash").critical("Uncaught exception", exc_info=(t, v, tb))
        mark_shutdown(f"Crash: {t.__name__}: {v}")
    sys.excepthook = hook
    mark_running()


STATE = config.LOG_DIR / "state.txt"


def mark_running():
    """On start: report how the previous session ended, then mark this one as running."""
    log = logging.getLogger("applog")
    if STATE.exists():
        prev = STATE.read_text().strip()
        if prev.startswith("RUNNING"):
            log.warning("Previous session ended WITHOUT a recorded shutdown reason "
                        "(power cut, kill or crash). It was: %s", prev)
        else:
            log.info("Previous shutdown: %s", prev)
    STATE.write_text(f"RUNNING since {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")


def mark_shutdown(reason):
    STATE.write_text(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} - {reason}")
