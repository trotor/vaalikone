from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from vaalikone.api.routes.documents import router as documents_router
from vaalikone.api.routes.parties import router as parties_router
from vaalikone.api.routes.representatives import router as representatives_router
from vaalikone.api.routes.sources import router as sources_router
from vaalikone.api.routes.stats import router as stats_router
from vaalikone.api.routes.query import router as query_router

app = FastAPI(title="Vaalikone API", version="0.1.0")

app.include_router(parties_router)
app.include_router(representatives_router)
app.include_router(sources_router)
app.include_router(stats_router)
app.include_router(query_router)
app.include_router(documents_router)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}
