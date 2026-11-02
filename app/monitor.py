"""Live system readings for the sidebar: CPU, RAM, GPU (via nvidia-smi) and free disk space.

Nothing here needs extra packages: CPU load comes from GetSystemTimes, RAM from GlobalMemoryStatusEx.
"""

import ctypes
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import engine

GB = 1024 ** 3


class _FileTime(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_ulong), ("hi", ctypes.c_ulong)]


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _ticks(ft):
    return (ft.hi << 32) | ft.lo


def _num(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None  # "[N/A]" and the like


def _mac_cpu():
    # sum of per-process load from ps, scaled to all cores
    try:
        out = subprocess.run(["ps", "-A", "-o", "%cpu="], capture_output=True, text=True, timeout=4).stdout
        total = sum(_num(x) or 0 for x in out.split())
        return round(min(100.0, total / (os.cpu_count() or 1)), 1)
    except Exception:
        return None


def _mac_ram():
    try:
        total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=4).stdout)
        out = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return None
    page = int(re.search(r"page size of (\d+)", out).group(1)) if "page size of" in out else 16384
    pages = {k.strip(): int(v.strip().rstrip(".")) for k, v in re.findall(r"^([^:\n]+):\s+(\d+)\.?$", out, re.M)}
    # what Activity Monitor calls "memory used": app memory + wired + compressed
    used = (pages.get("Anonymous pages", 0) - pages.get("Pages purgeable", 0) + pages.get("Pages wired down", 0)
            + pages.get("Pages occupied by compressor", 0)) * page
    return {"total_gb": round(total / GB, 1), "used_gb": round(used / GB, 1)}


def _mac_gpu():
    # the Apple GPU reports its load to the IORegistry; it has no memory of its own (it uses the RAM)
    try:
        out = subprocess.run(["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"], capture_output=True, text=True,
                             timeout=4).stdout
    except Exception:
        return None
    util = re.search(r'"Device Utilization %"\s*=\s*(\d+)', out)
    model = re.search(r'"model"\s*=\s*"([^"]+)"', out)
    return {"name": (model.group(1) if model else "Apple") + " GPU", "shared": True,
            "util": float(util.group(1)) if util else None}


def _mac_volume(p):
    # "/Volumes/T7/..." -> "T7"; the startup disk needs no name (a long path does not fit the sidebar)
    parts = p.resolve().parts
    return parts[2] if len(parts) > 2 and parts[1] == "Volumes" else ""


class Monitor:
    def __init__(self):
        self._cpu_prev = None
        self._cache, self._at = None, 0.0

    def cpu_percent(self):
        if engine.IS_MAC:
            return _mac_cpu()
        idle, kernel, user = _FileTime(), _FileTime(), _FileTime()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        now = (_ticks(idle), _ticks(kernel) + _ticks(user))  # kernel time already includes idle time
        prev, self._cpu_prev = self._cpu_prev, now
        if not prev or now[1] <= prev[1]:
            return None
        return round(100 * (1 - (now[0] - prev[0]) / (now[1] - prev[1])), 1)

    @staticmethod
    def ram():
        if engine.IS_MAC:
            return _mac_ram()
        m = _MemStatus(dwLength=ctypes.sizeof(_MemStatus))
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        total = m.ullTotalPhys / GB
        return {"total_gb": round(total, 1), "used_gb": round(total - m.ullAvailPhys / GB, 1)}

    @staticmethod
    def gpu():
        if engine.IS_MAC:
            return _mac_gpu()
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=4, creationflags=engine.CREATE_NO_WINDOW).stdout
        except Exception:
            return None
        rows = [[x.strip() for x in line.split(",")] for line in out.strip().splitlines() if line.strip()]
        if not rows:
            return None
        r = max(rows, key=lambda r: _num(r[3]) or 0)  # the card with the most memory is the one in use
        used, total = _num(r[2]), _num(r[3])
        return {"name": r[0].replace("NVIDIA GeForce ", ""), "util": _num(r[1]),
                "vram_used_gb": round(used / 1024, 1) if used is not None else None,
                "vram_total_gb": round(total / 1024, 1) if total is not None else None,
                "temp": _num(r[4]), "power": _num(r[5]), "power_limit": _num(r[6])}

    @staticmethod
    def disk(path):
        p = Path(path)
        while not p.exists() and p.parent != p:
            p = p.parent
        try:
            u = shutil.disk_usage(p)
        except OSError:
            return None
        return {"free_gb": round(u.free / GB), "total_gb": round(u.total / GB),
                "drive": _mac_volume(p) if engine.IS_MAC else p.drive or str(p)}

    def sample(self, disk_path):
        """At most one reading per second, however many windows ask."""
        if self._cache and time.monotonic() - self._at < 1.0:
            return self._cache
        self._cache = {"cpu": self.cpu_percent(), "ram": self.ram(), "gpu": self.gpu(), "disk": self.disk(disk_path)}
        self._at = time.monotonic()
        return self._cache
