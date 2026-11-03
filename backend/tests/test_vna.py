import numpy as np

from app.services.resonance import find_resonances
from app.services.touchstone import parse_s1p


def synthetic_s1p(f0=1575.42, depth_db=-25.0, width=40.0) -> str:
    f = np.linspace(1000, 2000, 1001)  # MHz
    mag_db = -1.0 + (depth_db + 1.0) * np.exp(-((f - f0) / width) ** 2)
    lines = ["! prueba sintética", "# MHz S DB R 50"]
    lines += [f"{a:.3f} {b:.4f} -30.0" for a, b in zip(f, mag_db)]
    return "\n".join(lines)


def test_resonance_found_at_l1():
    sp = parse_s1p(synthetic_s1p())
    res = find_resonances(sp)
    assert len(res) == 1
    r = res[0]
    assert abs(r["freq_mhz"] - 1575.42) < 1.5
    assert r["s11_db"] < -24
    assert r["bw_mhz"] and r["bw_mhz"] > 20
    assert "GPS L1" in r["covers"]


def test_ri_format_and_vswr():
    sp = parse_s1p("# GHz S RI R 50\n1.5 0.0 0.0\n1.6 0.5 0.0\n")
    assert abs(sp.vswr[0] - 1.0) < 1e-6
    assert abs(sp.vswr[1] - 3.0) < 1e-3  # |Γ|=0.5 -> VSWR=3
    assert abs(sp.impedance[0] - 50) < 1e-6
