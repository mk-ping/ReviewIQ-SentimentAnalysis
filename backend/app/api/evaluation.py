import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.core import thresholds as T
from app.db.session import get_session
from app.services import evaluation as E

router = APIRouter(tags=["evaluation"])


class LabelBody(BaseModel):
    review_id: int
    label: Literal["neg", "neu", "pos"]
    mismatch_label: bool | None = None
    source: Literal["gold", "manager"] = "gold"


def _r(x, nd=3):
    return None if x is None else round(x, nd)


@router.get("/labels/queue")
async def label_queue(source: Literal["gold", "manager"] = "gold", session: AsyncSession = Depends(get_session)):
    """Next review to label. Order is a fixed shuffle (md5 of the id), so the sample is not biased toward any product or score.
    Model predictions are not sent, so they cannot anchor the person labelling."""
    ws = await _ws(session)
    a = {"ws": ws, "src": source}
    total, done = (await session.execute(text("""
        SELECT count(*), count(g.review_id) FROM review r
        LEFT JOIN gold_label g ON g.review_id = r.review_id AND g.source = :src
        WHERE r.workspace_id = :ws"""), a)).one()
    row = (await session.execute(text("""
        SELECT r.review_id, p.name, r.rating_norm, r.text_clean, r.language FROM review r
        JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND NOT EXISTS (SELECT 1 FROM gold_label g WHERE g.review_id = r.review_id AND g.source = :src)
        ORDER BY md5(r.review_id::text) LIMIT 1"""), a)).first()
    return {"labelled": done, "total": total, "remaining": total - done,
            "item": None if row is None else {"review_id": row[0], "product": row[1], "stars": row[2], "text": row[3], "language": row[4]}}


@router.post("/labels")
async def save_label(body: LabelBody, session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    ok = (await session.execute(text("SELECT 1 FROM review WHERE review_id = :id AND workspace_id = :ws"),
                                {"id": body.review_id, "ws": ws})).scalar()
    if not ok:
        raise HTTPException(404, "Review not found.")
    await session.execute(text("""
        INSERT INTO gold_label (review_id, label, mismatch_label, source) VALUES (:id, :l, :m, :s)
        ON CONFLICT (review_id) DO UPDATE SET label = EXCLUDED.label, mismatch_label = EXCLUDED.mismatch_label,
            source = EXCLUDED.source, labelled_at = now()"""),
        {"id": body.review_id, "l": body.label, "m": body.mismatch_label, "s": body.source})
    await session.commit()
    return {"saved": True, "review_id": body.review_id}


@router.delete("/labels/{review_id}")
async def delete_label(review_id: int, session: AsyncSession = Depends(get_session)):
    await session.execute(text("DELETE FROM gold_label WHERE review_id = :id"), {"id": review_id})
    await session.commit()
    return {"deleted": True}


@router.get("/labels/export.csv")
async def export_labels(session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT g.review_id, g.label, g.mismatch_label, g.source, r.rating_norm, r.language, r.text_clean
        FROM gold_label g JOIN review r ON r.review_id = g.review_id WHERE r.workspace_id = :ws ORDER BY g.review_id"""),
        {"ws": ws})).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["review_id", "label", "mismatch_label", "source", "stars", "language", "text"])
    for r in rows:
        w.writerow(list(r))
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=gold_labels.csv"})


@router.get("/evaluation")
async def evaluation(min_labels: int = Query(30, ge=1), session: AsyncSession = Depends(get_session)):
    ws = await _ws(session)
    a = {"ws": ws}
    gold = (await session.execute(text("""
        SELECT g.review_id, g.label, g.mismatch_label, r.language, r.rating_norm, s.text_label, s.confidence, s.mismatch_type
        FROM gold_label g JOIN review r ON r.review_id = g.review_id LEFT JOIN review_score s ON s.review_id = g.review_id
        WHERE r.workspace_id = :ws AND g.source = 'gold'"""), a)).all()
    n = len(gold)
    base = {"labelled": n, "low_sample": n < min_labels, "min_labels": min_labels}
    if n == 0:
        return {**base, "note": "No gold labels yet. Label reviews on the Gold Labels page first. Accuracy is measured against these, never against stars."}

    by_id = {g[0]: g for g in gold}
    truth = {g[0]: g[1] for g in gold}

    def block(ids: list[int], preds: dict[int, str]) -> dict:
        ids = [i for i in ids if i in preds]
        gl, pl = [truth[i] for i in ids], [preds[i] for i in ids]
        return {"n": len(ids), "macro_f1": _r(E.macro_f1(gl, pl)), "accuracy": _r(E.accuracy(gl, pl)),
                "macro_f1_ci": [_r(x) for x in E.bootstrap_macro_f1(gl, pl) or ()] or None,
                "per_class": {c: {k: _r(v) if isinstance(v, float) else v for k, v in d.items()} for c, d in E.per_class(gl, pl).items()},
                "confusion": E.confusion(gl, pl)}

    models = []
    preds_by_model: dict[str, dict[int, str]] = {}
    for rid, name, pn, pu, pp in (await session.execute(text("""
        SELECT pr.review_id, m.name, pr.p_neg, pr.p_neu, pr.p_pos FROM prediction pr
        JOIN model m ON m.model_id = pr.model_id JOIN gold_label g ON g.review_id = pr.review_id AND g.source = 'gold'
        JOIN review r ON r.review_id = pr.review_id WHERE r.workspace_id = :ws"""), a)).all():
        preds_by_model.setdefault(name, {})[rid] = E.argmax_label(pn, pu, pp)
    for name, preds in sorted(preds_by_model.items()):
        models.append({"model": name, **block(list(truth), preds)})

    stars_pred = {i: E.stars_to_label(g[4]) for i, g in by_id.items() if g[4] is not None}
    stars_block = block(list(truth), stars_pred)

    fused_pred = {i: g[5] for i, g in by_id.items() if g[5]}
    fused_block = block(list(truth), fused_pred)

    langs = {}
    for lang in sorted({g[3] or "unknown" for g in gold}):
        ids = [i for i, g in by_id.items() if (g[3] or "unknown") == lang]
        main = next(iter(preds_by_model.values()), {})
        b = block(ids, main)
        langs[lang] = {"n": b["n"], "macro_f1": b["macro_f1"], "low_sample": b["n"] < 10}

    mm_rows = [(g[2], g[7] is not None) for g in gold if g[2] is not None and g[5] is not None]
    mismatch = E.binary_precision_recall([m for m, _ in mm_rows], [f for _, f in mm_rows])
    mismatch = {k: _r(v) if isinstance(v, float) else v for k, v in mismatch.items()}

    cal_rows = [(g[6], g[5] == g[1]) for g in gold if g[6] is not None and g[5]]
    calib = E.calibration([c for c, _ in cal_rows], [k for _, k in cal_rows])

    return {
        **base,
        "text_models": models,
        "fused_text_label": fused_block,
        "stars_only": stars_block,
        "by_language": langs,
        "mismatch_flags": mismatch,
        "calibration": calib,
        "gold_vs_stars_disagreement": _r(1 - (E.accuracy([truth[i] for i in stars_pred], [stars_pred[i] for i in stars_pred]) or 0)) if stars_pred else None,
        "note": ("Measured on hand-labelled reviews, not on stars. "
                 + ("Fewer labels than the minimum, so treat every number as a first look. " if n < min_labels else "")
                 + "Thresholds are starting values until tuned on this set."),
    }
