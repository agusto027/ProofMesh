from contextlib import asynccontextmanager

from fastapi import FastAPI

from proofmesh.app.config import get_settings
from proofmesh.app.mcp_server import mcp
from proofmesh.storage.database import initialize


@asynccontextmanager
async def lifespan(_app):
    await initialize()
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="ProofMesh", version="0.1.0", description="Evidence-first agent orchestration API",
              lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "proofmesh"}


@app.get("/config")
async def configuration():
    settings = get_settings()
    return {"database": "configured", "host": settings.host, "port": settings.port,
            "search_provider": settings.search_provider}


# Keep this catch-all mount after API routes; FastMCP serves its own /mcp endpoint.
app.mount("/", mcp.streamable_http_app())


def run():
    import uvicorn
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
