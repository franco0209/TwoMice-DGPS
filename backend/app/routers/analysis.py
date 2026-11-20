import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..services import acquisition as acq
from ..services import dgps, report

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    h: float = Field(description="Altura elipsoidal (m)")

    def t(self):
        return (self.lat, self.lon, self.h)


class RunBody(BaseModel):
    session_id: str
    ref_known: Position | None = None      # por defecto, la verdad de la simulación
    rover_truth: Position | None = None    # opcional: habilita la exactitud (no solo la precisión)
    block: int | None = Field(None, ge=1, le=5000)
    n_boot: int = Field(500, ge=0, le=5000)


def session_dir(session_id: str):
    """Resuelve el id contra las carpetas existentes (evita rutas arbitrarias)."""
    if acq.SESSIONS_DIR.exists():
        for d in acq.SESSIONS_DIR.iterdir():
            if d.is_dir() and d.name == session_id:
                return d
    raise HTTPException(404, "Sesión no encontrada")


def _result(ref, rov, **kw):
    try:
        return dgps.analyze(ref, rov, **kw)
    except dgps.AnalysisError as e:
        raise HTTPException(422, str(e))


@router.post("/run")
def run(body: RunBody):
    d = session_dir(body.session_id)
    try:
        ref, rov, meta = dgps.load_session(d)
    except dgps.AnalysisError as e:
        raise HTTPException(422, str(e))
    truth = dgps.truth_from_meta(meta)
    ref_known = body.ref_known.t() if body.ref_known else truth.get("ref")
    rover_truth = body.rover_truth.t() if body.rover_truth else truth.get("rover")
    if ref_known is None:
        raise HTTPException(422, "Sesión real: indique la posición conocida de la referencia")
    res = _result(ref, rov, ref_known=ref_known, rover_truth=rover_truth,
                  block=body.block, n_boot=body.n_boot)
    res["session"] = {"id": d.name, "mode": meta.get("mode")}
    (d / "analysis.json").write_text(json.dumps(res), encoding="utf-8")
    return res


@router.post("/upload")
async def upload(
    ref_file: UploadFile = File(...), rover_file: UploadFile = File(...),
    ref_lat: float = Form(...), ref_lon: float = Form(...), ref_h: float = Form(...),
    rover_lat: float | None = Form(None), rover_lon: float | None = Form(None),
    rover_h: float | None = Form(None),
    block: int | None = Form(None), n_boot: int = Form(500),
):
    """Analiza dos logs .nmea subidos (p. ej. registrados con un terminal serie)."""
    ref = dgps.parse_nmea_text((await ref_file.read()).decode("ascii", errors="ignore"))
    rov = dgps.parse_nmea_text((await rover_file.read()).decode("ascii", errors="ignore"))
    truth = (rover_lat, rover_lon, rover_h) if None not in (rover_lat, rover_lon, rover_h) else None
    res = _result(ref, rov, ref_known=(ref_lat, ref_lon, ref_h), rover_truth=truth,
                  block=block, n_boot=min(max(n_boot, 0), 5000))
    res["session"] = {"id": None, "mode": "upload"}
    return res


@router.get("/experiments")
def experiments():
    """Sesiones guardadas con su último análisis (si existe)."""
    out = []
    for m in acq.list_sessions():
        p = acq.SESSIONS_DIR / m["id"] / "analysis.json"
        a = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        out.append({
            "id": m["id"], "mode": m.get("mode"), "epochs": m.get("epochs"),
            "ended_at": m.get("ended_at"), "error": m.get("error"),
            "has_truth": bool((m.get("sim") or {}).get("receivers")),
            "summary": None if a is None else {
                "cep50_before": a["before"]["cep50"], "cep50_after": a["after"]["cep50"],
                "cep95_before": a["before"]["cep95"], "cep95_after": a["after"]["cep95"],
                "improvement": a["improvement"], "same_sats_pct": a["epochs"]["same_sats_pct"],
            },
        })
    return out


@router.get("/sessions/{session_id}/result")
def saved_result(session_id: str):
    p = session_dir(session_id) / "analysis.json"
    if not p.exists():
        raise HTTPException(404, "Esa sesión aún no se ha analizado")
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/sessions/{session_id}/export")
def export(session_id: str, fmt: str = "csv"):
    res = saved_result(session_id)
    if fmt == "json":
        return Response(json.dumps(res, indent=2), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{session_id}.json"'})
    if fmt != "csv":
        raise HTTPException(422, "fmt debe ser csv o json")
    return Response(report.series_csv(res), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{session_id}.csv"'})
