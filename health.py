import config, storage


def cpu_temp():
    try:
        return int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
    except OSError:
        return None


def ram_free_pct():
    try:
        m = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
        return m["MemAvailable"] * 100 / m["MemTotal"]
    except (OSError, KeyError):
        return None


def summary():
    t, r = cpu_temp(), ram_free_pct()
    d = storage.free_pct() if storage.usb_ok() else None
    f = lambda v: "n/a" if v is None else f"{v:.0f}"
    return f"heartbeat temp={f(t)}C ram_free={f(r)}% usb_free={f(d)}%"


class Monitor:
    def __init__(self):
        self.bad = 0

    def check(self):
        """Returns (warnings, critical_reason). A critical reason is only returned after
        CRITICAL_READINGS consecutive bad checks, so a short spike never shuts the Pi down."""
        warns, crit = [], None
        t, ram = cpu_temp(), ram_free_pct()
        if t is not None:
            if t >= config.TEMP_SHUTDOWN_C:
                crit = f"CPU temperature {t:.0f} C"
            elif t >= config.TEMP_WARN_C:
                warns.append("CPU running hot")
        if ram is not None and ram < config.RAM_MIN_FREE_PCT:
            crit = crit or f"RAM almost full ({ram:.0f}% free)"
        if storage.usb_ok():
            free = storage.free_pct()
            if free < config.DISK_CRITICAL_PCT:
                crit = crit or f"USB drive full ({free:.1f}% free)"
            elif free < config.DISK_MIN_FREE_PCT:
                warns.append("Low disk space - good images paused, defects still saved")
        else:
            warns.append("USB drive not found - images will not be saved")
        self.bad = self.bad + 1 if crit else 0
        return warns, (crit if self.bad >= config.CRITICAL_READINGS else None)
