"""Simulador GNSS a nivel de pseudorango que emite NMEA.

Cadena (por receptor y por época):
  órbitas keplerianas -> geometría (con tiempo de vuelo y Sagnac) -> pseudorangos
  con errores físicos -> selección de satélites rastreados (máscara de elevación,
  umbral C/N0) -> PVT por mínimos cuadrados ponderados -> sentencias NMEA.

Qué es COMÚN a ambos receptores (se cancela en el diferencial): error de
efemérides/reloj del satélite, ionosfera y troposfera residuales.
Qué es INDEPENDIENTE por receptor (no se cancela): multitrayecto, ruido,
reloj del receptor y la selección de satélites (C/N0 depende de la antena).

Como la posición sale de resolver los pseudorangos de cada receptor, el efecto
de que dos receptores usen conjuntos de satélites distintos aparece solo,
sin inyectarlo a mano. Limitaciones: la salida de un receptor real pasa además
por un filtro interno (Kalman) y por modelos de iono/tropo propios; aquí se
modelan sólo como error residual. La constelación sintética no es el cielo real
de la fecha salvo que se cargue un almanaque YUMA.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from . import nmea
from .constellation import (C, SatArray, positions_ecef, synthetic_constellation,
                            to_rx_frame)
from .geo import azel, ecef_to_geodetic, enu_matrix, geodetic_to_ecef

GPS_EPOCH = dt.datetime(1980, 1, 6, tzinfo=dt.timezone.utc)
LEAP_SECONDS = 18
RE = 6371e3
SHELL_H = 350e3


@dataclass
class ReceiverConfig:
    name: str
    lat: float
    lon: float
    alt: float                       # altura elipsoidal verdadera (m)
    cn0_offset_db: float = 0.0       # p. ej. pérdida por desadaptación (ver módulo VNA)
    noise_scale: float = 1.0
    multipath_scale: float = 1.0
    ttff_s: float = 10.0             # segundos hasta el primer fix


@dataclass
class SimConfig:
    start: dt.datetime
    receivers: list[ReceiverConfig]
    dt: float = 1.0
    seed: int = 1
    elev_mask: float = 10.0
    max_sats: int = 12
    cn0_min_track: float = 33.0
    iono_zenith_m: float = 5.0
    iono_residual: float = 0.5       # fracción que el modelo del receptor NO corrige
    tropo_residual: float = 0.04
    eph_sigma_m: float = 1.2
    eph_tau_s: float = 3600.0
    atm_sigma_m: float = 0.4
    atm_tau_s: float = 900.0
    mp_sigma_m: float = 0.9
    mp_tau_s: float = 120.0
    noise_sigma_m: float = 0.35
    cn0_tau_s: float = 20.0
    cn0_sigma_db: float = 2.0
    geoid_sep_m: float = 0.0
    nmea_decimals: int = 4


def gps_sow(t_utc: dt.datetime) -> float:
    return ((t_utc - GPS_EPOCH).total_seconds() + LEAP_SECONDS) % 604800.0


def _gm(state, tau, step, rng):
    """Proceso Gauss-Markov de varianza unitaria."""
    phi = np.exp(-step / tau)
    return phi * state + np.sqrt(1 - phi ** 2) * rng.standard_normal(state.shape)


def solve_pvt(sats: SatArray, pr, sigma, t_sow, x0, lat_lon):
    """PVT por mínimos cuadrados ponderados. Devuelve (x_ecef, b, dops) o None."""
    n = len(pr)
    if n < 4:
        return None
    x = np.array(x0, dtype=float)
    b = 0.0
    w = 1.0 / sigma ** 2
    for _ in range(12):
        tau = (pr - b) / C
        prx = to_rx_frame(positions_ecef(sats, t_sow - tau), tau)
        d = prx - x
        rho = np.linalg.norm(d, axis=1)
        u = d / rho[:, None]
        h = np.hstack([-u, np.ones((n, 1))])
        res = pr - (rho + b)
        hw = h * w[:, None]
        try:
            dx = np.linalg.solve(h.T @ hw, hw.T @ res)
        except np.linalg.LinAlgError:
            return None
        x += dx[:3]
        b += dx[3]
        if np.linalg.norm(dx[:3]) < 1e-4:
            break
    rot = enu_matrix(*lat_lon)
    he = h[:, :3] @ rot.T
    try:
        q = np.linalg.inv(np.hstack([he, np.ones((n, 1))]).T @ np.hstack([he, np.ones((n, 1))]))
    except np.linalg.LinAlgError:
        return None
    hdop = float(np.sqrt(q[0, 0] + q[1, 1]))
    vdop = float(np.sqrt(q[2, 2]))
    pdop = float(np.sqrt(q[0, 0] + q[1, 1] + q[2, 2]))
    return x, b, (pdop, hdop, vdop)


class GnssSimulator:
    def __init__(self, cfg: SimConfig, sats: SatArray | None = None):
        self.cfg = cfg
        self.sats = sats if sats is not None else synthetic_constellation(cfg.seed)
        self.t = cfg.start.astimezone(dt.timezone.utc)
        self.k = 0
        self.rng = np.random.default_rng(cfg.seed + 1000)
        n, r = len(self.sats), len(cfg.receivers)
        self._eph = self.rng.standard_normal(n)
        self._atm = self.rng.standard_normal(n)
        self._mp = self.rng.standard_normal((r, n))
        self._cn0 = self.rng.standard_normal((r, n))
        self._clk0 = self.rng.uniform(-1e5, 1e5, r)
        self._drift = self.rng.normal(0, 20.0, r)
        self._x_prev: list[np.ndarray] = [np.zeros(3) for _ in range(r)]
        self.truth_ecef = [geodetic_to_ecef(rc.lat, rc.lon, rc.alt) for rc in cfg.receivers]
        self.last: dict[str, dict] = {}

    # --------------------------------------------------------------- paso
    def step(self) -> dict[str, list[str]]:
        cfg = self.cfg
        s = cfg.dt
        self._eph = _gm(self._eph, cfg.eph_tau_s, s, self.rng)
        self._atm = _gm(self._atm, cfg.atm_tau_s, s, self.rng)
        self._mp = _gm(self._mp, cfg.mp_tau_s, s, self.rng)
        self._cn0 = _gm(self._cn0, cfg.cn0_tau_s, s, self.rng)
        sow = gps_sow(self.t)
        out = {rc.name: self._receiver_epoch(i, rc, sow) for i, rc in enumerate(cfg.receivers)}
        self.t += dt.timedelta(seconds=s)
        self.k += 1
        return out

    def _receiver_epoch(self, i, rc: ReceiverConfig, sow) -> list[str]:
        cfg, sats = self.cfg, self.sats
        rx = self.truth_ecef[i]
        nsat = len(sats)

        tau = np.full(nsat, 0.075)
        for _ in range(3):
            prx = to_rx_frame(positions_ecef(sats, sow - tau), tau)
            rho = np.linalg.norm(prx - rx, axis=1)
            tau = rho / C
        az, el = azel(rx, prx, rc.lat, rc.lon)
        sin_el = np.sin(np.radians(np.clip(el, 1.0, 90.0)))

        # C/N0 y rastreo
        cn0 = 47.0 - 16.0 * (1 - sin_el) + cfg.cn0_sigma_db * self._cn0[i] + rc.cn0_offset_db
        cand = np.where((el >= cfg.elev_mask) & (cn0 >= cfg.cn0_min_track))[0]
        tracked = cand[np.argsort(-cn0[cand])][: cfg.max_sats]

        # errores de pseudorango
        obl = 1.0 / np.sqrt(1 - (RE * np.cos(np.radians(el)) / (RE + SHELL_H)) ** 2)
        local_h = (self.t.hour + self.t.minute / 60 + rc.lon / 15.0) % 24
        diurnal = 0.15 + 0.85 * max(0.0, np.cos(2 * np.pi * (local_h - 14) / 24))
        iono = cfg.iono_residual * cfg.iono_zenith_m * diurnal * obl
        tropo = cfg.tropo_residual * 2.3 * np.exp(-rc.alt / 8000.0) * 1.001 / np.sqrt(0.002001 + sin_el ** 2)
        common = cfg.eph_sigma_m * self._eph + cfg.atm_sigma_m * obl * self._atm + iono + tropo
        mp_sig = cfg.mp_sigma_m * rc.multipath_scale * (0.25 + np.exp(-np.clip(el, 0, 90) / 20.0))
        noise_sig = cfg.noise_sigma_m * rc.noise_scale * 10 ** ((45.0 - cn0) / 20.0)
        clock = self._clk0[i] + self._drift[i] * self.k * cfg.dt
        pr = (rho + clock + common + mp_sig * self._mp[i]
              + noise_sig * self.rng.standard_normal(nsat))

        t_utc = self.t
        fix = None
        if self.k * cfg.dt >= rc.ttff_s and len(tracked) >= 4:
            sigma = np.sqrt(0.3 ** 2 + (0.9 / sin_el[tracked]) ** 2)
            fix = solve_pvt(sats.subset(tracked), pr[tracked], sigma, sow,
                            self._x_prev[i], (rc.lat, rc.lon))
        lines: list[str] = []
        tr_set = set(tracked.tolist())
        view = [(int(sats.prn[j]), el[j], az[j], cn0[j] if j in tr_set else None)
                for j in np.argsort(-el) if el[j] > 0]
        info = {"tracked": int(len(tracked)), "fix": fix is not None}
        if fix is not None:
            x, _b, (pdop, hdop, vdop) = fix
            self._x_prev[i] = x
            lat, lon, h = ecef_to_geodetic(x)
            enu = enu_matrix(rc.lat, rc.lon) @ (x - rx)
            info.update(err_enu=enu.tolist(), hdop=hdop, lat=lat, lon=lon, alt=h)
            speed = abs(self.rng.normal(0, 0.12))
            lines.append(nmea.gga(t_utc, lat, lon, h - cfg.geoid_sep_m, 1, len(tracked),
                                  hdop, cfg.geoid_sep_m, cfg.nmea_decimals))
            lines.append(nmea.gsa(3, [int(sats.prn[j]) for j in tracked], pdop, hdop, vdop))
            lines += nmea.gsv(view)
            lines.append(nmea.rmc(t_utc, lat, lon, speed, float(self.rng.uniform(0, 360)),
                                  True, cfg.nmea_decimals))
        else:
            lines.append(nmea.gga(t_utc, 0, 0, 0, 0, 0, 99.99))
            lines.append(nmea.gsa(1, [], 99.9, 99.9, 99.9))
            lines += nmea.gsv([(p, e, a, None) for p, e, a, _ in view])
            lines.append(nmea.rmc(t_utc, 0, 0, 0, 0, False))
        self.last[rc.name] = info
        return lines
