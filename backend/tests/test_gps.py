import datetime as dt
import time

import numpy as np
import pytest
from pyproj import Transformer

from app.services import acquisition as acq
from app.services import nmea
from app.services.constellation import parse_yuma, positions_ecef, synthetic_constellation
from app.services.geo import azel, ecef_to_geodetic, geodetic_to_ecef

T0 = dt.datetime(2026, 11, 3, 15, 0, tzinfo=dt.timezone.utc)


def test_geodesy_matches_pyproj():
    tr = Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    for lat, lon, h in [(-12.05, -77.04, 150.0), (45.0, 10.0, 2000.0), (0.0, 179.0, -30.0)]:
        ours = geodetic_to_ecef(lat, lon, h)
        ref = np.array(tr.transform(lon, lat, h))
        assert np.linalg.norm(ours - ref) < 1e-3
        la, lo, hh = ecef_to_geodetic(ours)
        assert abs(la - lat) < 1e-9 and abs(lo - lon) < 1e-9 and abs(hh - h) < 1e-4


def test_orbit_radius_and_visibility():
    sats = synthetic_constellation()
    p = positions_ecef(sats, 12345.0)
    r = np.linalg.norm(p, axis=1)
    assert np.all((r > 26.2e6) & (r < 26.9e6))
    rx = geodetic_to_ecef(-12.05, -77.04, 150)
    _, el = azel(rx, p, -12.05, -77.04)
    assert 6 <= np.sum(el > 10) <= 14


def test_yuma_parser():
    txt = """******** Week 100 almanac for PRN-05 ********
ID:                         05
Health:                     000
Eccentricity:               0.5E-002
Time of Applicability(s):  319488.0000
Orbital Inclination(rad):   0.9700000000
Rate of Right Ascen(r/s):  -0.7900000000E-008
SQRT(A)  (m 1/2):           5153.600000
Right Ascen at Week(rad):   1.0000000000
Argument of Perigee(rad):   0.5000000000
Mean Anom(rad):             0.2000000000
Af0(s):                     0.0
Af1(s/s):                   0.0
week:                        100
"""
    s = parse_yuma(txt)
    assert len(s) == 1 and s.prn[0] == 5
    assert abs(s.a[0] - 5153.6 ** 2) < 1


def test_nmea_checksum_and_roundtrip():
    assert nmea.checksum("GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,") == "47"
    lines = [nmea.gga(T0, -12.0464, -77.0428, 150.2, 1, 9, 1.1, 0.0),
             nmea.gsa(3, [1, 5, 7, 9], 1.8, 1.1, 1.4),
             *nmea.gsv([(1, 50, 120, 44), (5, 10, 300, None)]),
             nmea.rmc(T0, -12.0464, -77.0428, 0.1, 90, True)]
    asm = nmea.EpochAssembler()
    assert all(asm.feed(l) is None for l in lines)
    e = asm.flush()
    assert abs(e.lat + 12.0464) < 2e-6 and abs(e.lon + 77.0428) < 2e-6  # cuantización 1e-4 min
    assert e.nsats == 9 and e.sats_used == ["GP01", "GP05", "GP07", "GP09"]
    assert [s.id for s in e.sats_view] == ["GP01", "GP05"] and e.sats_view[1].snr is None
    assert e.utc == T0 and e.valid


def test_bad_checksum_is_counted_not_fatal():
    asm = nmea.EpochAssembler()
    good = nmea.gga(T0, -12.0, -77.0, 100, 1, 8, 1.0)
    asm.feed(good[:-2] + "00")
    asm.feed("basura")
    assert asm.bad_lines == 1


def _run(duration=900, **kw):
    cfg = acq.default_sim_config(start=T0, seed=3, **kw)
    s = acq.AcquisitionSession("sim", ["ref", "rover"], out_dir=pytest.tmp_path)
    s.start_sim(cfg, duration, speed=0)
    for t in s._threads:
        t.join(timeout=120)
    return s


@pytest.fixture(autouse=True)
def _tmp(tmp_path):
    pytest.tmp_path = tmp_path


def test_sim_statistics_are_plausible():
    s = _run()
    assert s.state == "finished" and not s.error
    for rx in ("ref", "rover"):
        eps = [e for e in s.channels[rx].epochs if e["quality"] == 1]
        assert len(eps) > 800
        assert 7 <= np.mean([e["nsats"] for e in eps]) <= 12
        assert 0.6 < np.mean([e["hdop"] for e in eps]) < 2.5
    sim_err = np.array([s.sim.last[rx]["err_enu"] for rx in ("ref", "rover")])
    assert np.all(np.abs(sim_err[:, :2]) < 15)  # error horizontal de metros, no de km


def test_replaying_the_log_gives_same_epochs():
    """Intercambiabilidad sim/real: el log .nmea escrito reproduce las mismas épocas."""
    s = _run(duration=120)
    r = acq.AcquisitionSession("sim", ["ref", "rover"], out_dir=pytest.tmp_path / "replay")
    r.start_replay({rx: s.dir / f"{rx}.nmea" for rx in ("ref", "rover")})
    for t in r._threads:
        t.join(timeout=30)
    for rx in ("ref", "rover"):
        a, b = s.channels[rx].epochs, r.channels[rx].epochs
        assert len(a) == len(b) > 100
        assert [x["lat"] for x in a] == [x["lat"] for x in b]
        assert [x["sats_used"] for x in a] == [x["sats_used"] for x in b]


def test_errors_are_common_mode_and_differential_helps():
    """Corrección en dominio de posición con épocas de mismo conjunto de satélites."""
    s = _run(duration=1800)
    ref = {e["utc"]: e for e in s.channels["ref"].epochs if e["quality"] == 1}
    rov = {e["utc"]: e for e in s.channels["rover"].epochs if e["quality"] == 1}
    keys = [k for k in ref if k in rov]
    same = [k for k in keys if set(ref[k]["sats_used"]) == set(rov[k]["sats_used"])]
    assert len(same) > 0.3 * len(keys)  # mismo conjunto es frecuente pero no universal
    truth_ref = s.sim.truth_ecef[0]
    truth_rov = s.sim.truth_ecef[1]
    from app.services.geo import enu_matrix
    R = enu_matrix(-12.0464, -77.0428)

    def enu(e, truth):
        return (R @ (geodetic_to_ecef(e["lat"], e["lon"], e["alt"]) - truth))[:2]

    raw = np.array([enu(rov[k], truth_rov) for k in same])
    corr = np.array([enu(rov[k], truth_rov) - enu(ref[k], truth_ref) for k in same])
    cep = lambda a: np.median(np.hypot(a[:, 0], a[:, 1]))
    assert cep(corr) < 0.75 * cep(raw)
