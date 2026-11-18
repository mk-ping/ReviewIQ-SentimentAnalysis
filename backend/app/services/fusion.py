from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.models import MLModel, Prediction, Review, ReviewScore
from app.services.routing import MEMBERS, group_of


def ensemble(preds: list[tuple], weights: list[float]) -> tuple[float, float, float]:
    """Weighted average of probabilities: sum(w x p) / sum(w)."""
    tot = sum(weights)
    return tuple(sum(w * p[i] for w, p in zip(weights, preds)) / tot for i in range(3))


def fuse(p_neg: float, p_neu: float, p_pos: float, expected: float | None, stars: float | None) -> dict:
    """Original formulas (study guide 5.12 to 5.14). The mismatch rule is the original confidence rule."""
    conf = max(p_neg, p_neu, p_pos)
    label = "neg" if conf == p_neg else ("neu" if conf == p_neu else "pos")
    out = {"text_label": label, "confidence": round(conf, 4), "fused_stars": None,
           "pred_stars": expected, "star_gap": None, "mismatch_type": None}
    if stars is None:
        return out
    text_score = p_pos - p_neg
    star_score = (stars - 3) / 2
    w = min(max(conf, T.FUSION_W_MIN), T.FUSION_W_MAX)
    out["fused_stars"] = round(3 + 2 * (w * text_score + (1 - w) * star_score), 3)
    if expected is not None:
        out["star_gap"] = round(expected - stars, 3)
    if conf >= T.MISMATCH_MIN_CONF and abs(text_score - star_score) >= T.MISMATCH_DIFF:
        out["mismatch_type"] = "underrated" if text_score > star_score else "overrated"
    return out


async def score_batch(session: AsyncSession, batch_id: int) -> int:
    """Per review: take the predictions of the models in its route group, average them with the group's weights
    (equal weights when the group has fewer than 100 validation reviews), then fuse with the stars."""
    from app.services import sentiment  # imported here so fuse() and ensemble() stay light
    from app.services import stacker

    key_of = {(c["name"], c["version"]): k for k, c in sentiment.registry().items()}
    mkey = {mid: key_of[(n, v)] for mid, n, v in
            (await session.execute(select(MLModel.model_id, MLModel.name, MLModel.version))).all() if (n, v) in key_of}
    wt: dict[tuple, float] = {}
    for g, mid, w, nv in (await session.execute(text("SELECT route_group, model_id, weight, n_val FROM model_weight"))).all():
        if mid in mkey and nv >= T.MIN_VAL_PER_GROUP:
            wt[(g, mkey[mid])] = float(w)
    rows = (
        await session.execute(
            select(Review.review_id, Review.rating_norm, Review.language, Review.text_clean, Prediction.model_id,
                   Prediction.p_neg, Prediction.p_neu, Prediction.p_pos, Prediction.expected_stars)
            .join(Prediction, Prediction.review_id == Review.review_id)
            .where(Review.batch_id == batch_id)
        )
    ).all()
    by: dict[int, dict] = {}
    for rid, st, lang, txt, mid, n, u, p, e in rows:
        k = mkey.get(mid)
        if k is None:
            continue
        d = by.setdefault(rid, {"stars": st, "group": group_of(lang), "text": txt, "preds": {}})
        d["preds"][k] = (n, u, p, e)
    payload = []
    for rid, d in by.items():
        g = d["group"]
        keys = [k for k in d["preds"] if k in MEMBERS[g]]
        if not keys:
            continue
        ws = [wt.get((g, k)) for k in keys]
        if any(w is None for w in ws):
            ws = [1.0] * len(keys)
        n, u, p = ensemble([d["preds"][k][:3] for k in keys], ws)
        n, u, p = stacker.refine(g, {k: d["preds"][k][:3] for k in keys}, (n, u, p), text=d["text"])   # learned combination, only when it passed its gate
        expected = d["preds"]["nlptown"][3] if "nlptown" in keys else None
        payload.append({"review_id": rid, **fuse(n, u, p, expected, d["stars"])})
    cols = ["text_label", "confidence", "fused_stars", "pred_stars", "star_gap", "mismatch_type"]
    for i in range(0, len(payload), 2000):
        stmt = pg_insert(ReviewScore)
        stmt = stmt.on_conflict_do_update(
            index_elements=["review_id"],
            set_={**{c: stmt.excluded[c] for c in cols}, "scored_at": func.now()},
        )
        await session.execute(stmt, payload[i : i + 2000])
    await session.commit()
    return len(payload)
