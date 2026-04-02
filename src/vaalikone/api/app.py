from fastapi import FastAPI

from vaalikone.api.routes.parties import router as parties_router
from vaalikone.api.routes.representatives import router as representatives_router
from vaalikone.api.routes.sources import router as sources_router

app = FastAPI(title="Vaalikone API", version="0.1.0")

app.include_router(parties_router)
app.include_router(representatives_router)
app.include_router(sources_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
