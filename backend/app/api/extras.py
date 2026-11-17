import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(tags=["extras"])


def _load(name: str, ws: int, command: str) -> dict:
    p = Path(settings.tfidf_path).parent / f"{name}_ws{ws}.json"
    if not p.exists():
        return {"available": False, "command": command}
    try:
        return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}
    except ValueError:
        return {"available": False, "command": command}


@router.get("/extras/absa")
async def absa(session: AsyncSession = Depends(get_session)):
    """The saved result of scripts/absa_validate.py for this workspace."""
    return _load("absa", await _ws(session), "python -m scripts.absa_validate")


@router.get("/extras/topics")
async def topics(session: AsyncSession = Depends(get_session)):
    """The saved result of scripts/topic_discovery.py for this workspace."""
    return _load("topics", await _ws(session), "pip install -r requirements-extra.txt, then python -m scripts.topic_discovery")
