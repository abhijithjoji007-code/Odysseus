from __future__ import annotations
from datetime import datetime
import platform
import shutil
import psutil

def current_time_message() -> str:
    now = datetime.now()
    return f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %d %B %Y')}."

def system_metrics() -> dict[str, int | float | str]:
    disk = shutil.disk_usage('/')
    try:
        battery = psutil.sensors_battery()
    except (OSError, RuntimeError):
        battery = None
    return {
        "cpu_percent": round(psutil.cpu_percent(interval=0.15), 1),
        "ram_percent": round(psutil.virtual_memory().percent, 1),
        "disk_percent": round((disk.used / disk.total) * 100, 1),
        "battery_percent": int(battery.percent) if battery else -1,
        "platform": platform.system(),
    }

def system_summary() -> str:
    m = system_metrics()
    battery = "unavailable" if m["battery_percent"] == -1 else f'{m["battery_percent"]}%'
    return f"CPU usage is {m['cpu_percent']}%. RAM usage is {m['ram_percent']}%. Disk usage is {m['disk_percent']}%. Battery is {battery}."
