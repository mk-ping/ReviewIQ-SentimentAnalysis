import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.models import Product, Review, ReviewScore


async def true_rating(session: AsyncSession, workspace_id: int = 1) -> list[dict]:
    rows = (
        await session.execute(
            select(Product.name, Review.rating_norm, ReviewScore.fused_stars, ReviewScore.mismatch_type)
            .join(Review, Review.product_id == Product.product_id)
            .join(ReviewScore, ReviewScore.review_id == Review.review_id)
            .where(Review.workspace_id == workspace_id, Review.rating_norm.is_not(None),
                   ReviewScore.fused_stars.is_not(None), Review.spam_score <= T.SPAM_MAX)
        )
    ).all()
    by: dict[str, list] = {}
    for name, r, f, mm in rows:
        by.setdefault(name, []).append((r, f, mm))
    if not by:
        return []
    c_all = float(np.mean([f for v in by.values() for _, f, _ in v]))
    rng = np.random.default_rng(42)
    m = T.TRUE_RATING_M
    out = []
    for name, v in sorted(by.items()):
        r = np.array([x[0] for x in v], dtype=float)
        f = np.array([x[1] for x in v], dtype=float)
        n = len(v)
        w = n / (n + m)
        shown = float(r.mean())
        tr = float(w * f.mean() + (1 - w) * c_all)
        idx = rng.integers(0, n, size=(T.BOOTSTRAP_N, n))
        gaps = w * f[idx].mean(axis=1) + (1 - w) * c_all - r[idx].mean(axis=1)
        lo, hi = float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))
        out.append({
            "product": name, "n": n, "low_sample": n < T.LOW_SAMPLE,
            "shown_avg": round(shown, 2), "true_rating": round(tr, 2), "gap": round(tr - shown, 2),
            "ci_low": round(lo, 2), "ci_high": round(hi, 2), "clear_difference": n >= T.LOW_SAMPLE and not (lo <= 0 <= hi),
            "mismatch_share": round(sum(1 for x in v if x[2]) / n, 2),
        })
    return out
