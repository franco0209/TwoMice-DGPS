import asyncio
import datetime as dt
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..services import acquisition as acq

router = APIRouter(prefix="/api/gps", tags=["gps"])
_current: acq.AcquisitionSession | None = None


class SimParams(BaseModel):
    seed: int = 1
    lat: float = -12.0464
    lon: float = -77.0428
    alt: float = 150.0
    baseline_m: float = Field(3.0, ge=0.1, le=1000)
    rover_cn0_offset_db: float = Field(0.0, ge=-15, le=5)
    start: dt.datetime | None = None
    iono_zenith_m: float = Field(5.0, ge=0, le=30)
    mp_sigma_m: float = Field(0.9, ge=0, le=10)
    elev_mask: float = Field(10.0, ge=0, le=45)


class PortParams(BaseModel):
    port: str
    baud: int = 9600


class StartBody(BaseModel):
    mode: Literal["sim", "real"]
    duration_s: float = Field(600, gt=0, le=86400)
    speed: float = Field(1.0, ge=0, le=100000, description="Solo sim. 0 = lo más rápido posible")
    sim: SimParams = SimParams()
    ref: PortParams | None = None
    rover: PortParams | None = None


def _require() -> acq.AcquisitionSession:
    if _current is None:
        raise HTTPException(404, "No hay sesión")
    return _current


@router.get("/ports")
def ports():
    from serial.tools import list_ports
    return [{"port": p.device, "description": p.description} for p in list_ports.comports()]


@router.post("/sessions")
def start(body: StartBody):
    global _current
    if _current is not None and _current.state == "running":
        raise HTTPException(409, "Ya hay una sesión en curso; deténgala primero")
    if body.mode == "sim":
        p = body.sim
        s = acq.AcquisitionSession("sim", ["ref", "rover"])
        cfg = acq.default_sim_config(
            start=p.start, seed=p.seed, lat=p.lat, lon=p.lon, alt=p.alt,
            baseline_m=p.baseline_m, rover_cn0_offset_db=p.rover_cn0_offset_db,
            iono_zenith_m=p.iono_zenith_m, mp_sigma_m=p.mp_sigma_m, elev_mask=p.elev_mask)
        s.start_sim(cfg, body.duration_s, body.speed)
    else:
        if not (body.ref and body.rover):
            raise HTTPException(422, "El modo real requiere los puertos ref y rover")
        if body.ref.port == body.rover.port:
            raise HTTPException(422, "ref y rover deben usar puertos distintos")
        s = acq.AcquisitionSession("real", ["ref", "rover"])
        s.start_real({"ref": (body.ref.port, body.ref.baud),
                      "rover": (body.rover.port, body.rover.baud)}, body.duration_s)
    _current = s
    return s.status()


@router.get("/sessions/current")
def current():
    return _require().status()


@router.post("/sessions/current/stop")
def stop():
    s = _require()
    s.stop()
    return s.status()


@router.get("/sessions")
def sessions():
    return acq.list_sessions()


@router.get("/sessions/current/epochs")
def current_epochs(max_points: int = 2000):
    s = _require()
    out = {}
    for rx, ch in s.channels.items():
        eps = list(ch.epochs)
        step = max(1, len(eps) // max_points)
        out[rx] = [{k: e[k] for k in ("utc", "lat", "lon", "alt", "quality", "nsats", "hdop")}
                   for e in eps[::step]]
    return out


@router.websocket("/ws")
async def ws(sock: WebSocket):
    """Envía épocas nuevas (JSON) de la sesión actual. Cliente: {"epoch": {...}} y {"status": {...}}."""
    await sock.accept()
    last = 0
    sid = None
    try:
        while True:
            s = _current
            if s is not None:
                if s.id != sid:
                    sid, last = s.id, 0
                for e in s.events_since(last):
                    last = e["seq"]
                    await sock.send_text(json.dumps({"epoch": e}))
                st = s.status()
                for r in st["receivers"].values():
                    r.pop("last", None)
                await sock.send_text(json.dumps({"status": st}))
            await asyncio.sleep(0.25)
    except (WebSocketDisconnect, RuntimeError):
        pass
