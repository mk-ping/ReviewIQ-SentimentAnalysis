from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.actions import router as actions_router
from app.api.dashboard import router as dashboard_router
from app.api.evaluation import router as evaluation_router
from app.api.explorer import router as explorer_router
from app.api.ingest import router as ingest_router
from app.api.insights import router as insights_router
from app.api.issues import router as issues_router
from app.api.jobs import router as jobs_router
from app.api.mapping import router as mapping_router
from app.api.reports import router as reports_router
from app.api.results import router as results_router
from app.api.uploads import router as uploads_router
from app.core.config import settings
from app.db.session import get_session

app = FastAPI(title=settings.app_name, version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads_router)
app.include_router(mapping_router)
app.include_router(ingest_router)
app.include_router(insights_router)
app.include_router(jobs_router)
app.include_router(issues_router)
app.include_router(dashboard_router)
app.include_router(explorer_router)
app.include_router(evaluation_router)
app.include_router(actions_router)
app.include_router(results_router)
app.include_router(reports_router)


@app.get("/")
async def root():
    return {"app": settings.app_name, "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    db_ok = (await session.execute(text("SELECT 1"))).scalar() == 1
    vec = (
        await session.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    ).scalar()
    return {"status": "ok", "database": db_ok, "pgvector": vec}


from pathlib import Path as _Path
from fastapi.responses import FileResponse as _FileResponse


@app.get("/app", include_in_schema=False)
async def web_app():
    return _FileResponse(_Path(__file__).parent / "static" / "index.html")
