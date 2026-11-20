"""Diferencial en el dominio de la posición (a partir de NMEA).

Para cada época con fix en ambos receptores:
    Δ = posición_conocida_ref − posición_medida_ref      (en ENU)
    rover_corregido = rover_medido + Δ
La corrección solo es válida si ambos receptores usaron el MISMO conjunto de
satélites (errores comunes). Las demás épocas se descartan y se cuentan.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

from . import nmea, stats
from .geo import enu_matrix, geodetic_to_ecef


class AnalysisError(ValueError):
    pass


def parse_nmea_text(text: str) -> list[dict]:
    asm = nmea.EpochAssembler()
    out = []
    for line in text.splitlines():
        ep = asm.feed(line)
        if ep is not None:
            out.append(ep.to_dict())
    ep = asm.flush()
    if ep is not None:
        out.append(ep.to_dict())
    return out


def load_session(session_dir: Path) -> tuple[list[dict], list[dict], dict]:
    meta_p = session_dir / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    try:
        ref = parse_nmea_text((session_dir / "ref.nmea").read_text(encoding="ascii", errors="ignore"))
        rov = parse_nmea_text((session_dir / "rover.nmea").read_text(encoding="ascii", errors="ignore"))
    except FileNotFoundError as e:
        raise AnalysisError(f"Falta el archivo {Path(e.filename).name}") from e
    return ref, rov, meta


def truth_from_meta(meta: dict) -> dict[str, tuple[float, float, float]]:
    """En simulación la verdad de terreno de ambos receptores está en meta.json
    (lat, lon, altura elipsoidal). En modo real no existe."""
    return {r["name"]: (r["lat"], r["lon"], r["alt"])
            for r in (meta.get("sim") or {}).get("receivers", [])}


def _ts(e: dict) -> float | None:
    if not e.get("utc"):
        return None
    return round(dt.datetime.fromisoformat(e["utc"]).timestamp(), 1)


def _ecef(e: dict) -> np.ndarray:
    h = e["alt"] + (e.get("geoid_sep") or 0.0)  # NMEA da la altura sobre el geoide
    return geodetic_to_ecef(e["lat"], e["lon"], h)


def _index(eps: list[dict]) -> dict[float, dict]:
    return {t: e for e in eps if e["quality"] > 0 and e["lat"] is not None
            and (t := _ts(e)) is not None}


def analyze(ref_eps: list[dict], rov_eps: list[dict], *,
            ref_known: tuple[float, float, float] | None,
            rover_truth: tuple[float, float, float] | None = None,
            block: int | None = None, n_boot: int = 500, seed: int = 0,
            max_series: int = 3000) -> dict:
    """`ref_known`/`rover_truth` = (lat, lon, h_elipsoidal). Si `rover_truth` es None se
    evalúa solo precisión (dispersión respecto a la propia media): el sesgo no es medible."""
    if ref_known is None:
        raise AnalysisError("Se requiere la posición conocida de la referencia")
    ref, rov = _index(ref_eps), _index(rov_eps)
    common_t = sorted(set(ref) & set(rov))
    if not common_t:
        raise AnalysisError("No hay épocas simultáneas con fix en ambos receptores")

    p_ref = geodetic_to_ecef(*ref_known)
    R = enu_matrix(ref_known[0], ref_known[1])

    def to_enu(e):
        return R @ (_ecef(e) - p_ref)

    same_t = [t for t in common_t
              if ref[t]["sats_used"] and set(ref[t]["sats_used"]) == set(rov[t]["sats_used"])]
    if len(same_t) < 10:
        raise AnalysisError(
            f"Solo {len(same_t)} épocas con el mismo conjunto de satélites "
            f"(de {len(common_t)} simultáneas); insuficiente para el diferencial")

    ref_enu = np.array([to_enu(ref[t]) for t in same_t])   # error de la referencia (verdad = origen)
    rov_enu = np.array([to_enu(rov[t]) for t in same_t])   # móvil en el ENU de la referencia
    rov_corr = rov_enu - ref_enu                            # + Δ, con Δ = −error_ref

    accuracy = rover_truth is not None
    rov_true = R @ (geodetic_to_ecef(*rover_truth) - p_ref) if accuracy else rov_enu.mean(axis=0)
    err_before = rov_enu - rov_true
    err_after = rov_corr - rov_true

    m_before, m_after = stats.horizontal_metrics(err_before), stats.horizontal_metrics(err_after)
    # contexto: móvil sin filtrar ni corregir, todas las épocas simultáneas
    m_raw_all = stats.horizontal_metrics(np.array([to_enu(rov[t]) for t in common_t]) - rov_true)

    len_raw = np.linalg.norm(rov_enu[:, :2], axis=1)              # móvil medido − ref conocida (1 receptor)
    len_dgps = np.linalg.norm(rov_corr[:, :2], axis=1)            # móvil corregido − ref conocida = móvil medido − ref medida
    baseline = {
        "raw_len_mean": float(len_raw.mean()), "raw_len_std": float(len_raw.std(ddof=1)),
        "dgps_len_mean": float(len_dgps.mean()), "dgps_len_std": float(len_dgps.std(ddof=1)),
    }
    if accuracy:
        true_len = float(np.linalg.norm(rov_true[:2]))
        baseline["true_len"] = true_len
        baseline["raw_len_err_rmse"] = float(np.sqrt(np.mean((len_raw - true_len) ** 2)))
        baseline["dgps_len_err_rmse"] = float(np.sqrt(np.mean((len_dgps - true_len) ** 2)))

    boot = stats.bootstrap_ci(err_before, err_after, block=block, n_boot=n_boot, seed=seed)
    step = max(1, len(same_t) // max_series)
    sel = slice(None, None, step)
    t0 = same_t[0]
    r_b, r_a = np.hypot(err_before[:, 0], err_before[:, 1]), np.hypot(err_after[:, 0], err_after[:, 1])
    return {
        "accuracy": accuracy,
        "ref_known": list(ref_known),
        "rover_truth": list(rover_truth) if accuracy else None,
        "epochs": {
            "ref_fix": len(ref), "rover_fix": len(rov), "simultaneous": len(common_t),
            "same_sats": len(same_t), "discarded": len(common_t) - len(same_t),
            "same_sats_pct": 100.0 * len(same_t) / len(common_t),
        },
        "before": m_before, "after": m_after, "raw_all": m_raw_all,
        "improvement": stats.improvement(m_before, m_after),
        "baseline": baseline,
        "stability": {
            "lag1_before": stats.lag1_autocorr(r_b), "lag1_after": stats.lag1_autocorr(r_a),
            "ref_error_h_mean": float(np.mean(np.hypot(ref_enu[:, 0], ref_enu[:, 1]))),
        },
        "bootstrap": boot,
        "series": {
            "t_s": [float(t - t0) for t in same_t[sel]],
            "before": err_before[sel].round(3).tolist(),
            "after": err_after[sel].round(3).tolist(),
        },
    }
