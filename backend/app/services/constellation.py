"""Constelación GPS: elementos keplerianos y posición ECEF (IS-GPS-200).

Dos orígenes de datos:
  * `synthetic_constellation`: 30 satélites en 6 planos (55°), representativa
    pero NO es el cielo real de una fecha concreta.
  * `parse_yuma`: almanaque YUMA real (descargable de navcen.uscg.gov), para
    reproducir la geometría real de un día.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

MU = 3.986005e14          # m^3/s^2
OMEGA_E = 7.2921151467e-5  # rad/s
C = 299792458.0
WEEK = 604800.0


@dataclass
class SatArray:
    """Elementos orbitales en arreglos (vectorizable)."""
    prn: np.ndarray
    a: np.ndarray
    e: np.ndarray
    inc: np.ndarray       # rad
    raan0: np.ndarray     # rad, Ω0 de IS-GPS-200
    raan_rate: np.ndarray  # rad/s, Ω̇
    argp: np.ndarray      # rad
    m0: np.ndarray        # rad
    toe: np.ndarray       # s de la semana

    def __len__(self):
        return len(self.prn)

    def subset(self, idx) -> "SatArray":
        return SatArray(*(getattr(self, f)[idx] for f in self.__dataclass_fields__))


def positions_ecef(sat: SatArray, t_sow) -> np.ndarray:
    """Posición ECEF (N,3) de cada satélite en el instante de transmisión t_sow.

    `t_sow` puede ser un escalar o un arreglo (N,) (un instante por satélite).
    La posición está expresada en el marco ECEF de ese mismo instante.
    """
    tk = np.asarray(t_sow, dtype=float) - sat.toe
    tk = (tk + WEEK / 2) % WEEK - WEEK / 2
    n = np.sqrt(MU / sat.a ** 3)
    m = sat.m0 + n * tk
    ecc = m.copy()
    for _ in range(8):
        ecc = m + sat.e * np.sin(ecc)
    nu = np.arctan2(np.sqrt(1 - sat.e ** 2) * np.sin(ecc), np.cos(ecc) - sat.e)
    r = sat.a * (1 - sat.e * np.cos(ecc))
    u = nu + sat.argp
    xo, yo = r * np.cos(u), r * np.sin(u)
    omg = sat.raan0 + (sat.raan_rate - OMEGA_E) * tk - OMEGA_E * sat.toe
    ci, si = np.cos(sat.inc), np.sin(sat.inc)
    co, so = np.cos(omg), np.sin(omg)
    return np.stack([xo * co - yo * ci * so, xo * so + yo * ci * co, yo * si], axis=1)


def to_rx_frame(pos_tx: np.ndarray, tau) -> np.ndarray:
    """Corrección de Sagnac: pasa de ECEF(t_tx) a ECEF(t_rx) con tiempo de vuelo tau."""
    th = OMEGA_E * np.asarray(tau, dtype=float)
    c, s = np.cos(th), np.sin(th)
    x, y, z = pos_tx[:, 0], pos_tx[:, 1], pos_tx[:, 2]
    return np.stack([x * c + y * s, -x * s + y * c, z], axis=1)


def synthetic_constellation(seed: int = 1, planes: int = 6, per_plane: int = 5) -> SatArray:
    rng = np.random.default_rng(seed)
    n = planes * per_plane
    p = np.repeat(np.arange(planes), per_plane)
    k = np.tile(np.arange(per_plane), planes)
    raan = np.radians(p * 360.0 / planes + 17.0)
    m0 = np.radians(k * 360.0 / per_plane + p * 360.0 / (planes * per_plane) * 2 + rng.uniform(-6, 6, n))
    return SatArray(
        prn=np.arange(1, n + 1),
        a=np.full(n, 26559.7e3),
        e=rng.uniform(0.001, 0.012, n),
        inc=np.radians(np.full(n, 55.0)),
        raan0=raan,
        raan_rate=np.full(n, -8.0e-9),
        argp=np.radians(rng.uniform(0, 360, n)),
        m0=m0,
        toe=np.zeros(n),
    )


_YUMA_KEYS = {
    "ID": "prn", "Eccentricity": "e", "Time of Applicability(s)": "toa",
    "Orbital Inclination(rad)": "inc", "Rate of Right Ascen(r/s)": "rate",
    "SQRT(A)  (m 1/2)": "sqrta", "Right Ascen at Week(rad)": "raan0",
    "Argument of Perigee(rad)": "argp", "Mean Anom(rad)": "m0", "Health": "health",
}


def parse_yuma(text: str, only_healthy: bool = True) -> SatArray:
    """Lee un almanaque YUMA. Devuelve los satélites sanos por defecto."""
    sats = []
    for block in re.split(r"\*{5,}.*\n", text):
        rec = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            for k, name in _YUMA_KEYS.items():
                if key == k.strip():
                    rec[name] = float(val.split()[0])
        if {"prn", "e", "toa", "inc", "rate", "sqrta", "raan0", "argp", "m0"} <= rec.keys():
            if only_healthy and rec.get("health", 0) != 0:
                continue
            sats.append(rec)
    if not sats:
        raise ValueError("Almanaque YUMA sin satélites válidos")
    col = lambda k: np.array([s[k] for s in sats], dtype=float)
    return SatArray(
        prn=col("prn").astype(int), a=col("sqrta") ** 2, e=col("e"), inc=col("inc"),
        raan0=col("raan0"), raan_rate=col("rate"), argp=col("argp"), m0=col("m0"),
        toe=col("toa"),
    )
