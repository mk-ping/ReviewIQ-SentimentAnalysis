from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import FILT, _args, _f, _ws
from app.core import thresholds as T
from app.db.session import get_session
from app.services.distribution import GAP_BUCKETS, fold
from app.services.export_csv import short_model

router = APIRouter(tags=["distribution"])

SCORED = """FROM review r JOIN product p ON p.product_id = r.product_id
            JOIN review_score s ON s.review_id = r.review_id
            WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.text_label IS NOT NULL""" + FILT


@router.get("/sentiment-distribution")
async def sentiment_distribution(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                                 session: AsyncSession = Depends(get_session)):
    """How many reviews are positive, neutral and negative: overall, by star level, product, aspect and language."""
    a = _args(await _ws(session), product, date_from, date_to)
    ex = session.execute
    overall = (await ex(text(f"SELECT 'all', s.text_label, count(*) {SCORED} GROUP BY 2"), a)).all()
    by_star = (await ex(text(f"""SELECT round(r.rating_norm::numeric)::int, s.text_label, count(*) {SCORED}
                                 AND r.rating_norm IS NOT NULL GROUP BY 1, 2"""), a)).all()
    by_product = (await ex(text(f"SELECT p.name, s.text_label, count(*) {SCORED} GROUP BY 1, 2"), a)).all()
    by_lang = (await ex(text(f"SELECT coalesce(r.language, 'unknown'), s.text_label, count(*) {SCORED} GROUP BY 1, 2"), a)).all()
    asp = dict(a, conf=T.ASPECT_MIN_CONF, thr=-T.NEG_MENTION)
    by_aspect = (await ex(text("""
        SELECT x.name, CASE WHEN ra.sentiment >= :thr THEN 'pos' WHEN ra.sentiment <= -:thr THEN 'neg' ELSE 'neu' END, count(*)
        FROM review_aspect ra JOIN aspect x ON x.aspect_id = ra.aspect_id
        JOIN review r ON r.review_id = ra.review_id JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.confidence >= :conf""" + FILT + " GROUP BY 1, 2"), asp)).all()
    tot = fold(overall)
    n = tot[0]["n"] if tot else 0
    stars = {d["key"]: d for d in fold(by_star)}
    return {
        "n": n, "low_sample": n < T.LOW_SAMPLE,
        "overall": tot[0] if tot else None,
        "by_star": [stars.get(s, {"key": s, "pos": 0, "neu": 0, "neg": 0, "n": 0, "pos_share": 0, "neu_share": 0, "neg_share": 0}) for s in range(1, 6)],
        "by_product": fold(by_product, keep=15),
        "by_aspect": fold(by_aspect),
        "by_language": fold(by_lang),
        "note": "Review labels come from the weighted ensemble. Aspect counts are sentence mentions, so one review can appear in several aspects.",
    }


GAP_CASE = """CASE WHEN abs(s.fused_stars - r.rating_norm) < 0.5 THEN 3
       WHEN s.fused_stars > r.rating_norm THEN 3 + CASE WHEN abs(s.fused_stars - r.rating_norm) < 1 THEN 1
                                                        WHEN abs(s.fused_stars - r.rating_norm) < 2 THEN 2 ELSE 3 END
       ELSE 3 - CASE WHEN abs(s.fused_stars - r.rating_norm) < 1 THEN 1
                     WHEN abs(s.fused_stars - r.rating_norm) < 2 THEN 2 ELSE 3 END END"""


def _matrix(rows) -> list[list[int]]:
    m = [[0] * 5 for _ in range(5)]
    for act, other, n in rows:
        if act and other and 1 <= act <= 5 and 1 <= other <= 5:
            m[act - 1][other - 1] = int(n)
    return m


