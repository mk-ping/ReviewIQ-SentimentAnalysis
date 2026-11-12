from datetime import date, timedelta
from statistics import mean, pstdev

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import FILT, _args, _f, _ws
from app.core import thresholds as T
from app.db.session import get_session

router = APIRouter(tags=["explorer"])

NEG_OK = "ra.sentiment <= :neg AND ra.confidence >= :conf AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> ''"


def spike_z(history: list[float], latest: float):
    """z = (count - mean) / std over earlier weeks. None when there is too little or flat history."""
    if len(history) < T.SPIKE_MIN_WEEKS:
        return None
    sd = pstdev(history)
    if sd == 0:
        return None
    return (latest - mean(history)) / sd


@router.get("/rating-vs-text")
async def rating_vs_text(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                         session: AsyncSession = Depends(get_session)):
    a = _args(await _ws(session), product, date_from, date_to)
    a["gap"] = T.STAR_GAP_FLAG
    base = """FROM review r JOIN product p ON p.product_id = r.product_id
              JOIN review_score s ON s.review_id = r.review_id
              WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.fused_stars IS NOT NULL""" + FILT
    n, mm, under, over, gap, big = (await session.execute(text(f"""
        SELECT count(*), count(*) FILTER (WHERE s.mismatch_type IS NOT NULL),
               count(*) FILTER (WHERE s.mismatch_type = 'underrated'), count(*) FILTER (WHERE s.mismatch_type = 'overrated'),
               avg(abs(s.star_gap)), count(*) FILTER (WHERE abs(s.star_gap) >= :gap) {base}"""), a)).one()
    levels = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, count(*), avg(s.pred_stars) {base} GROUP BY 1 ORDER BY 1"""), a)).all()
    return {
        "n": n, "low_sample": n < T.LOW_SAMPLE,
        "agreement_rate": _f(1 - mm / n, 3) if n else None,
        "mismatches": mm, "underrated": under, "overrated": over,
        "mean_abs_star_gap": _f(gap), "big_gap_share": _f(big / n, 3) if n else None,
        "by_star": [{"stars": s, "reviews": c, "avg_text_stars": _f(p)} for s, c, p in levels],
        "note": "Based on one sentiment model with uncalibrated confidence; thresholds are starting values until the gold set exists.",
    }


@router.get("/aspects/drivers")
async def drivers(min_stars: float = Query(1, ge=1, le=5), max_stars: float = Query(2, ge=1, le=5),
                  session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    a = {"ws": ws, "spam": T.SPAM_MAX, "lo": min_stars, "hi": max_stars, "conf": T.ASPECT_MIN_CONF}
    sizes = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE r.rating_norm BETWEEN :lo AND :hi), count(*) FILTER (WHERE r.rating_norm NOT BETWEEN :lo AND :hi)
        FROM review r JOIN review_aspect_run u ON u.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND r.rating_norm IS NOT NULL"""), a)).one()
    n_in, n_out = sizes
    rows = (await session.execute(text("""
        SELECT x.name,
               count(DISTINCT x.review_id) FILTER (WHERE x.rating_norm BETWEEN :lo AND :hi),
               count(DISTINCT x.review_id) FILTER (WHERE x.rating_norm NOT BETWEEN :lo AND :hi),
               avg(x.sentiment) FILTER (WHERE x.rating_norm BETWEEN :lo AND :hi)
        FROM (SELECT a.name, ra.review_id, ra.sentiment, r.rating_norm FROM review_aspect ra
              JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
              WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND r.rating_norm IS NOT NULL
                AND ra.confidence >= :conf) x
        GROUP BY x.name"""), a)).all()
    out = [{"aspect": n, "reviews_in_range": i, "share_in_range": _f(i / n_in, 3) if n_in else None,
            "share_elsewhere": _f(o / n_out, 3) if n_out else None, "avg_sentiment_in_range": _f(s)}
           for n, i, o, s in rows]
    out.sort(key=lambda d: -(d["share_in_range"] or 0))
    return {"stars": [min_stars, max_stars], "reviews_in_range": n_in, "reviews_elsewhere": n_out,
            "low_sample": n_in < T.LOW_SAMPLE, "drivers": out,
            "note": "Compares how often each aspect is discussed by this star range versus all other rated reviews."}


