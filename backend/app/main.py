from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import vna

app = FastAPI(title="TwoMice-DGPS", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(vna.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
