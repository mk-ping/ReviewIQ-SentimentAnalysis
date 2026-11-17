
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import thresholds as T
from app.core.severe_terms import PREFILTER, severe_hits
from app.db.session import get_session
from app.services.replies import draft_reply, draft_thanks

router = APIRouter(tags=["replies"])


@router.get("/severe")
async def severe(limit: int = 100, session: AsyncSession = Depends(get_session)):
    """Reviews with safety, allergy, fraud or legal terms, regardless of how many there are."""
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT r.review_id, p.name, r.rating_norm, r.review_date, r.language, r.text_clean
        FROM review r JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND r.text_clean ~* :rx
        ORDER BY r.review_date DESC NULLS LAST, r.review_id DESC LIMIT 2000"""),
        {"ws": ws, "spam": T.SPAM_MAX, "rx": PREFILTER})).all()
    items = []
    for rid, prod, stars, d, lang, txt in rows:
        cats = severe_hits(txt)
        if cats:
            items.append({"review_id": rid, "product": prod, "stars": stars, "date": d, "language": lang,
                          "categories": cats, "text": txt})
    by_cat: dict[str, int] = {}
    for it in items:
        for c in it["categories"]:
            by_cat[c] = by_cat.get(c, 0) + 1
    return {"total": len(items), "by_category": by_cat, "items": items[:limit],
            "note": "Matches are found by words, so a hit can be a false alarm. A person should read each one."}


@router.get("/replies/queue")
async def reply_queue(kind: Literal["needs", "praise"] = "needs", tone: str = "professional", signature: str | None = None,
                      product: str | None = None, limit: int = 30, session: AsyncSession = Depends(get_session)):
    """kind=needs: reviews that deserve an answer, serious complaints first, then the most negative.
    kind=praise: happy reviews that deserve a thank-you. Reviews already marked sent or skipped are left out."""
    ws = await _ws(session)
    if kind == "needs":
        cond, order = "(s.text_label = 'neg' OR r.text_clean ~* :rx)", "s.fused_stars ASC NULLS LAST, r.review_id"
        aspect_cond, aspect_order = "ra.sentiment <= :neg", "ra.sentiment ASC"
    else:
        cond, order = "(s.text_label = 'pos' AND r.rating_norm >= 4 AND NOT (r.text_clean ~* :rx))", "s.fused_stars DESC NULLS LAST, r.review_id"
        aspect_cond, aspect_order = "ra.sentiment >= :pos", "ra.sentiment DESC"
    args = {"ws": ws, "spam": T.SPAM_MAX, "rx": PREFILTER, "conf": T.ASPECT_MIN_CONF, "neg": T.NEG_MENTION, "pos": -T.NEG_MENTION, "product": product}
    rows = (await session.execute(text(f"""
        SELECT r.review_id, p.name, r.rating_norm, r.language, r.text_clean, s.fused_stars, s.text_label,
               d.status, d.body,
               (SELECT a.name FROM review_aspect ra JOIN aspect a ON a.aspect_id = ra.aspect_id
                 WHERE ra.review_id = r.review_id AND ra.confidence >= :conf AND {aspect_cond}
                 ORDER BY {aspect_order} LIMIT 1) AS top_aspect
        FROM review r JOIN product p ON p.product_id = r.product_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        LEFT JOIN reply_draft d ON d.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND COALESCE(d.status, 'draft') = 'draft' AND {cond}
          AND (CAST(:product AS text) IS NULL OR p.name = CAST(:product AS text))
        ORDER BY {order} LIMIT 500"""), args)).all()
    items = []
    for rid, prod, stars, lang, txt, fused, label, status, body, aspect in rows:
        cats = severe_hits(txt) if kind == "needs" else []
        if kind == "needs":
            auto = draft_reply(cats, aspect, lang, product=prod, tone=tone, signature=signature)
        else:
            auto = draft_thanks(aspect, lang, product=prod, tone=tone, signature=signature)
        items.append({"review_id": rid, "product": prod, "stars": stars, "language": lang, "text": txt, "fused_stars": fused,
                      "severe": cats, "aspect": aspect, "saved": body is not None, "draft": body if body is not None else auto})
    if kind == "needs":
        items.sort(key=lambda i: (not i["severe"], i["fused_stars"] if i["fused_stars"] is not None else 99))
    done = dict((await session.execute(text("""
        SELECT d.status, count(*) FROM reply_draft d JOIN review r ON r.review_id = d.review_id
        WHERE r.workspace_id = :ws GROUP BY 1"""), {"ws": ws})).all())
    prods = [r[0] for r in (await session.execute(text("SELECT name FROM product WHERE workspace_id = :ws ORDER BY name"), {"ws": ws})).all()]
    return {"kind": kind, "total": len(items), "items": items[:limit], "products": prods,
            "counts": {"waiting": len(items), "serious": sum(1 for i in items if i["severe"]),
                       "sent": int(done.get("sent", 0)), "skipped": int(done.get("skipped", 0)), "saved_drafts": int(done.get("draft", 0))}}


class ReplyBody(BaseModel):
    body: str
    status: Literal["draft", "sent", "skipped"] = "draft"


@router.put("/replies/{review_id}")
async def save_reply(review_id: int, payload: ReplyBody, session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    ok = (await session.execute(text("SELECT 1 FROM review WHERE review_id = :id AND workspace_id = :ws"),
                                {"id": review_id, "ws": ws})).scalar()
    if not ok:
        raise HTTPException(404, "Review not found.")
    if payload.status != "skipped" and not payload.body.strip():
        raise HTTPException(422, "The reply is empty.")
    await session.execute(text("""
        INSERT INTO reply_draft (review_id, body, status) VALUES (:id, :b, :s)
        ON CONFLICT (review_id) DO UPDATE SET body = EXCLUDED.body, status = EXCLUDED.status, updated_at = now()"""),
        {"id": review_id, "b": payload.body.strip(), "s": payload.status})
    await session.commit()
    return {"saved": True, "review_id": review_id, "status": payload.status}

