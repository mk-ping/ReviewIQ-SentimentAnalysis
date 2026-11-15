from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import _ws
from app.db.session import get_session
from app.models import UploadBatch
from app.services.export_csv import build_csv, short_model, vote_label

router = APIRouter(tags=["sentiment"])


@router.get("/sentiment/uploads")
async def sentiment_uploads(session: AsyncSession = Depends(get_session)):
    """Every upload with how far it has been analysed, so a manager can return to earlier results."""
    ws = await _ws(session)
    rows = (await session.execute(text("""
        SELECT b.batch_id, b.file_name, b.status, b.created_at, b.rows_total, b.rows_rejected,
               count(r.review_id) AS reviews, count(s.review_id) AS scored,
               count(u.review_id) AS aspects_done, count(e.review_id) AS embedded,
               count(*) FILTER (WHERE s.text_label = 'pos') AS pos,
               count(*) FILTER (WHERE s.text_label = 'neu') AS neu,
               count(*) FILTER (WHERE s.text_label = 'neg') AS neg
        FROM upload_batch b
        LEFT JOIN review r ON r.batch_id = b.batch_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        LEFT JOIN review_aspect_run u ON u.review_id = r.review_id
        LEFT JOIN review_embedding e ON e.review_id = r.review_id
        WHERE b.workspace_id = :ws GROUP BY b.batch_id ORDER BY b.batch_id DESC"""), {"ws": ws})).mappings().all()
    return {"uploads": [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]}


@router.get("/uploads/{batch_id}/votes")
async def model_votes(batch_id: int, session: AsyncSession = Depends(get_session)):
    """What each model voted for this upload (its own most likely class per review)."""
    if await session.get(UploadBatch, batch_id) is None:
        raise HTTPException(404, "Upload not found.")
    rows = (await session.execute(text("""
        SELECT m.name, m.version, count(*) AS reviews,
               count(*) FILTER (WHERE p.p_neg >= p.p_neu AND p.p_neg >= p.p_pos) AS neg,
               count(*) FILTER (WHERE p.p_neu > p.p_neg AND p.p_neu >= p.p_pos) AS neu,
               count(*) FILTER (WHERE p.p_pos > p.p_neg AND p.p_pos > p.p_neu) AS pos,
               avg(p.expected_stars) AS avg_expected_stars
        FROM prediction p JOIN model m ON m.model_id = p.model_id JOIN review r ON r.review_id = p.review_id
        WHERE r.batch_id = :b GROUP BY m.model_id, m.name, m.version ORDER BY m.name"""), {"b": batch_id})).all()
    return {"models": [{"model": short_model(n), "version": v, "reviews": c, "neg": ng, "neu": nu, "pos": ps,
                        "avg_expected_stars": None if a is None else round(float(a), 2)} for n, v, c, ng, nu, ps, a in rows]}


@router.get("/uploads/{batch_id}/results.csv")
async def results_csv(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    rows = (await session.execute(text("""
        SELECT r.review_id, p.name, r.rating_raw, r.rating_norm, r.language, r.review_date, r.text_clean, r.spam_score,
               s.text_label, s.confidence, s.fused_stars, s.pred_stars, s.star_gap, s.mismatch_type
        FROM review r JOIN product p ON p.product_id = r.product_id
        LEFT JOIN review_score s ON s.review_id = r.review_id
        WHERE r.batch_id = :b ORDER BY r.review_id"""), {"b": batch_id})).all()
    preds = (await session.execute(text("""
        SELECT p.review_id, m.name, p.p_neg, p.p_neu, p.p_pos
        FROM prediction p JOIN model m ON m.model_id = p.model_id JOIN review r ON r.review_id = p.review_id
        WHERE r.batch_id = :b"""), {"b": batch_id})).all()
    votes: dict[int, dict[str, str]] = {}
    for rid, name, n, u, pp in preds:
        votes.setdefault(rid, {})[short_model(name)] = vote_label(n, u, pp)
    body = build_csv([tuple(r) for r in rows], votes)
    stem = (batch.file_name or f"upload_{batch_id}").rsplit(".", 1)[0][:60] or f"upload_{batch_id}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{safe}_results.csv"'})
