"""Métricas de error de posicionamiento y bootstrap por bloques.

Todas las funciones reciben errores ENU en metros respecto a una verdad
(shape (N, 3): este, norte, arriba).
"""
from __future__ import annotations

import numpy as np

METRIC_KEYS = ("rmse_h", "cep50", "cep95", "2drms")


def horizontal_metrics(err_enu: np.ndarray) -> dict:
    """RMSE, CEP50/95 empíricos, 2DRMS, sesgo y desviación de un conjunto de errores."""
    e = np.asarray(err_enu, dtype=float)
    if len(e) == 0:
        return {"n": 0}
    r = np.hypot(e[:, 0], e[:, 1])
    mean = e.mean(axis=0)
    std = e.std(axis=0, ddof=1) if len(e) > 1 else np.zeros(3)
    rmse_h = float(np.sqrt(np.mean(r ** 2)))
    rp = np.hypot(e[:, 0] - mean[0], e[:, 1] - mean[1])
    return {
        "n": int(len(e)),
        "rmse_h": rmse_h,
        "rmse_v": float(np.sqrt(np.mean(e[:, 2] ** 2))),
        "rmse_3d": float(np.sqrt(np.mean(r ** 2 + e[:, 2] ** 2))),
        "cep50": float(np.percentile(r, 50)),
        "cep95": float(np.percentile(r, 95)),
        "2drms": 2.0 * rmse_h,
        "max_h": float(r.max()),
        "bias_e": float(mean[0]), "bias_n": float(mean[1]), "bias_u": float(mean[2]),
        "bias_h": float(np.hypot(mean[0], mean[1])),
        "std_e": float(std[0]), "std_n": float(std[1]), "std_u": float(std[2]),
        # precisión (dispersión alrededor de la propia media), independiente del sesgo
        "cep50_prec": float(np.percentile(rp, 50)),
        "cep95_prec": float(np.percentile(rp, 95)),
    }


def improvement(before: dict, after: dict) -> dict:
    """% de mejora (positivo = el diferencial reduce el error)."""
    out = {}
    for k in METRIC_KEYS + ("rmse_v",):
        b, a = before.get(k), after.get(k)
        out[k] = None if not b else 100.0 * (b - a) / b
    return out


def lag1_autocorr(x: np.ndarray) -> float:
    x = np.asarray(x, float)
    x = x - x.mean()
    d = float(np.dot(x, x))
    return float(np.dot(x[:-1], x[1:]) / d) if d > 0 and len(x) > 2 else 0.0


def default_block_len(err_enu: np.ndarray) -> int:
    """Longitud de bloque ~ tiempo de decorrelación (primer cruce de la ACF por 1/e), acotada."""
    e = np.asarray(err_enu, float)
    n = len(e)
    if n < 20:
        return 1
    best = 1
    cap = min(n // 4, 600)
    for ax in (0, 1):
        x = e[:, ax] - e[:, ax].mean()
        d = float(np.dot(x, x))
        if d == 0:
            continue
        lag = next((k for k in range(1, cap) if np.dot(x[:-k], x[k:]) / d < 1 / np.e), cap)
        best = max(best, lag)
    return int(min(max(best, 2), max(2, n // 5)))


def block_bootstrap_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Bootstrap circular por bloques: conserva la correlación temporal dentro de cada bloque."""
    nb = -(-n // block)
    starts = rng.integers(0, n, nb)
    idx = (starts[:, None] + np.arange(block)[None, :]) % n
    return idx.ravel()[:n]


def bootstrap_ci(before_enu: np.ndarray, after_enu: np.ndarray, *, block: int | None = None,
                 n_boot: int = 1000, seed: int = 0, level: float = 0.95) -> dict:
    """IC por bootstrap de bloques *pareado* (mismas épocas antes/después) para
    las métricas de cada caso y para el % de mejora."""
    b = np.asarray(before_enu, float)
    a = np.asarray(after_enu, float)
    n = len(b)
    if n < 10 or n_boot < 1:
        return {"block": 1, "n_boot": 0, "ci": {}}
    block = block or default_block_len(b)
    rng = np.random.default_rng(seed)
    acc = {f"{c}_{k}": [] for c in ("before", "after") for k in METRIC_KEYS}
    acc.update({f"imp_{k}": [] for k in METRIC_KEYS})
    for _ in range(n_boot):
        idx = block_bootstrap_indices(n, block, rng)
        mb, ma = horizontal_metrics(b[idx]), horizontal_metrics(a[idx])
        for k in METRIC_KEYS:
            acc[f"before_{k}"].append(mb[k])
            acc[f"after_{k}"].append(ma[k])
            acc[f"imp_{k}"].append(100.0 * (mb[k] - ma[k]) / mb[k] if mb[k] else np.nan)
    lo, hi = 100 * (1 - level) / 2, 100 * (1 + level) / 2
    ci = {k: [float(np.nanpercentile(v, lo)), float(np.nanpercentile(v, hi))] for k, v in acc.items()}
    return {"block": int(block), "n_boot": n_boot, "level": level, "ci": ci}
