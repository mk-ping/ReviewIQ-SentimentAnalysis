from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import domains as D
from app.core import thresholds as T
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(tags=["domains"])


@router.get("/domains")
async def list_domains():
    """Every review type with its aspects and seed phrases."""
    return {"forced": settings.aspect_domain, "domains": [
        {"key": k, "label": p["label"], "categories": [{"aspect": c, "seeds": p["seeds"][c]} for c in p["categories"]]}
        for k, p in D.PROFILES.items()]}


@router.get("/domains/detected")
async def detected(session: AsyncSession = Depends(get_session)):
    """The review type found for each product, the same way the aspects job decides."""
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT p.name, r.text_clean FROM review r JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :sp ORDER BY r.review_id LIMIT 20000"""),
        {"ws": ws, "sp": T.SPAM_MAX})).all()
    by: dict[str, list[str]] = {}
    for n, t in rows:
        by.setdefault(n, []).append(t)
    return {"forced": settings.aspect_domain, "products": [
        {"product": n, "domain": D.detect_domain(ts, settings.aspect_domain), "reviews": len(ts)} for n, ts in sorted(by.items())]}
