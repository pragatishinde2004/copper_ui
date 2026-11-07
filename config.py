from pathlib import Path

USB_ROOT = Path("/mnt/ml_work")      # CHANGE to your USB mount point
DATA_DIR = USB_ROOT / "inspection_data"
IMG_DIR = DATA_DIR / "images"
DB_URL = f"sqlite:///{DATA_DIR / 'inspection.db'}"

CAMERA_INDEX = 0
JPEG_QUALITY = 85                     # ~150-200 KB per image
MAX_GOOD_PER_DAY = 15                 # defect images are always saved
DISK_MIN_FREE_PCT = 10                # below this, good images stop saving

# --- Detection (from f3_detect_only.py) ---
MODEL_PATH = Path(__file__).parent / "final-v2.pt"   # new model? change the file name here (only place)
CONF = 0.25
IMGSZ = 640
BUZZER_PIN = 17
CAMERA_SIZE = (640, 480)
WINDOW_SEC = 1.0    # one GOOD/DEFECT record per window (a window is DEFECT if any defect frame in it)

# --- 24/7 safety ---
LOG_DIR = Path(__file__).parent / "logs"   # on the SD card, so logging works even if the USB is missing
TEMP_WARN_C = 75
TEMP_SHUTDOWN_C = 82
RAM_MIN_FREE_PCT = 5
DISK_CRITICAL_PCT = 2                      # USB below this free space -> graceful shutdown
CRITICAL_READINGS = 3                      # consecutive 10 s checks before shutting down

# --- Laptop test mode: python main.py --laptop (webcam, no buzzer, local folder, no power-off) ---
import sys
LAPTOP = "--laptop" in sys.argv
if LAPTOP:
    USB_ROOT = Path(__file__).parent / "laptop_data"
    USB_ROOT.mkdir(exist_ok=True)
    DATA_DIR = USB_ROOT / "inspection_data"
    IMG_DIR = DATA_DIR / "images"
    DB_URL = f"sqlite:///{DATA_DIR / 'inspection.db'}"

POPUP_IMAGES = 2      # defect images shown when a bar is clicked

# --- Class names of the model (run check_model.py to see them) ---
DEFECT_WORDS = ("defect",)     # a class whose name contains one of these counts as a defect
EMPTY_WORDS = ("empty", "background")   # class names meaning "nothing on the belt"; () = model has none
EMPTY_SKIP_FRAC = 0.8          # a window that is >= 80% empty frames is not counted at all
