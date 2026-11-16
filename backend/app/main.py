from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.actions import router as actions_router
from app.api.auth import require_user, router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.distribution import router as distribution_router
from app.api.evaluation import router as evaluation_router
from app.api.explorer import router as explorer_router
from app.api.ingest import router as ingest_router
from app.api.listing import router as listing_router
from app.api.insights import router as insights_router
from app.api.issues import router as issues_router
from app.api.jobs import router as jobs_router
from app.api.mapping import router as mapping_router
from app.api.quality import router as quality_router
from app.api.replies import router as replies_router
from app.api.reports import router as reports_router
from app.api.results import router as results_router
from app.api.sentiment import router as sentiment_router
from app.api.uploads import router as uploads_router
from app.core.config import settings
from app.db.session import get_session

app = FastAPI(title=settings.app_name, version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(require_user)]   # every data route needs a logged-in user (settings.auth_required)
app.include_router(auth_router)
app.include_router(uploads_router, dependencies=protected)
app.include_router(mapping_router, dependencies=protected)
app.include_router(ingest_router, dependencies=protected)
app.include_router(listing_router, dependencies=protected)
app.include_router(insights_router, dependencies=protected)
app.include_router(jobs_router, dependencies=protected)
app.include_router(issues_router, dependencies=protected)
app.include_router(dashboard_router, dependencies=protected)
app.include_router(explorer_router, dependencies=protected)
app.include_router(evaluation_router, dependencies=protected)
app.include_router(actions_router, dependencies=protected)
app.include_router(results_router, dependencies=protected)
app.include_router(sentiment_router, dependencies=protected)
app.include_router(quality_router, dependencies=protected)
app.include_router(distribution_router, dependencies=protected)
app.include_router(reports_router, dependencies=protected)
app.include_router(replies_router, dependencies=protected)


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
