from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _f, _ws
from app.core import thresholds as T
from app.db.session import get_session

router = APIRouter(tags=["quality"])


@router.get("/data-quality")
async def data_quality(session: AsyncSession = Depends(get_session)):
    """What came in, what was repaired or rejected, and how clean the stored reviews are."""
    ws = await _ws(session)
    a = {"ws": ws, "spam": T.SPAM_MAX}
    up = (await session.execute(text("""
        SELECT count(*), coalesce(sum(rows_total), 0), coalesce(sum(rows_ok), 0), coalesce(sum(rows_repaired), 0),
               coalesce(sum(rows_rejected), 0) FROM upload_batch WHERE workspace_id = :ws"""), a)).one()
    rv = (await session.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE spam_score > :spam), coalesce(sum(dup_count - 1), 0),
               count(*) FILTER (WHERE rating_norm IS NULL), count(*) FILTER (WHERE review_date IS NULL),
               count(s.review_id), count(*) FILTER (WHERE r.language IS NULL)
        FROM review r LEFT JOIN review_score s ON s.review_id = r.review_id WHERE r.workspace_id = :ws"""), a)).one()
    langs = (await session.execute(text("""
        SELECT coalesce(language, 'unknown'), count(*) FROM review WHERE workspace_id = :ws GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""), a)).all()
    n_files, total, ok, repaired, rejected = up
    n, spam, dups, no_rating, no_date, scored, no_lang = rv
    pct = lambda x: _f(100 * x / n, 1) if n else None  # noqa: E731
    return {
        "files": n_files, "rows_in_files": int(total), "accepted": int(ok), "repaired": int(repaired), "rejected": int(rejected),
        "reconciles": int(ok) + int(repaired) + int(rejected) == int(total),
        "reviews": n, "spam": spam, "spam_pct": pct(spam), "duplicates_removed": int(dups),
        "missing_rating": no_rating, "missing_rating_pct": pct(no_rating), "missing_date": no_date, "missing_date_pct": pct(no_date),
        "scored": scored, "scored_pct": pct(scored), "language_unknown": no_lang,
        "languages": [{"language": l, "reviews": c} for l, c in langs],
        "note": "Accepted + repaired + rejected should equal the rows in the files: nothing is dropped without a record.",
    }


@router.get("/review-flags")
async def review_flags(session: AsyncSession = Depends(get_session)):
    """Patterns that can mean fake or pushed reviews: bursts, repeated text, one author, and rating outliers."""
    ws = await _ws(session)
    a = {"ws": ws, "z": T.SPIKE_Z, "minc": T.SPIKE_MIN_COUNT}
    ex = session.execute
    bursts = (await ex(text("""
        WITH d AS (
          SELECT review_date AS day, CASE WHEN rating_norm >= 4.5 THEN 'five_star' ELSE 'one_star' END AS kind, count(*) AS c
          FROM review WHERE workspace_id = :ws AND review_date IS NOT NULL AND (rating_norm >= 4.5 OR rating_norm <= 1.5)
          GROUP BY 1, 2),
        st AS (SELECT kind, avg(c) AS m, coalesce(nullif(stddev_pop(c), 0), 1) AS sd, count(*) AS days FROM d GROUP BY kind)
        SELECT d.day, d.kind, d.c, st.m, st.sd FROM d JOIN st USING (kind)
        WHERE st.days >= 5 AND d.c >= :minc AND d.c > st.m + :z * st.sd ORDER BY (d.c - st.m) / st.sd DESC LIMIT 10"""), a)).all()
    same_text = (await ex(text("""
        SELECT left(text_clean, 140), count(*), count(DISTINCT product_id), count(DISTINCT review_date)
        FROM review WHERE workspace_id = :ws AND length(text_clean) >= 15
        GROUP BY text_clean HAVING count(*) > 1 ORDER BY count(*) DESC LIMIT 10"""), a)).all()
    authors = (await ex(text("""
        SELECT left(extra ->> 'author', 40), count(*), count(DISTINCT product_id), avg(rating_norm),
               count(*) FILTER (WHERE rating_norm >= 4.5)
        FROM review WHERE workspace_id = :ws AND coalesce(extra ->> 'author', '') <> ''
        GROUP BY extra ->> 'author' HAVING count(*) >= 3 ORDER BY count(*) DESC LIMIT 10"""), a)).all()
    has_author = await session.scalar(text(
        "SELECT count(*) FROM review WHERE workspace_id = :ws AND coalesce(extra ->> 'author', '') <> ''"), a)
    outliers = (await ex(text("""
        WITH m AS (SELECT product_id, avg(rating_norm) AS mean, count(rating_norm) AS n FROM review
                   WHERE workspace_id = :ws GROUP BY product_id)
        SELECT r.review_id, p.name, r.rating_norm, m.mean, left(r.text_clean, 200)
        FROM review r JOIN m ON m.product_id = r.product_id JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND m.n >= 10 AND r.rating_norm IS NOT NULL AND abs(r.rating_norm - m.mean) >= 3
        ORDER BY abs(r.rating_norm - m.mean) DESC LIMIT 10"""), a)).all()
    return {
        "bursts": [{"day": str(d), "kind": k, "reviews": c, "usual": _f(m, 1)} for d, k, c, m, sd in bursts],
        "same_text": [{"text": t, "reviews": c, "products": p, "days": dd} for t, c, p, dd in same_text],
        "authors": [{"author": au, "reviews": c, "products": p, "avg_rating": _f(r), "five_star": f} for au, c, p, r, f in authors],
        "author_column_found": (has_author or 0) > 0,
        "outliers": [{"review_id": i, "product": pn, "stars": _f(r, 1), "product_average": _f(mean), "text": tx} for i, pn, r, mean, tx in outliers],
        "note": "Flags are leads to check, not proof. A burst is a day with far more 5 star or 1 star reviews than usual.",
    }
