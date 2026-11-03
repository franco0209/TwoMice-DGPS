from fastapi import APIRouter, File, HTTPException, UploadFile

from ..services.resonance import band_report, find_resonances
from ..services.touchstone import parse_s1p

router = APIRouter(prefix="/api/vna", tags=["vna"])


@router.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        sp = parse_s1p((await file.read()).decode("utf-8", errors="ignore"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    z = sp.impedance
    return {
        "filename": file.filename,
        "z0": sp.z0,
        "freq_mhz": (sp.freq_hz / 1e6).tolist(),
        "s11_db": sp.s11_db.tolist(),
        "vswr": sp.vswr.tolist(),
        "z_real": z.real.tolist(),
        "z_imag": z.imag.tolist(),
        "gamma_real": sp.gamma.real.tolist(),
        "gamma_imag": sp.gamma.imag.tolist(),
        "resonances": find_resonances(sp),
        "bands": band_report(sp),
    }
