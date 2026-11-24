"""GNSS-SDR: genera la configuración, lanza el proceso y entrega su NMEA al pipeline.

    SDR (UHD / rtl_tcp-osmosdr) o archivo IQ -> gnss-sdr -> NMEA (archivo) -> tail
        -> ReceiverChannel.ingest()   (mismo destino que serial_reader)

Un proceso por receptor (ref y rover). Solo recepción.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import sdr

SOURCES = ("usrp", "rtlsdr", "file")


@dataclass
class GnssSdrConfig:
    source: str = "usrp"          # usrp | rtlsdr | file
    fs: float = 2.0e6             # sample rate de procesamiento
    gain: float = 40.0
    device_args: str = ""         # UHD: 'addr=192.168.10.2' / 'serial=...' (opcional)
    rtl_index: int = 0
    antenna: str = "RX2"          # puerto UHD (RX2 en B2xx; TX/RX no)
    subdevice: str = ""           # UHD: 'A:A', 'A:B' (B210 con 2 canales)
    file_path: str = ""           # source == file
    sample_type: str = "ishort"   # file: ishort (sc16) | byte (rtl uint8) | gr_complex
    pvt_rate_ms: int = 1000
    nmea_path: str = "nmea.log"
    channels: int = 8
    extra: dict[str, str] = field(default_factory=dict)


def build_conf(c: GnssSdrConfig) -> str:
    """Texto del .conf de GNSS-SDR (GPS L1 C/A, PVT con salida NMEA a archivo)."""
    if c.source not in SOURCES:
        raise ValueError(f"Fuente desconocida: {c.source!r}")
    if not 0.5e6 <= c.fs <= 10e6:
        raise ValueError("fs fuera de rango (0.5–10 MS/s)")
    if not 1 <= c.channels <= 12:
        raise ValueError("channels fuera de rango (1–12)")
    # Se evita cualquier salto de línea en valores de usuario (inyección de claves)
    for v in (c.device_args, c.antenna, c.subdevice, c.file_path, c.nmea_path, c.sample_type):
        if "\n" in v or "\r" in v:
            raise ValueError("Valor de configuración inválido")
    L = ["; Generado por TwoMice-DGPS. Solo recepción.", "[GNSS-SDR]",
         f"GNSS-SDR.internal_fs_sps={int(c.fs)}", ""]
    if c.source == "usrp":
        sdr.device_args(c.device_args)  # valida claves y valores
        kv = dict(p.split("=", 1) for p in c.device_args.strip().split(",") if "=" in p)
        L += ["SignalSource.implementation=UHD_Signal_Source",
              f"SignalSource.device_address={kv.get('addr', '')}",
              "SignalSource.item_type=gr_complex",
              f"SignalSource.sampling_frequency={int(c.fs)}",
              f"SignalSource.freq={int(sdr.L1_HZ)}",
              f"SignalSource.gain={c.gain}",
              "SignalSource.RF_channels=1",
              "SignalSource.dump=false"]
        if c.subdevice:
            L.append(f"SignalSource.subdevice={c.subdevice}")
        if "serial" in kv:
            L.append(f"SignalSource.device_serial={kv['serial']}")
        L.append(f"SignalSource.antenna={c.antenna}")
    elif c.source == "rtlsdr":
        L += ["SignalSource.implementation=Osmosdr_Signal_Source",
              f"SignalSource.osmosdr_args=rtl={int(c.rtl_index)}",
              "SignalSource.item_type=gr_complex",
              f"SignalSource.sampling_frequency={int(c.fs)}",
              f"SignalSource.freq={int(sdr.L1_HZ)}",
              "SignalSource.AGC_enabled=false",
              f"SignalSource.gain={c.gain}",
              "SignalSource.dump=false"]
    else:
        if not c.file_path:
            raise ValueError("Falta file_path")
        L += ["SignalSource.implementation=File_Signal_Source",
              f"SignalSource.filename={c.file_path}",
              f"SignalSource.item_type={c.sample_type}",
              f"SignalSource.sampling_frequency={int(c.fs)}",
              "SignalSource.repeat=false",
              "SignalSource.dump=false"]
        if c.sample_type == "byte":
            L.append("SignalSource.enable_throttle_control=false")
    L += ["",
          "SignalConditioner.implementation=Signal_Conditioner",
          "DataTypeAdapter.implementation=Pass_Through",
          "InputFilter.implementation=Pass_Through",
          "Resampler.implementation=Pass_Through",
          "",
          f"Channels_1C.count={c.channels}",
          f"Channels.in_acquisition={c.channels}",
          "Channel.signal=1C",
          "",
          "Acquisition_1C.implementation=GPS_L1_CA_PCPS_Acquisition",
          "Acquisition_1C.item_type=gr_complex",
          "Acquisition_1C.coherent_integration_time_ms=1",
          "Acquisition_1C.threshold=0.008",
          "Acquisition_1C.doppler_max=10000",
          "Acquisition_1C.doppler_step=250",
          "",
          "Tracking_1C.implementation=GPS_L1_CA_DLL_PLL_Tracking",
          "Tracking_1C.item_type=gr_complex",
          "Tracking_1C.pll_bw_hz=40.0",
          "Tracking_1C.dll_bw_hz=4.0",
          "",
          "TelemetryDecoder_1C.implementation=GPS_L1_CA_Telemetry_Decoder",
          "Observables.implementation=Hybrid_Observables",
          "",
          "PVT.implementation=RTKLIB_PVT",
          "PVT.positioning_mode=Single",
          f"PVT.output_rate_ms={c.pvt_rate_ms}",
          f"PVT.display_rate_ms={max(500, c.pvt_rate_ms)}",
          "PVT.flag_nmea_tty_port=false",
          f"PVT.nmea_dump_filename={c.nmea_path}",
          "PVT.flag_nmea_tty_port=false",
          "PVT.flag_rtcm_server=false",
          "PVT.dump=false"]
    for k, v in c.extra.items():
        if not re.fullmatch(r"[\w.\-]+", k) or "\n" in v:
            raise ValueError(f"Clave extra inválida: {k!r}")
        L.append(f"{k}={v}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------- salida de gnss-sdr

_RE_TRACK = re.compile(r"Tracking of GPS L1 C/A signal started on channel (\d+) for satellite GPS PRN (\d+)")
_RE_LOSS = re.compile(r"Loss of lock in channel (\d+)")
_RE_ACQ = re.compile(r"Satellite GPS PRN (\d+) .*?Doppler", re.I)
_RE_NAV = re.compile(r"New GPS NAV message received in channel (\d+): subframe (\d) from satellite GPS PRN (\d+)")
_RE_POS = re.compile(r"Position at (.+?) UTC using (\d+) observations is Lat = ([\-\d.]+) \[deg\], Long = ([\-\d.]+) \[deg\], Height= ([\-\d.]+) \[m\]")
_RE_CN0 = re.compile(r"Current receiver time|C/N0", re.I)


@dataclass
class GnssSdrState:
    tracking: dict[int, int] = field(default_factory=dict)   # canal -> PRN
    acquired: set[int] = field(default_factory=set)
    nav: set[int] = field(default_factory=set)               # PRN con subframes decodificados
    fix: dict | None = None
    log_tail: list[str] = field(default_factory=list)

    def feed(self, line: str):
        line = line.rstrip()
        if not line:
            return
        self.log_tail.append(line)
        del self.log_tail[:-40]
        if (m := _RE_TRACK.search(line)):
            ch, prn = int(m.group(1)), int(m.group(2))
            self.tracking[ch] = prn
            self.acquired.add(prn)
        elif (m := _RE_LOSS.search(line)):
            self.tracking.pop(int(m.group(1)), None)
        elif (m := _RE_NAV.search(line)):
            self.nav.add(int(m.group(3)))
        elif (m := _RE_POS.search(line)):
            self.fix = {"utc": m.group(1), "nsats": int(m.group(2)), "lat": float(m.group(3)),
                        "lon": float(m.group(4)), "alt": float(m.group(5))}

    def summary(self) -> dict:
        return {"tracking": sorted(self.tracking.values()), "acquired": sorted(self.acquired),
                "nav_decoded": sorted(self.nav), "fix": self.fix}


# --------------------------------------------------------------- proceso


class GnssSdrProcess:
    """Lanza `gnss-sdr`, sigue su stdout y hace tail del archivo NMEA hacia `ingest`."""

    def __init__(self, conf: GnssSdrConfig, work_dir: Path, ingest=None, on_error=None, *,
                 popen=subprocess.Popen, binary: str = "gnss-sdr"):
        self.conf = conf
        self.dir = Path(work_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.nmea_path = self.dir / "gnsssdr.nmea"
        self.conf.nmea_path = str(self.nmea_path)
        self.conf_path = self.dir / "gnss-sdr.conf"
        self.ingest = ingest or (lambda line: None)
        self.on_error = on_error or (lambda msg: None)
        self.state = GnssSdrState()
        self.proc = None
        self._popen = popen
        self._binary = binary
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.started_at: float | None = None
        self.returncode: int | None = None

    def start(self):
        self.conf_path.write_text(build_conf(self.conf), encoding="utf-8")
        self.nmea_path.touch()
        self.proc = self._popen(
            [self._binary, f"--config_file={self.conf_path}"], cwd=str(self.dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, shell=False)
        self.started_at = time.time()
        for fn in (self._read_log, self._tail_nmea):
            t = threading.Thread(target=fn, daemon=True)
            self._threads.append(t)
            t.start()

    def _read_log(self):
        try:
            for line in self.proc.stdout:
                self.state.feed(line)
                if self._stop.is_set():
                    break
        except (ValueError, OSError):
            pass
        self.returncode = self.proc.wait()
        if not self._stop.is_set() and self.returncode != 0:
            tail = " | ".join(self.state.log_tail[-3:])
            self.on_error(f"gnss-sdr terminó con código {self.returncode}: {tail}")

    def _tail_nmea(self):
        with open(self.nmea_path, encoding="ascii", errors="ignore") as f:
            buf = ""
            while not self._stop.is_set():
                chunk = f.read()
                if chunk:
                    buf += chunk
                    *lines, buf = buf.split("\n")
                    for ln in lines:
                        if ln.startswith("$"):
                            self.ingest(ln)
                    continue
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self, timeout: float = 5.0):
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for t in self._threads:
            t.join(timeout=2)

    def status(self) -> dict:
        return {"running": self.running, "returncode": self.returncode,
                "elapsed_s": (time.time() - self.started_at) if self.started_at else 0,
                "nmea_bytes": os.path.getsize(self.nmea_path) if self.nmea_path.exists() else 0,
                **self.state.summary(), "log_tail": self.state.log_tail[-8:]}
