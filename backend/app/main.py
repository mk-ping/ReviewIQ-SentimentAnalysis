from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    db_ok = (await session.execute(text("SELECT 1"))).scalar() == 1
    vec = (
        await session.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
    ).scalar()
    return {"status": "ok", "database": db_ok, "pgvector": vec}
