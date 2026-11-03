"""Detección de resonancias, ancho de banda y comparación con bandas GNSS."""
from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from .touchstone import Sparam1Port

# Frecuencias centrales GNSS en MHz
GNSS_BANDS = {
    "GPS L5": 1176.45,
    "GPS L2": 1227.60,
    "GLONASS L2": 1246.00,
    "GLONASS L1": 1602.00,
    "GPS L1": 1575.42,
}


def find_resonances(
    sp: Sparam1Port, bw_level_db: float = -10.0, min_prominence_db: float = 3.0
) -> list[dict]:
    f_mhz = sp.freq_hz / 1e6
    s11 = sp.s11_db
    vswr = sp.vswr
    z = sp.impedance
    idx, _ = find_peaks(-s11, prominence=min_prominence_db)

    out = []
    for i in idx:
        lo = hi = i
        while lo > 0 and s11[lo] <= bw_level_db:
            lo -= 1
        while hi < len(s11) - 1 and s11[hi] <= bw_level_db:
            hi += 1
        has_bw = s11[i] <= bw_level_db
        f0 = float(f_mhz[i])
        out.append(
            {
                "freq_mhz": f0,
                "s11_db": float(s11[i]),
                "vswr": float(vswr[i]),
                "z_real": float(z[i].real),
                "z_imag": float(z[i].imag),
                "bw_mhz": float(f_mhz[hi] - f_mhz[lo]) if has_bw else None,
                "f_low_mhz": float(f_mhz[lo]) if has_bw else None,
                "f_high_mhz": float(f_mhz[hi]) if has_bw else None,
                "covers": [
                    n
                    for n, fc in GNSS_BANDS.items()
                    if has_bw and f_mhz[lo] <= fc <= f_mhz[hi]
                ],
            }
        )
    return out


def band_report(sp: Sparam1Port) -> dict[str, dict]:
    """S11 y VSWR en la frecuencia de cada banda GNSS (interpolado)."""
    f_mhz = sp.freq_hz / 1e6
    rep = {}
    for name, fc in GNSS_BANDS.items():
        if f_mhz[0] <= fc <= f_mhz[-1]:
            rep[name] = {
                "freq_mhz": fc,
                "s11_db": float(np.interp(fc, f_mhz, sp.s11_db)),
                "vswr": float(np.interp(fc, f_mhz, sp.vswr)),
            }
    return rep
