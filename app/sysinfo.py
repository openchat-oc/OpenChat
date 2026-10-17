"""Detección ligera del entorno (sin dependencias extra)."""
from __future__ import annotations

import ctypes
import os
import platform
import sys


def is_windows() -> bool:
    return sys.platform.startswith("win")


def total_ram_gb() -> float | None:
    try:
        if is_windows():
            class MEMSTAT(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMSTAT()
            st.dwLength = ctypes.sizeof(MEMSTAT)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return st.ullTotalPhys / 1024 ** 3
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 ** 2
    except Exception:
        return None
    return None


def describe() -> str:
    ram = total_ram_gb()
    return (f"{platform.system()} {platform.release()} · Python {platform.python_version()} · "
            f"{os.cpu_count() or '?'} CPU" + (f" · {ram:.1f} GB RAM" if ram else ""))


def local_model_advice(ram_gb: float | None) -> str:
    if ram_gb is None:
        return "No pude detectar la memoria; empieza por un modelo pequeño."
    if ram_gb < 6:
        return "Memoria limitada: usa un modelo pequeño (1–2 mil millones de parámetros) o el modo nube."
    if ram_gb < 12:
        return "Memoria moderada: los modelos pequeños van bien; evita los de 7B o más."
    return "Memoria suficiente para modelos medianos, pero empieza por uno pequeño si dudas."
