import sys
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import acquisition as acq
from app.services import gnsssdr, sdr

FIND = """[INFO] [UHD] linux; GNU C++ version 15.2.0; UHD_4.9.0.1
--------------------------------------------------
-- UHD Device 0
--------------------------------------------------
Device Address:
    serial: 31A1B2C
    addr: 192.168.10.2
    name:
    product: X310
    type: x300
"""
PROBE = """  _____________________________________________________
 /
|       Device: X300 Device
|     _____________________________________________________
|    /
|   |       Mboard: X310
|   |   serial: 31A1B2C
|   |   product: 30818
|   |   RX Dboard: A
|   |   |   RX Frontend: 0
|   |   |   Freq range: 0.000 to 6000.000 MHz
|   |   |   Gain range PGA: 0.0 to 31.5 step 0.5 dB
|   |   RX Dboard: B
"""
RTL = """Found 1 device(s):
  0:  Realtek, RTL2838UHIDIR, SN: 00000001

Using device 0: Generic RTL2832U OEM
Found Rafael Micro R820T tuner
Supported gain values (29): 0.0 0.9 1.4
"""


def fake(rc, txt):
    return lambda argv, timeout: (rc, txt)


def test_device_args_validation():
    assert sdr.device_args("addr=192.168.10.2") == ["--args=addr=192.168.10.2"]
    assert sdr.device_args("") == []
    for bad in ("addr=1.2.3.4;rm -rf", "foo=bar", "type=zzz", "addr", "serial=a b"):
        with pytest.raises(ValueError):
            sdr.device_args(bad)


def test_tools_status():
    have = {"uhd_find_devices": "/usr/bin/uhd_find_devices", "uhd_usrp_probe": "/x"}
    r = sdr.tools_status(which=have.get, runner=fake(0, "UHD_4.9.0.1-1"))
    assert r["tools"]["uhd_find_devices"]["version"] == "4.9.0.1"
    assert r["ready"] == {"usrp": True, "rtlsdr": False, "gnsssdr": False}
    assert len(r["hints"]) == 2


def test_ping():
    ok = sdr.ping("192.168.10.2", runner=fake(0, "3 packets transmitted, 3 received, 0% packet loss\nrtt min/avg/max/mdev = 0.1/0.25/0.4/0.1 ms"))
    assert ok["ok"] and ok["received"] == 3 and ok["rtt_ms"] == 0.25
    bad = sdr.ping("192.168.10.2", runner=fake(1, "3 packets transmitted, 0 received, 100% packet loss"))
    assert not bad["ok"] and "subred" in bad["message"]
    assert not sdr.ping("-f; ls")["ok"]  # no es una IP: no llega a ejecutarse


def test_usb():
    out = sdr.usb_devices(runner=fake(0, "Bus 001 Device 004: ID 0bda:2838 Realtek RTL2838 DVB-T\nBus 002 Device 002: ID 2500:0020 Ettus B200\nBus 001 Device 001: ID 1d6b:0002 hub"))
    assert [d["kind"] for d in out["devices"]] == ["rtlsdr", "usrp"] and out["ok"]
    assert not sdr.usb_devices(runner=fake(0, "ID 1d6b:0002 hub"))["ok"]


def test_find_and_probe_usrp():
    r = sdr.find_devices("addr=192.168.10.2", runner=fake(0, FIND))
    assert r["ok"] and r["devices"][0]["serial"] == "31A1B2C" and r["devices"][0]["product"] == "X310"
    assert not sdr.find_devices("", runner=fake(0, "No UHD Devices Found"))["ok"]
    assert not sdr.find_devices("evil=1")["ok"]
    p = sdr.probe_usrp("addr=192.168.10.2", runner=fake(0, PROBE))
    assert p["ok"] and p["rx_channels"] == 2 and p["gain_db"] == [0.0, 31.5] and p["freq_mhz"][1] == 6000.0
    narrow = PROBE.replace("0.000 to 6000.000", "50.000 to 860.000")
    assert not sdr.probe_usrp("", runner=fake(0, narrow))["ok"]


def test_rtl():
    r = sdr.rtl_find(0, runner=fake(0, RTL))
    assert r["ok"] and r["tuner"] == "Rafael Micro R820T"
    assert "No hay" in sdr.rtl_find(0, runner=fake(1, "No supported devices found."))["message"]
    assert "udev" in sdr.rtl_find(0, runner=fake(1, "usb_open error -3\nPlease fix the device permissions"))["message"]
    assert "blacklist" in sdr.rtl_find(0, runner=fake(1, "usb_claim_interface error -6\nFailed to open rtlsdr device"))["message"]


def test_iq_metrics_and_judge():
    rng = np.random.default_rng(0)
    n = 1 << 16
    noise = (rng.normal(0, 0.1, n) + 1j * rng.normal(0, 0.1, n)).astype(np.complex64)
    m = sdr.iq_metrics(noise, 2.048e6)
    assert -22 < m["power_dbfs"] < -14 and m["clip_pct"] == 0 and m["peak_over_floor_db"] < 15
    assert sdr.judge_capture(m)["ok"]
    sat = np.clip(noise * 20, -1, 1)
    assert not sdr.judge_capture(sdr.iq_metrics(sat, 2.048e6))["ok"]
    weak = noise * 1e-4
    assert not sdr.judge_capture(sdr.iq_metrics(weak, 2.048e6))["ok"]
    tone = noise + 0.3 * np.exp(2j * np.pi * 0.2 * np.arange(n))
    assert sdr.iq_metrics(tone.astype(np.complex64), 2.048e6)["peak_over_floor_db"] > 25


