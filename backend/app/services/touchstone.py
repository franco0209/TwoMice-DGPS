"""Lectura de archivos Touchstone .s1p y cálculo de S11, VSWR e impedancia."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_FREQ_UNITS = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}


@dataclass
class Sparam1Port:
    freq_hz: np.ndarray
    gamma: np.ndarray  # coeficiente de reflexión complejo (S11)
    z0: float = 50.0

    @property
    def s11_db(self) -> np.ndarray:
        return 20 * np.log10(np.maximum(np.abs(self.gamma), 1e-12))

    @property
    def vswr(self) -> np.ndarray:
        mag = np.minimum(np.abs(self.gamma), 0.999999)
        return (1 + mag) / (1 - mag)

    @property
    def impedance(self) -> np.ndarray:
        g = np.where(np.abs(1 - self.gamma) < 1e-12, 1 - 1e-12, self.gamma)
        return self.z0 * (1 + g) / (1 - g)


def parse_s1p(text: str) -> Sparam1Port:
    unit, fmt, z0 = 1e9, "MA", 50.0  # valores por defecto del estándar
    rows: list[list[float]] = []
    for raw in text.splitlines():
        line = raw.split("!")[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            tok = line[1:].upper().split()
            for t in tok:
                if t in _FREQ_UNITS:
                    unit = _FREQ_UNITS[t]
            if "S" in tok:
                pass
            for t in tok:
                if t in ("DB", "MA", "RI"):
                    fmt = t
            if "R" in tok and tok.index("R") + 1 < len(tok):
                z0 = float(tok[tok.index("R") + 1])
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 3:
            rows.append([float(p) for p in parts[:3]])
    if not rows:
        raise ValueError("El archivo no contiene datos de S11")

    data = np.array(rows)
    freq = data[:, 0] * unit
    a, b = data[:, 1], data[:, 2]
    if fmt == "RI":
        gamma = a + 1j * b
    elif fmt == "DB":
        gamma = 10 ** (a / 20) * np.exp(1j * np.deg2rad(b))
    else:  # MA
        gamma = a * np.exp(1j * np.deg2rad(b))
    order = np.argsort(freq)
    return Sparam1Port(freq[order], gamma[order], z0)
