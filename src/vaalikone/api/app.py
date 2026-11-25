from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vaalikone.api.deps import verify_api_key
from vaalikone.api.routes.documents import router as documents_router
from vaalikone.api.routes.elections import router as elections_router
from vaalikone.api.routes.parties import router as parties_router
from vaalikone.api.routes.query import router as query_router
from vaalikone.api.routes.representatives import router as representatives_router
from vaalikone.api.routes.sources import router as sources_router
from vaalikone.api.routes.stats import router as stats_router

app = FastAPI(title="Vaalikone API", version="0.2.0")

# API key auth (active only when VAALIKONE_API_KEY is set; / and /health stay open)
api_dependencies = [Depends(verify_api_key)]

app.include_router(parties_router, dependencies=api_dependencies)
app.include_router(representatives_router, dependencies=api_dependencies)
app.include_router(sources_router, dependencies=api_dependencies)
app.include_router(stats_router, dependencies=api_dependencies)
app.include_router(query_router, dependencies=api_dependencies)
app.include_router(documents_router, dependencies=api_dependencies)
app.include_router(elections_router, dependencies=api_dependencies)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}