def test_capture_check_usrp_with_fake_runner():
    rng = np.random.default_rng(1)

    def runner(argv, timeout):
        assert argv[0] == "rx_samples_to_file" and "--freq" in argv
        path = argv[argv.index("--file") + 1]
        x = (rng.normal(0, 3000, 2 * 100_000)).astype(np.int16)
        x.tofile(path)
        return 0, ""

    r = sdr.capture_check("usrp", args="addr=192.168.10.2", fs=2e6, seconds=0.5, runner=runner)
    assert r["ok"] and r["stage"] == "ok" and len(r["spectrum"]["db"]) > 100
    assert not sdr.capture_check("usrp", args="x=1", runner=runner)["ok"]
    assert not sdr.capture_check("rtlsdr", runner=fake(127, "no"))["ok"]


def test_build_conf():
    c = gnsssdr.GnssSdrConfig(source="usrp", device_args="addr=192.168.10.2", nmea_path="/t/n.nmea")
    t = gnsssdr.build_conf(c)
    assert "UHD_Signal_Source" in t and "device_address=192.168.10.2" in t
    assert "freq=1575420000" in t and "PVT.nmea_dump_filename=/t/n.nmea" in t
    assert "Osmosdr_Signal_Source" in gnsssdr.build_conf(gnsssdr.GnssSdrConfig(source="rtlsdr"))
    f = gnsssdr.build_conf(gnsssdr.GnssSdrConfig(source="file", file_path="/d/x.dat", sample_type="byte"))
    assert "File_Signal_Source" in f and "item_type=byte" in f
    with pytest.raises(ValueError):
        gnsssdr.build_conf(gnsssdr.GnssSdrConfig(source="file"))
    with pytest.raises(ValueError):
        gnsssdr.build_conf(gnsssdr.GnssSdrConfig(source="usrp", antenna="RX2\nPVT.x=1"))


def test_state_parsing():
    st = gnsssdr.GnssSdrState()
    st.feed("Tracking of GPS L1 C/A signal started on channel 0 for satellite GPS PRN 07 (Block IIF)")
    st.feed("Tracking of GPS L1 C/A signal started on channel 1 for satellite GPS PRN 12 (Block IIR)")
    st.feed("New GPS NAV message received in channel 0: subframe 1 from satellite GPS PRN 07 (Block IIF)")
    st.feed("Loss of lock in channel 1!")
    st.feed("Position at 2026-Nov-24 12:00:01.000000 UTC using 6 observations is Lat = -12.0464 [deg], Long = -77.0428 [deg], Height= 150.2 [m]")
    s = st.summary()
    assert s["tracking"] == [7] and s["acquired"] == [7, 12] and s["nav_decoded"] == [7]
    assert s["fix"]["nsats"] == 6 and s["fix"]["lat"] == -12.0464


FAKE_GNSSSDR = r'''
import sys, time, re
conf = open(sys.argv[1].split("=",1)[1]).read()
path = re.search(r"PVT.nmea_dump_filename=(.*)", conf).group(1)
print("Tracking of GPS L1 C/A signal started on channel 0 for satellite GPS PRN 05 (Block IIF)", flush=True)
with open(path, "a") as f:
    for i in range(3):
        f.write("$GPGGA,120000.00,1202.7840,S,07702.5680,W,1,06,1.2,150.0,M,0.0,M,,*00\n"); f.flush()
        time.sleep(0.2)
'''


def test_process_pipes_nmea_into_channel(tmp_path):
    import subprocess
    script = tmp_path / "fake.py"
    script.write_text(FAKE_GNSSSDR)
    got = []

    def popen(argv, **kw):
        return subprocess.Popen([sys.executable, str(script), argv[1]], **kw)

    p = gnsssdr.GnssSdrProcess(gnsssdr.GnssSdrConfig(source="rtlsdr"), tmp_path / "w", got.append, popen=popen)
    p.start()
    for _ in range(50):
        if len(got) >= 3 and not p.running:
            break
        time.sleep(0.1)
    p.stop()
    assert len(got) == 3 and got[0].startswith("$GPGGA")
    assert p.state.summary()["tracking"] == [5]
    assert (tmp_path / "w" / "gnss-sdr.conf").exists()


def test_session_sdr_ends_when_processes_end(tmp_path):
    import subprocess
    script = tmp_path / "fake.py"
    script.write_text(FAKE_GNSSSDR)

    def popen(argv, **kw):
        return subprocess.Popen([sys.executable, str(script), argv[1]], **kw)

    s = acq.AcquisitionSession("sdr", ["ref", "rover"], out_dir=tmp_path)
    s.start_sdr({k: gnsssdr.GnssSdrConfig(source="rtlsdr") for k in ("ref", "rover")}, popen=popen)
    for _ in range(80):
        if s.state == "finished":
            break
        time.sleep(0.1)
    assert s.state == "finished"
    assert s.channels["ref"].lines == 3 and s.channels["rover"].lines == 3
    assert (s.dir / "ref.nmea").read_text().count("$GPGGA") == 3
    assert s.status()["sdr"]["ref"]["tracking"] == [5]


def test_api_endpoints(monkeypatch):
    c = TestClient(app)
    assert "ready" in c.get("/api/sdr/tools").json()
    monkeypatch.setattr(sdr, "_run", fake(0, FIND))
    assert c.post("/api/sdr/ping", json={"ip": "-f"}).json()["ok"] is False
    assert c.post("/api/sdr/find", json={"kind": "usrp", "args": "bad=1"}).json()["ok"] is False
    assert c.post("/api/gps/sessions", json={"mode": "sdr"}).status_code == 422
    r = c.post("/api/gps/sessions", json={"mode": "sdr", "sdr_ref": {"source": "file", "file_path": "/no/existe"},
                                          "sdr_rover": {"source": "file", "file_path": "/no/existe"}})
    assert r.status_code == 422 and "no existe" in r.json()["detail"]
