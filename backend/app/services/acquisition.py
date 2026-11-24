"""Adquisición de GPS: mismo pipeline para simulación y receptores reales.

    fuente (serie | simulador | archivo)  ->  líneas NMEA
        -> ReceiverChannel.ingest(línea): log crudo .nmea + EpochAssembler
        -> AcquisitionSession: eventos para el WebSocket + meta.json

Los archivos `<rx>.nmea` que escribe una sesión simulada tienen el mismo
formato que los de una sesión real, así que el análisis posterior no
distingue el origen (salvo el `meta.json`, que marca `mode` y guarda la
verdad de terreno solo en simulación).
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from . import nmea
from .constellation import SatArray
from .gnss_sim import GnssSimulator, ReceiverConfig, SimConfig

SESSIONS_DIR = Path(__file__).resolve().parents[3] / "data" / "sessions"


class ReceiverChannel:
    """Un receptor: recibe líneas, las registra y arma épocas."""

    def __init__(self, rx_id: str, log_path: Path | None, on_epoch):
        self.rx_id = rx_id
        self.asm = nmea.EpochAssembler()
        self.on_epoch = on_epoch
        self.epochs: list[dict] = []
        self.last: dict | None = None
        self._log = open(log_path, "w", encoding="ascii", newline="\n") if log_path else None
        self.lines = 0

    def ingest(self, line: str):
        self.lines += 1
        if self._log:
            self._log.write(line.rstrip("\r\n") + "\n")
        ep = self.asm.feed(line)
        if ep is not None:
            self._emit(ep)

    def _emit(self, ep: nmea.Epoch):
        d = ep.to_dict()
        d["rx"] = self.rx_id
        self.last = d
        self.epochs.append(d)
        self.on_epoch(d)

    def close(self):
        ep = self.asm.flush()
        if ep is not None:
            self._emit(ep)
        if self._log:
            self._log.close()
            self._log = None


# ------------------------------------------------------------------ fuentes


def serial_reader(port: str, baud: int, ingest, stop: threading.Event, on_error):
    """Lee un puerto serie y alimenta `ingest(línea)`. Mismo destino que la simulación."""
    import serial  # pyserial

    try:
        with serial.Serial(port, baud, timeout=0.5) as ser:
            while not stop.is_set():
                raw = ser.readline()
                if raw:
                    ingest(raw.decode("ascii", errors="ignore"))
    except Exception as e:  # puerto ocupado, desconectado...
        on_error(f"{port}: {e}")


def probe_port(port: str, baud: int, seconds: float = 3.0, *, opener=None) -> dict:
    """Abre `port` unos segundos y valida que haya NMEA legible (con checksum).

    Devuelve {ok, stage, message, ...}. `stage` indica hasta dónde llegó:
    open (no abrió) -> data (no llegó nada) -> nmea (llegó, pero no es NMEA válido)
    -> ok. Incluye sentencias vistas, última calidad de fix, satélites y HDOP.
    """
    import pynmea2

    out = {"port": port, "baud": baud, "ok": False, "stage": "open", "message": "",
           "sentences": [], "good": 0, "bad": 0, "quality": None, "nsats": None, "hdop": None,
           "sats_tracked": 0}
    try:
        if opener is None:
            import serial  # pyserial
            opener = lambda: serial.Serial(port, baud, timeout=0.5)  # noqa: E731
        ser = opener()
    except Exception as e:
        out["message"] = f"No se pudo abrir {port}: {e} (¿ocupado por otro programa?)"
        return out
    kinds: set[str] = set()
    raw_bytes = 0
    tracked: set[str] = set()
    t_end = time.time() + seconds
    try:
        while time.time() < t_end:
            raw = ser.readline()
            if not raw:
                continue
            raw_bytes += len(raw)
            line = raw.decode("ascii", errors="ignore").strip()
            if not line.startswith("$"):
                out["bad"] += 1
                continue
            try:
                m = pynmea2.parse(line, check=True)
            except Exception:
                out["bad"] += 1
                continue
            out["good"] += 1
            kinds.add(m.sentence_type)
            if m.sentence_type == "GGA":
                out["quality"] = int(m.gps_qual or 0)
                out["nsats"] = int(m.num_sats or 0)
                try:
                    out["hdop"] = float(m.horizontal_dil)
                except (TypeError, ValueError):
                    out["hdop"] = None
            elif m.sentence_type == "GSV":
                for i in range(1, 5):
                    if getattr(m, f"sv_prn_num_{i}", "") and getattr(m, f"snr_{i}", ""):
                        tracked.add(f"{m.talker}{getattr(m, f'sv_prn_num_{i}')}")
    finally:
        try:
            ser.close()
        except Exception:
            pass
    out["sentences"] = sorted(kinds)
    out["sats_tracked"] = len(tracked)
    if raw_bytes == 0:
        out.update(stage="data", message="El puerto abre pero no llega ningún dato. "
                   "Revise baudios, alimentación del receptor y que TX del receptor vaya a RX del adaptador.")
    elif out["good"] == 0:
        out.update(stage="nmea", message="Llegan datos pero ninguna sentencia NMEA válida: "
                   "casi seguro los baudios no coinciden (pruebe 4800, 9600, 38400, 115200).")
    else:
        missing = [k for k in ("GGA", "RMC") if k not in kinds]
        out.update(ok=True, stage="ok",
                   message="NMEA correcto" + (f", pero faltan {', '.join(missing)}" if missing else ""))
        if missing:
            out["ok"] = False
    return out


def file_reader(path: str | Path, ingest, stop: threading.Event, speed: float = 0.0):
    """Reproduce un log NMEA (real o simulado). speed=0 -> lo más rápido posible;
    speed>0 -> espera 1/speed s por época (aprox., usa los GGA)."""
    with open(path, encoding="ascii", errors="ignore") as f:
        for line in f:
            if stop.is_set():
                break
            ingest(line)
            if speed > 0 and "GGA," in line[:8]:
                time.sleep(1.0 / speed)


# ------------------------------------------------------------------- sesión


class AcquisitionSession:
    def __init__(self, mode: str, receivers: list[str], *, out_dir: Path | None = None,
                 meta: dict | None = None):
        self.id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.mode = mode
        self.rx_ids = receivers
        self.dir = (out_dir or SESSIONS_DIR) / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = {"id": self.id, "mode": mode, "receivers": receivers, **(meta or {})}
        self.state = "idle"
        self.error: str | None = None
        self.events: deque = deque(maxlen=20000)
        self.seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.channels = {rx: ReceiverChannel(rx, self.dir / f"{rx}.nmea", self._on_epoch)
                         for rx in receivers}
        self.started_at: float | None = None
        self.sim: GnssSimulator | None = None
        self.procs: dict = {}

    # -- eventos
    def _on_epoch(self, d: dict):
        with self._lock:
            self.seq += 1
            self.events.append({"seq": self.seq, **d})

    def events_since(self, seq: int) -> list[dict]:
        with self._lock:
            return [e for e in self.events if e["seq"] > seq]

    def _fail(self, msg: str):
        self.error = msg
        self._stop.set()  # un puerto caído invalida la sesión diferencial

    # -- arranque
    def start_sim(self, cfg: SimConfig, duration_s: float, speed: float,
                  sats: SatArray | None = None):
        self.sim = GnssSimulator(cfg, sats)
        self.meta["sim"] = {
            "seed": cfg.seed, "dt": cfg.dt, "start": cfg.start.isoformat(),
            "receivers": [vars(r) for r in cfg.receivers],
            "truth_note": "En simulación la verdad de terreno es exacta; en modo real no existe.",
        }
        n = int(duration_s / cfg.dt)

        def run():
            self.state = "running"
            self.started_at = time.time()
            try:
                for _ in range(n):
                    if self._stop.is_set():
                        break
                    t0 = time.time()
                    for rx, lines in self.sim.step().items():
                        ch = self.channels[rx]
                        for ln in lines:
                            ch.ingest(ln)
                    if speed > 0:
                        time.sleep(max(0.0, cfg.dt / speed - (time.time() - t0)))
            except Exception as e:
                self._fail(f"simulación: {e}")
            self._finish()

        self._spawn(run)

    def start_real(self, ports: dict[str, tuple[str, int]], duration_s: float | None = None):
        self.meta["ports"] = {k: {"port": p, "baud": b} for k, (p, b) in ports.items()}
        self.state = "running"
        self.started_at = time.time()
        for rx, (port, baud) in ports.items():
            self._spawn(lambda rx=rx, port=port, baud=baud: serial_reader(
                port, baud, self.channels[rx].ingest, self._stop, self._fail))
        if duration_s:
            threading.Timer(duration_s, self.stop).start()
        self._spawn(self._watch_real)

    def start_replay(self, files: dict[str, str | Path], speed: float = 0.0):
        self.meta["replay"] = {k: str(v) for k, v in files.items()}
        self.state = "running"
        self.started_at = time.time()
        workers = [threading.Thread(target=file_reader, daemon=True, args=(
            p, self.channels[rx].ingest, self._stop, speed)) for rx, p in files.items()]

        def run():
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            self._finish()

        self._spawn(run)

    def start_sdr(self, configs: dict, duration_s: float | None = None, *, popen=None, binary="gnss-sdr"):
        """Un proceso GNSS-SDR por receptor (config: `gnsssdr.GnssSdrConfig`).

        Su NMEA entra por `ReceiverChannel.ingest`, igual que un puerto serie. Con fuente
        «archivo» la sesión termina sola cuando acaban los procesos.
        """
        from . import gnsssdr
        self.meta["sdr"] = {rx: {k: v for k, v in vars(c).items() if k != "nmea_path"}
                            for rx, c in configs.items()}
        kw = {"popen": popen} if popen else {}
        self.procs = {rx: gnsssdr.GnssSdrProcess(c, self.dir / f"gnsssdr-{rx}", self.channels[rx].ingest,
                                                 self._fail, binary=binary, **kw)
                      for rx, c in configs.items()}
        self.state = "running"
        self.started_at = time.time()
        for p in self.procs.values():
            p.start()
        if duration_s:
            threading.Timer(duration_s, self.stop).start()

        def watch():
            while not self._stop.is_set():
                if all(not p.running for p in self.procs.values()):
                    time.sleep(0.5)  # deja drenar el tail de NMEA
                    break
                time.sleep(0.2)
            for p in self.procs.values():
                p.stop()
            self._finish()

        self._spawn(watch)

    def sdr_status(self) -> dict:
        return {rx: p.status() for rx, p in getattr(self, "procs", {}).items()}

    def _watch_real(self):
        while not self._stop.is_set():
            time.sleep(0.2)
        self._finish()

    def _spawn(self, fn):
        t = threading.Thread(target=fn, daemon=True)
        self._threads.append(t)
        t.start()

    # -- fin
    def stop(self):
        self._stop.set()

    def _finish(self):
        if self.state == "finished":
            return
        for ch in self.channels.values():
            ch.close()
        self.state = "finished"
        self.meta["ended_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        self.meta["epochs"] = {rx: len(ch.epochs) for rx, ch in self.channels.items()}
        self.meta["bad_lines"] = {rx: ch.asm.bad_lines for rx, ch in self.channels.items()}
        if self.error:
            self.meta["error"] = self.error
        (self.dir / "meta.json").write_text(json.dumps(self.meta, indent=2), encoding="utf-8")

    def status(self) -> dict:
        return {
            "id": self.id, "mode": self.mode, "state": self.state, "error": self.error,
            "elapsed_s": (time.time() - self.started_at) if self.started_at else 0,
            "seq": self.seq,
            **({"sdr": self.sdr_status()} if self.procs else {}),
            "receivers": {rx: {"lines": ch.lines, "epochs": len(ch.epochs),
                               "bad_lines": ch.asm.bad_lines, "last": ch.last}
                          for rx, ch in self.channels.items()},
        }


def default_sim_config(*, start: dt.datetime | None = None, seed: int = 1,
                       lat=-12.0464, lon=-77.0428, alt=150.0, baseline_m: float = 3.0,
                       rover_cn0_offset_db: float = 0.0, **kw) -> SimConfig:
    """Referencia + móvil separado `baseline_m` metros hacia el este."""
    import math
    dlon = baseline_m / (111320.0 * math.cos(math.radians(lat)))
    return SimConfig(
        start=start or dt.datetime.now(dt.timezone.utc).replace(microsecond=0),
        seed=seed,
        receivers=[
            ReceiverConfig("ref", lat, lon, alt),
            ReceiverConfig("rover", lat, lon + dlon, alt, cn0_offset_db=rover_cn0_offset_db),
        ],
        **kw,
    )


def list_sessions() -> list[dict]:
    out = []
    if SESSIONS_DIR.exists():
        for d in sorted(SESSIONS_DIR.iterdir(), reverse=True):
            m = d / "meta.json"
            if m.exists():
                out.append(json.loads(m.read_text(encoding="utf-8")))
    return out
