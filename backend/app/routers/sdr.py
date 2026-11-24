"""Endpoints de las etapas del asistente SDR (solo recepción)."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import sdr
from . import gps

router = APIRouter(prefix="/api/sdr", tags=["sdr"])
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


def _no_session():
    s = gps.current_session()
    if s is not None and s.state == "running":
        raise HTTPException(409, "Hay una sesión en curso; deténgala antes de sondear el hardware")


@router.get("/tools")
def tools():
    return sdr.tools_status()


class PingBody(BaseModel):
    ip: str
    count: int = Field(3, ge=1, le=10)


@router.post("/ping")
def ping(body: PingBody):
    return sdr.ping(body.ip, body.count)


@router.get("/usb")
def usb():
    return sdr.usb_devices()


class FindBody(BaseModel):
    kind: Literal["usrp", "rtlsdr"]
    args: str = ""
    index: int = Field(0, ge=0, le=16)


@router.post("/find")
def find(body: FindBody):
    _no_session()
    return sdr.find_devices(body.args) if body.kind == "usrp" else sdr.rtl_find(body.index)


@router.post("/probe")
def probe(body: FindBody):
    """USRP: uhd_usrp_probe. RTL-SDR: rtl_test (modelo y tuner)."""
    _no_session()
    return sdr.probe_usrp(body.args) if body.kind == "usrp" else sdr.rtl_find(body.index)


class BiasBody(BaseModel):
    index: int = Field(0, ge=0, le=16)
    on: bool


@router.post("/biast")
def biast(body: BiasBody):
    _no_session()
    return sdr.set_biast(body.index, body.on)


class CaptureBody(FindBody):
    fs: float = Field(2.048e6, ge=0.25e6, le=10e6)
    gain: float = Field(40.0, ge=0, le=76)
    seconds: float = Field(2.0, ge=0.5, le=10)
    save_as: str | None = Field(None, pattern=r"^[A-Za-z0-9_\-]{1,40}$")


@router.post("/capture-check")
def capture_check(body: CaptureBody):
    _no_session()
    keep = None
    if body.save_as:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        keep = str(RAW_DIR / f"{body.save_as}.iq")
    return sdr.capture_check(body.kind, args=body.args, index=body.index,
                             fs=body.fs, gain=body.gain, seconds=body.seconds, keep_path=keep)


@router.get("/gnsssdr/status")
def gnsssdr_status():
    s = gps.current_session()
    if s is None or s.mode != "sdr":
        raise HTTPException(404, "No hay sesión SDR")
    return {"state": s.state, "error": s.error, "sdr": s.sdr_status(),
            "epochs": {rx: len(ch.epochs) for rx, ch in s.channels.items()}}


@router.post("/gnsssdr/start")
def gnsssdr_start(body: gps.StartBody):
    body.mode = "sdr"
    return gps.start(body)


@router.post("/gnsssdr/stop")
def gnsssdr_stop():
    return gps.stop()