@router.get("/star-gap")
async def star_gap(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                   session: AsyncSession = Depends(get_session)):
    """Fused stars against customer stars. Gap = fused minus customer: above 0 is under-rated, below 0 is over-rated."""
    a = _args(await _ws(session), product, date_from, date_to)
    base = SCORED + " AND s.fused_stars IS NOT NULL AND r.rating_norm IS NOT NULL"
    n, mean, mabs, under, over = (await session.execute(text(f"""
        SELECT count(*), avg(s.fused_stars - r.rating_norm), avg(abs(s.fused_stars - r.rating_norm)),
               count(*) FILTER (WHERE s.mismatch_type = 'underrated'), count(*) FILTER (WHERE s.mismatch_type = 'overrated')
        {base}"""), a)).one()
    bk = dict((await session.execute(text(f"SELECT {GAP_CASE} AS b, count(*) {base} GROUP BY 1"), a)).all())
    per = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, count(*), avg(r.rating_norm), avg(s.fused_stars),
               count(*) FILTER (WHERE s.mismatch_type = 'underrated'), count(*) FILTER (WHERE s.mismatch_type = 'overrated')
        {base} GROUP BY 1 ORDER BY 1"""), a)).all()
    fm = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, round(s.fused_stars::numeric)::int, count(*) {base} GROUP BY 1, 2"""), a)).all()
    pm = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, round(s.pred_stars::numeric)::int, count(*) {base} AND s.pred_stars IS NOT NULL GROUP BY 1, 2"""), a)).all()
    return {
        "n": n, "low_sample": n < T.LOW_SAMPLE, "mean_gap": _f(mean), "mean_abs_gap": _f(mabs),
        "underrated": under, "overrated": over,
        "buckets": [{"label": GAP_BUCKETS[i], "count": int(bk.get(i, 0))} for i in range(7)],
        "by_star": [{"stars": s, "reviews": c, "avg_actual": _f(x), "avg_fused": _f(f), "underrated": u, "overrated": o}
                    for s, c, x, f, u, o in per],
        "fused_matrix": _matrix(fm), "predicted_matrix": _matrix(pm),
        "predicted_n": sum(int(c) for _, _, c in pm),
        "note": "Rows are the customer's stars, columns are what the model says. Predicted stars are not available for Hindi and Hinglish.",
    }


@router.get("/model-comparison")
async def model_comparison(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                           session: AsyncSession = Depends(get_session)):
    """Each model's own votes next to the ensemble, and how often each agrees with the ensemble and with the stars."""
    a = _args(await _ws(session), product, date_from, date_to)
    star = "CASE WHEN round(r.rating_norm::numeric) >= 4 THEN 'pos' WHEN round(r.rating_norm::numeric) = 3 THEN 'neu' ELSE 'neg' END"
    vote = ("CASE WHEN p.p_neg >= p.p_neu AND p.p_neg >= p.p_pos THEN 'neg' "
            "WHEN p.p_neu > p.p_neg AND p.p_neu >= p.p_pos THEN 'neu' ELSE 'pos' END")
    rows = (await session.execute(text(f"""
        SELECT m.name, count(*),
               count(*) FILTER (WHERE {vote} = 'neg'), count(*) FILTER (WHERE {vote} = 'neu'), count(*) FILTER (WHERE {vote} = 'pos'),
               avg(p.expected_stars),
               count(*) FILTER (WHERE {vote} = s.text_label),
               count(*) FILTER (WHERE r.rating_norm IS NOT NULL), count(*) FILTER (WHERE r.rating_norm IS NOT NULL AND {vote} = {star})
        FROM prediction p JOIN model m ON m.model_id = p.model_id
        JOIN review r ON r.review_id = p.review_id JOIN product pr ON pr.product_id = r.product_id
        JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.text_label IS NOT NULL
          AND (CAST(:product AS text) IS NULL OR pr.name = CAST(:product AS text))
          AND (CAST(:d1 AS date) IS NULL OR r.review_date >= CAST(:d1 AS date))
          AND (CAST(:d2 AS date) IS NULL OR r.review_date <= CAST(:d2 AS date))
        GROUP BY m.model_id, m.name ORDER BY m.name"""), a)).all()
    ens = (await session.execute(text(f"""
        SELECT count(*), count(*) FILTER (WHERE s.text_label = 'neg'), count(*) FILTER (WHERE s.text_label = 'neu'),
               count(*) FILTER (WHERE s.text_label = 'pos'), count(*) FILTER (WHERE r.rating_norm IS NOT NULL),
               count(*) FILTER (WHERE r.rating_norm IS NOT NULL AND s.text_label = {star}) {SCORED}"""), a)).one()
    sh = lambda x, d: _f(x / d, 3) if d else None  # noqa: E731
    models = [{"model": short_model(n), "reviews": c, "neg": ng, "neu": nu, "pos": ps,
               "avg_expected_stars": _f(ex), "agree_with_ensemble": sh(ag, c), "agree_with_stars": sh(st_ok, st_n)}
              for n, c, ng, nu, ps, ex, ag, st_n, st_ok in rows]
    models.append({"model": "Ensemble (final)", "reviews": ens[0], "neg": ens[1], "neu": ens[2], "pos": ens[3],
                   "avg_expected_stars": None, "agree_with_ensemble": 1.0 if ens[0] else None, "agree_with_stars": sh(ens[5], ens[4])})
    return {"models": models, "note": "Agreement with stars is only a rough guide: stars are noisy, which is why gold labels decide the weights."}