@router.get("/compare")
async def compare(products: list[str] = Query(..., min_length=1), session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    a = {"ws": ws, "spam": T.SPAM_MAX, "names": products, "conf": T.ASPECT_MIN_CONF}
    base = (await session.execute(text("""
        SELECT p.name, count(*), avg(r.rating_norm), stddev_pop(r.rating_norm), count(s.review_id),
               count(*) FILTER (WHERE s.text_label = 'pos'), count(*) FILTER (WHERE s.text_label = 'neg')
        FROM review r JOIN product p ON p.product_id = r.product_id LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND p.name = ANY(CAST(:names AS text[])) GROUP BY p.name"""), a)).all()
    asp = (await session.execute(text("""
        SELECT p.name, a.name, count(*), avg(ra.sentiment) FROM review_aspect ra
        JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
        JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.confidence >= :conf
          AND p.name = ANY(CAST(:names AS text[])) GROUP BY p.name, a.name"""), a)).all()
    by: dict[str, list] = {}
    for pn, an, c, s in asp:
        by.setdefault(pn, []).append({"aspect": an, "mentions": c, "avg_sentiment": _f(s), "low_sample": c < T.LOW_SAMPLE})
    found = {r[0] for r in base}
    return {"products": [
        {"product": n, "reviews": c, "low_sample": c < T.LOW_SAMPLE, "avg_rating": _f(avg), "spread": _f(sd),
         "net_sentiment": _f((pos - neg) / sc) if sc else None, "aspects": sorted(by.get(n, []), key=lambda d: -d["mentions"])}
        for n, c, avg, sd, sc, pos, neg in base],
        "not_found": [p for p in products if p not in found]}


@router.get("/reviews")
async def reviews(product: str | None = None, min_rating: float | None = None, max_rating: float | None = None,
                  language: str | None = None, mismatch_only: bool = False, q: str | None = None,
                  limit: int = Query(25, ge=1, le=200), after_id: int = Query(0, ge=0),
                  session: AsyncSession = Depends(get_session)):
    where = ["r.workspace_id = :ws", "r.review_id > :after"]
    a: dict = {"ws": await _ws(session), "after": after_id, "lim": limit, "neg": T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF}
    if product:
        where.append("p.name = :product"); a["product"] = product
    if min_rating is not None:
        where.append("r.rating_norm >= :minr"); a["minr"] = min_rating
    if max_rating is not None:
        where.append("r.rating_norm <= :maxr"); a["maxr"] = max_rating
    if language:
        where.append("r.language = :lang"); a["lang"] = language
    if mismatch_only:
        where.append("s.mismatch_type IS NOT NULL")
    if q:
        where.append("r.tsv @@ plainto_tsquery('simple', :q)"); a["q"] = q
    rows = (await session.execute(text(f"""
        SELECT r.review_id, p.name, r.rating_norm, r.review_date, r.language, r.text_clean,
               s.text_label, s.fused_stars, s.mismatch_type
        FROM review r JOIN product p ON p.product_id = r.product_id LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE {' AND '.join(where)} ORDER BY r.review_id LIMIT :lim"""), a)).all()
    ids = [r[0] for r in rows]
    phrases: dict[int, list] = {}
    if ids:
        for rid, an, term, ev, sent in (await session.execute(text(f"""
            SELECT ra.review_id, a.name, ra.term, ra.evidence_span, ra.sentiment FROM review_aspect ra
            JOIN aspect a ON a.aspect_id = ra.aspect_id
            WHERE ra.review_id = ANY(CAST(:ids AS bigint[])) AND {NEG_OK}"""), {**a, "ids": ids})).all():
            phrases.setdefault(rid, []).append({"aspect": an, "term": term, "phrase": ev, "sentiment": sent})
    items = [{"review_id": i, "product": pn, "stars": st, "date": d, "language": lg, "text": tx, "text_label": tl,
              "fused_stars": _f(fs), "mismatch": mt, "negative_phrases": phrases.get(i, [])}
             for i, pn, st, d, lg, tx, tl, fs, mt in rows]
    return {"items": items, "next_after_id": ids[-1] if len(ids) == limit else None}


@router.get("/alerts")
async def alerts(session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    a = {"ws": ws, "spam": T.SPAM_MAX, "neg": T.NEG_MENTION, "conf": T.ASPECT_MIN_CONF}
    lo, hi = (await session.execute(text("""
        SELECT date_trunc('week', min(review_date))::date, date_trunc('week', max(review_date))::date
        FROM review WHERE workspace_id = :ws AND spam_score <= :spam AND review_date IS NOT NULL"""), a)).one()
    if lo is None:
        return {"alerts": [], "weeks": 0, "note": "No dated reviews."}
    weeks = []
    w = lo
    while w <= hi:
        weeks.append(w)
        w += timedelta(days=7)
    counts: dict[str, dict[date, int]] = {}
    for name, wk, c in (await session.execute(text(f"""
        SELECT a.name, date_trunc('week', r.review_date)::date, count(DISTINCT r.review_id) FROM review_aspect ra
        JOIN aspect a ON a.aspect_id = ra.aspect_id JOIN review r ON r.review_id = ra.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND r.review_date IS NOT NULL AND {NEG_OK}
        GROUP BY 1, 2"""), a)).all():
        counts.setdefault(name, {})[wk] = c
    out = []
    for name, by in counts.items():
        series = [by.get(x, 0) for x in weeks]
        z = spike_z(series[:-1], series[-1])
        if z is not None and z > T.SPIKE_Z and series[-1] >= T.SPIKE_MIN_COUNT:
            out.append({"aspect": name, "week": weeks[-1], "count": series[-1],
                        "usual": round(mean(series[:-1]), 2), "z": round(z, 2)})
    enough = len(weeks) - 1 >= T.SPIKE_MIN_WEEKS
    return {"alerts": sorted(out, key=lambda d: -d["z"]), "weeks": len(weeks), "enough_history": enough,
            "note": ("Latest week compared with earlier weeks." if enough else
                     f"Needs at least {T.SPIKE_MIN_WEEKS} earlier weeks of dated reviews before any alert can fire.")}
