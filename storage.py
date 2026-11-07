import os
import shutil
import cv2
import config

_good_count = {}      # {"2026-09-29": 7}


def usb_ok():
    return config.USB_ROOT.is_dir() and (config.LAPTOP or config.USB_ROOT.is_mount())


def free_pct():
    u = shutil.disk_usage(config.USB_ROOT)
    return u.free * 100 / u.total


def _good_today(day):
    if day not in _good_count:
        _good_count.clear()
        _good_count[day] = len(list((config.IMG_DIR / day).glob("*/good/*.jpg")))
    return _good_count[day]


def save_image(frame, status, ts):
    """Save one image. Returns the path relative to DATA_DIR, or None if not saved."""
    if not usb_ok() or free_pct() < config.DISK_CRITICAL_PCT:
        return None
    day = ts.strftime("%Y-%m-%d")
    if status == "GOOD":
        if free_pct() < config.DISK_MIN_FREE_PCT or _good_today(day) >= config.MAX_GOOD_PER_DAY:
            return None
    folder = config.IMG_DIR / day / ts.strftime("%H") / status.lower()
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{ts:%Y%m%d_%H%M%S_%f}"[:-3] + f"_{status}.jpg"      # millisecond precision
    path = folder / name
    tmp = folder / ("." + name)              # hidden temp name, renamed only when complete
    try:
        if not cv2.imwrite(str(tmp), frame, [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]):
            return None
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    if status == "GOOD":
        _good_count[day] += 1
    return str(path.relative_to(config.DATA_DIR))
