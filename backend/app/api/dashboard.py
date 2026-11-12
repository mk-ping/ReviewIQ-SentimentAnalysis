from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.db.session import get_session
from app.models import Workspace
from app.services.views import refresh_views

router = APIRouter(tags=["dashboard"])

FILT = """
  AND (CAST(:product AS text) IS NULL OR p.name = CAST(:product AS text))
  AND (CAST(:d1 AS date) IS NULL OR r.review_date >= CAST(:d1 AS date))
  AND (CAST(:d2 AS date) IS NULL OR r.review_date <= CAST(:d2 AS date))
"""
MV_FILT = """
  AND (CAST(:product AS text) IS NULL OR p.name = CAST(:product AS text))
  AND (CAST(:d1 AS date) IS NULL OR m.day >= CAST(:d1 AS date))
  AND (CAST(:d2 AS date) IS NULL OR m.day <= CAST(:d2 AS date))
"""


async def _ws(session: AsyncSession) -> int:
    return await session.scalar(select(func.min(Workspace.workspace_id))) or 1


def _f(x, nd=2):
    return None if x is None else round(float(x), nd)


def _args(ws, product, d1, d2) -> dict:
    return {"ws": ws, "spam": T.SPAM_MAX, "product": product, "d1": d1, "d2": d2}


def audience(share_low: float, share_five: float, mean: float) -> str:
    if share_low >= 0.25 and share_five >= 0.4:
        return "divided: many customers love it and many dislike it"
    if mean >= 4.2:
        return "mostly happy"
    if mean <= 2.5:
        return "mostly unhappy"
    return "lukewarm"


@router.get("/distribution")
async def distribution(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                       session: AsyncSession = Depends(get_session)):
    a = _args(await _ws(session), product, date_from, date_to)
    base = """FROM review r JOIN product p ON p.product_id = r.product_id
              WHERE r.workspace_id = :ws AND r.rating_norm IS NOT NULL AND r.spam_score <= :spam""" + FILT
    hist = (await session.execute(text(f"SELECT round(r.rating_norm::numeric)::int AS star, count(*) {base} GROUP BY 1 ORDER BY 1"), a)).all()
    n, mean, sd = (await session.execute(text(f"SELECT count(*), avg(r.rating_norm), stddev_pop(r.rating_norm) {base}"), a)).one()
    counts = {s: c for s, c in hist}
    bars = [{"stars": s, "count": counts.get(s, 0), "share": round(counts.get(s, 0) / n, 3) if n else 0} for s in range(1, 6)]
    low = (counts.get(1, 0) + counts.get(2, 0)) / n if n else 0
    five = counts.get(5, 0) / n if n else 0
    return {"n": n, "low_sample": n < T.LOW_SAMPLE, "average": _f(mean), "spread": _f(sd), "histogram": bars,
            "share_1_2_stars": round(low, 3), "share_5_stars": round(five, 3),
            "audience": audience(low, five, float(mean)) if n else None,
            "note": "Audience label thresholds are reasoned starting values."}


@router.get("/summary")
async def summary(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                  session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    a = _args(ws, product, date_from, date_to)
    row = (await session.execute(text("""
        SELECT count(*), count(r.rating_norm), avg(r.rating_norm), count(s.review_id),
               count(*) FILTER (WHERE s.text_label = 'pos'), count(*) FILTER (WHERE s.text_label = 'neg'),
               count(*) FILTER (WHERE s.mismatch_type IS NOT NULL), count(s.fused_stars)
        FROM review r JOIN product p ON p.product_id = r.product_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam""" + FILT), a)).one()
    n, n_rated, avg, n_scored, n_pos, n_neg, n_mm, n_fused = row
    c_all = await session.scalar(text("SELECT avg(rating_norm) FROM review WHERE workspace_id = :ws AND spam_score <= :spam"),
                                 {"ws": ws, "spam": T.SPAM_MAX})
    weighted = None
    if n_rated and c_all is not None:
        w = n_rated / (n_rated + T.TRUE_RATING_M)
        weighted = w * float(avg) + (1 - w) * float(c_all)
    problems = (await session.execute(text("""
        SELECT i.name, i.n_reviews, ip.priority_score FROM issue i JOIN issue_priority ip ON ip.issue_id = i.issue_id
        WHERE i.workspace_id = :ws ORDER BY ip.priority_score DESC LIMIT 3"""), {"ws": ws})).all()
    strengths = (await session.execute(text("""
        SELECT a.name, count(*), avg(ra.sentiment) FROM review_aspect ra
        JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.sentiment >= :pos AND ra.confidence >= :conf
        GROUP BY a.name ORDER BY count(*) DESC LIMIT 3"""),
        {"ws": ws, "spam": T.SPAM_MAX, "pos": -T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF})).all()
    return {
        "reviews": n, "rated_reviews": n_rated, "scored_reviews": n_scored, "low_sample": n < T.LOW_SAMPLE,
        "average_rating": _f(avg), "weighted_rating": _f(weighted),
        "net_sentiment": _f((n_pos - n_neg) / n_scored) if n_scored else None,
        "percent_negative": _f(100 * n_neg / n_scored, 1) if n_scored else None,
        "mismatch_rate": _f(n_mm / n_fused, 3) if n_fused else None,
        "top_problems": [{"issue": i, "reviews": r, "priority_score": p} for i, r, p in problems],
        "top_strengths": [{"aspect": x, "positive_mentions": c, "avg_sentiment": _f(s)} for x, c, s in strengths],
        "scope": "Problems and strengths cover the whole workspace and ignore the product filter.",
    }


@router.get("/trends")
async def trends(grain: Literal["week", "month"] = "week", product: str | None = None,
                 date_from: date | None = None, date_to: date | None = None,
                 session: AsyncSession = Depends(get_session)):
    a = _args(await _ws(session), product, date_from, date_to)
    a["grain"] = grain
    rows = (await session.execute(text("""
        SELECT date_trunc(CAST(:grain AS text), m.day)::date AS period, sum(m.n), sum(m.sum_rating) / NULLIF(sum(m.n_rated), 0),
               sum(m.sum_fused) / NULLIF(sum(m.n_fused), 0),
               (sum(m.n_pos) - sum(m.n_neg))::float / NULLIF(sum(m.n_scored), 0)
        FROM mv_product_daily m JOIN product p ON p.product_id = m.product_id
        WHERE m.workspace_id = :ws""" + MV_FILT + " GROUP BY 1 ORDER BY 1"), a)).all()
    return {"grain": grain, "points": [
        {"period": p, "reviews": int(n), "low_sample": n < T.LOW_SAMPLE, "avg_rating": _f(r),
         "avg_fused_rating": _f(f), "net_sentiment": _f(ns)} for p, n, r, f, ns in rows],
        "note": "Reviews without a date are not in trends. Read from the materialized view; it refreshes after each job."}


@router.post("/views/refresh")
async def refresh():
    await refresh_views()
    return {"refreshed": True}
