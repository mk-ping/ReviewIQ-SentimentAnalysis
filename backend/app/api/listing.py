import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import thresholds as T
from app.core.action_rules import rule_for
from app.core.config import settings
from app.db.session import get_session
from app.services import listing as L
from app.services.aspects import llm_available

router = APIRouter(tags=["listing"])


class ListingBody(BaseModel):
    source_text: str = Field(min_length=20, max_length=8000)


@router.get("/products")
async def products(session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT p.product_id, p.name, count(r.review_id), count(e.review_id)
        FROM product p LEFT JOIN review r ON r.product_id = p.product_id
        LEFT JOIN review_embedding e ON e.review_id = r.review_id
        WHERE p.workspace_id = :ws GROUP BY p.product_id, p.name ORDER BY p.name"""), {"ws": ws})).all()
    return {"products": [{"product_id": i, "name": n, "reviews": c, "embedded": e} for i, n, c, e in rows]}


async def _view(session: AsyncSession, listing_id: int) -> list[dict]:
    rows = (await session.execute(text("""
        SELECT c.claim_id, c.text, c.quote, a.name, v.supports, v.contradicts, v.verdict
        FROM claim c LEFT JOIN aspect a ON a.aspect_id = c.aspect_id LEFT JOIN claim_verdict v ON v.claim_id = c.claim_id
        WHERE c.listing_id = :l ORDER BY c.claim_id"""), {"l": listing_id})).all()
    ids = [r[0] for r in rows]
    ev: dict[int, list] = {}
    if ids:
        for cid, rid, sent, stance, score in (await session.execute(text("""
            SELECT claim_id, review_id, sentence, stance, score FROM claim_evidence
            WHERE claim_id = ANY(CAST(:ids AS int[])) AND stance <> 'unrelated' ORDER BY claim_id, score DESC"""), {"ids": ids})).all():
            if len(ev.setdefault(cid, [])) < 5:
                ev[cid].append({"review_id": rid, "sentence": sent, "stance": stance, "similarity": round(score, 3)})
    out = []
    for cid, claim, quote, aspect, s, c, v in rows:
        rel = (s or 0) + (c or 0)
        action = None
        if v == "contradicted":
            action = f"{rule_for(aspect or '')[0]}, or rewrite the claim so it matches what customers experience."
        out.append({"claim_id": cid, "claim": claim, "quote": quote, "aspect": aspect, "verdict": v,
                    "supports": s, "contradicts": c,
                    "support_share": round(s / rel, 3) if rel else None, "evidence": ev.get(cid, []), "action": action})
    return out


@router.post("/products/{product_id}/listing")
async def add_listing(product_id: int, body: ListingBody, session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    if not (await session.execute(text("SELECT 1 FROM product WHERE product_id = :p AND workspace_id = :ws"), {"p": product_id, "ws": ws})).scalar():
        raise HTTPException(404, "Product not found. GET /products lists the ids.")
    embedded = (await session.execute(text(
        "SELECT count(*) FROM review_embedding e JOIN review r ON r.review_id = e.review_id WHERE r.product_id = :p"), {"p": product_id})).scalar()
    if not embedded:
        raise HTTPException(409, "This product's reviews have no embeddings yet. Run POST /uploads/{id}/embed (worker running) first.")
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        if not await llm_available(client):
            raise HTTPException(503, f"The local LLM '{settings.llm_model}' is not reachable at {settings.llm_url}. Start Ollama.")
        claims = await L.extract_claims(client, body.source_text)
        listing_id = (await session.execute(text(
            "INSERT INTO listing (workspace_id, product_id, source_text) VALUES (:ws, :p, :t) RETURNING listing_id"),
            {"ws": ws, "p": product_id, "t": body.source_text})).scalar_one()
        for c in claims:
            aid = None
            if c["aspect"]:
                aid = (await session.execute(text("SELECT aspect_id FROM aspect WHERE workspace_id = :ws AND name = :n"),
                                             {"ws": ws, "n": c["aspect"]})).scalar()
            cid = (await session.execute(text(
                "INSERT INTO claim (listing_id, text, quote, aspect_id) VALUES (:l, :t, :q, :a) RETURNING claim_id"),
                {"l": listing_id, "t": c["claim"], "q": c["quote"], "a": aid})).scalar_one()
            sup = con = 0
            for rid, sentence, sim in await L.collect_evidence(session, ws, product_id, c["claim"]):
                stance = await L.judge(client, c["claim"], sentence)
                if stance is None:
                    continue
                await session.execute(text("""
                    INSERT INTO claim_evidence (claim_id, review_id, sentence, stance, score) VALUES (:c, :r, :s, :st, :sc)
                    ON CONFLICT DO NOTHING"""), {"c": cid, "r": rid, "s": sentence, "st": stance, "sc": sim})
                sup += stance == "supports"
                con += stance == "contradicts"
            await session.execute(text(
                "INSERT INTO claim_verdict (claim_id, supports, contradicts, verdict) VALUES (:c, :s, :n, :v)"),
                {"c": cid, "s": sup, "n": con, "v": L.verdict(sup, con)})
        await session.commit()
    return {"listing_id": listing_id, "claims": await _view(session, listing_id),
            "note": f"Stance is judged by a small local model. A verdict needs at least {T.LISTING_MIN_EVIDENCE} relevant sentences; "
                    "thresholds are starting values until tuned on hand-checked claims."}


@router.get("/products/{product_id}/claims")
async def get_claims(product_id: int, session: AsyncSession = Depends(get_session)):
    lid = (await session.execute(text(
        "SELECT listing_id FROM listing WHERE product_id = :p ORDER BY uploaded_at DESC, listing_id DESC LIMIT 1"), {"p": product_id})).scalar()
    if lid is None:
        raise HTTPException(404, "No listing for this product yet. POST /products/{id}/listing first.")
    return {"listing_id": lid, "claims": await _view(session, lid)}
