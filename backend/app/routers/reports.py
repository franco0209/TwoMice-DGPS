import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from ..services import report
from .analysis import saved_result, session_dir
from ..services import dgps

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _pdf(res: dict, title: str, meta: dict | None, vna: dict | None) -> Response:
    data = report.build_pdf(res, title, meta, vna)
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="informe-twomice-dgps.pdf"'})


@router.get("/sessions/{session_id}.pdf")
def session_pdf(session_id: str):
    res = saved_result(session_id)
    d = session_dir(session_id)
    try:
        _, _, meta = dgps.load_session(d)
    except dgps.AnalysisError:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    return _pdf(res, f"Informe TwoMice-DGPS · sesión {session_id}", meta, None)


@router.post("/pdf")
async def pdf_from_result(result: UploadFile = File(...), vna: UploadFile | None = File(None)):
    """Informe a partir de un resultado de análisis (JSON) y, opcional, un análisis VNA (JSON)."""
    try:
        res = json.loads(await result.read())
        v = json.loads(await vna.read()) if vna else None
        return _pdf(res, "Informe TwoMice-DGPS", res.get("session"), v)
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"Resultado inválido: {e}")
