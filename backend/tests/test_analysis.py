import datetime as dt

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import analysis
from app.services import acquisition as acq
from app.services import dgps, report, stats

T0 = dt.datetime(2026, 11, 3, 15, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    out = tmp_path_factory.mktemp("sessions")
    cfg = acq.default_sim_config(start=T0, seed=3)
    s = acq.AcquisitionSession("sim", ["ref", "rover"], out_dir=out)
    s.start_sim(cfg, 1800, speed=0)
    for t in s._threads:
        t.join(timeout=120)
    return s, out


def test_metrics_known_values():
    rng = np.random.default_rng(0)
    e = np.column_stack([rng.normal(0, 1, 20000), rng.normal(0, 1, 20000), np.zeros(20000)])
    m = stats.horizontal_metrics(e)
    assert abs(m["cep50"] - 1.1774) < 0.03          # CEP50 = 1.1774 σ (Rayleigh)
    assert abs(m["2drms"] - 2 * np.sqrt(2)) < 0.05
    assert abs(m["cep95"] - 2.4477) < 0.06
    assert stats.improvement({"cep50": 2, "rmse_h": 2, "cep95": 2, "2drms": 2},
                             {"cep50": 1, "rmse_h": 1, "cep95": 1, "2drms": 1})["cep50"] == 50


def test_block_bootstrap_keeps_length_and_ci_contains_estimate():
    rng = np.random.default_rng(1)
    x = np.cumsum(rng.normal(0, .1, (600, 3)), axis=0)
    idx = stats.block_bootstrap_indices(600, 25, np.random.default_rng(0))
    assert len(idx) == 600
    out = stats.bootstrap_ci(x, x * 0.5, block=25, n_boot=200)
    lo, hi = out["ci"]["imp_cep50"]
    assert lo <= 50 + 1e-6 and hi >= 50 - 1e-6   # mejora exacta del 50 % en cada remuestreo


def test_differential_improves_and_filters_sats(session):
    s, out = session
    ref, rov, meta = dgps.load_session(s.dir)
    truth = dgps.truth_from_meta(meta)
    res = dgps.analyze(ref, rov, ref_known=truth["ref"], rover_truth=truth["rover"], n_boot=100)
    assert res["accuracy"]
    assert 0 < res["epochs"]["same_sats_pct"] < 100 and res["epochs"]["discarded"] > 0
    assert res["after"]["cep50"] < 0.75 * res["before"]["cep50"]
    assert res["improvement"]["cep50"] > 25
    assert abs(res["baseline"]["true_len"] - 3.0) < 0.05
    assert res["baseline"]["dgps_len_err_rmse"] < res["baseline"]["raw_len_err_rmse"]


def test_precision_only_when_no_rover_truth(session):
    s, _ = session
    ref, rov, meta = dgps.load_session(s.dir)
    res = dgps.analyze(ref, rov, ref_known=dgps.truth_from_meta(meta)["ref"], n_boot=0)
    assert res["accuracy"] is False and res["before"]["bias_h"] < 1e-6


def test_wrong_ref_position_does_not_help(session):
    """Una referencia mal ubicada introduce un sesgo: el diferencial NO debe verse mágicamente perfecto."""
    s, _ = session
    ref, rov, meta = dgps.load_session(s.dir)
    t = dgps.truth_from_meta(meta)
    bad = (t["ref"][0] + 5e-5, t["ref"][1], t["ref"][2])  # ~5.5 m al norte
    res = dgps.analyze(ref, rov, ref_known=bad, rover_truth=t["rover"], n_boot=0)
    assert res["after"]["bias_h"] > 4.0


def test_api_run_export_and_pdf(session, monkeypatch):
    s, out = session
    monkeypatch.setattr(acq, "SESSIONS_DIR", out)
    c = TestClient(app)
    r = c.post("/api/analysis/run", json={"session_id": s.id, "n_boot": 50})
    assert r.status_code == 200, r.text
    assert r.json()["improvement"]["cep50"] > 25
    assert c.post("/api/analysis/run", json={"session_id": "../x"}).status_code == 404
    exp = c.get("/api/analysis/experiments").json()
    assert exp[0]["summary"]["cep50_after"] < exp[0]["summary"]["cep50_before"]
    assert c.get(f"/api/analysis/sessions/{s.id}/export?fmt=csv").text.startswith("t_s,")
    pdf = c.get(f"/api/reports/sessions/{s.id}.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_api_upload_real_style_files(session):
    s, _ = session
    c = TestClient(app)
    ref = (s.dir / "ref.nmea").read_bytes()
    rov = (s.dir / "rover.nmea").read_bytes()
    import json
    meta = json.loads((s.dir / "meta.json").read_text())
    r0 = meta["sim"]["receivers"][0]
    r = c.post("/api/analysis/upload", files={"ref_file": ("r.nmea", ref), "rover_file": ("m.nmea", rov)},
               data={"ref_lat": r0["lat"], "ref_lon": r0["lon"], "ref_h": r0["alt"], "n_boot": 20})
    assert r.status_code == 200, r.text
    assert r.json()["accuracy"] is False
    r = c.post("/api/analysis/upload", files={"ref_file": ("r.nmea", b""), "rover_file": ("m.nmea", b"")},
               data={"ref_lat": 0, "ref_lon": 0, "ref_h": 0})
    assert r.status_code == 422
