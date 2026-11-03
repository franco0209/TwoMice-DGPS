"""Geodesia WGS-84: conversiones geodésicas/ECEF/ENU y acimut/elevación."""
from __future__ import annotations

import numpy as np

A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)


def geodetic_to_ecef(lat_deg, lon_deg, h):
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    return np.array([
        (n + h) * np.cos(lat) * np.cos(lon),
        (n + h) * np.cos(lat) * np.sin(lon),
        (n * (1 - E2) + h) * np.sin(lat),
    ])


def ecef_to_geodetic(xyz):
    """Devuelve (lat_deg, lon_deg, h). Iterativo, converge en <5 pasos."""
    x, y, z = xyz
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - E2))
    for _ in range(6):
        n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - E2 * n / (n + h)))
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    h = p / np.cos(lat) - n
    return float(np.degrees(lat)), float(np.degrees(lon)), float(h)


def enu_matrix(lat_deg, lon_deg):
    """Matriz R tal que enu = R @ (ecef - ecef_ref)."""
    lat, lon = np.radians(lat_deg), np.radians(lon_deg)
    sl, cl, so, co = np.sin(lat), np.cos(lat), np.sin(lon), np.cos(lon)
    return np.array([
        [-so, co, 0.0],
        [-sl * co, -sl * so, cl],
        [cl * co, cl * so, sl],
    ])


def azel(rx_ecef, sat_ecef, lat_deg, lon_deg):
    """Acimut [0,360) y elevación (grados) de satélites (N,3) vistos desde rx."""
    enu = (enu_matrix(lat_deg, lon_deg) @ (np.atleast_2d(sat_ecef) - rx_ecef).T).T
    e, n, u = enu[:, 0], enu[:, 1], enu[:, 2]
    az = np.degrees(np.arctan2(e, n)) % 360.0
    el = np.degrees(np.arctan2(u, np.hypot(e, n)))
    return az, el
