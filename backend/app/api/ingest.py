import csv
import hashlib
import io
import re

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import ColumnMapping, IngestIssue, Review, SourceTemplate, UploadBatch
from app.services.ingest import IngestError, run_ingest

router = APIRouter(prefix="/uploads", tags=["ingest"])


class MappingBody(BaseModel):
    mapping: dict[str, str] | None = None


async def build_report(session: AsyncSession, batch: UploadBatch) -> dict:
    breakdown = (
        await session.execute(
            select(IngestIssue.problem, IngestIssue.action, func.count())
            .where(IngestIssue.batch_id == batch.batch_id)
            .group_by(IngestIssue.problem, IngestIssue.action)
            .order_by(func.count().desc())
        )
    ).all()
    sample = (
        await session.execute(
            select(IngestIssue.row_no, IngestIssue.field, IngestIssue.problem, IngestIssue.action, IngestIssue.original_value)
            .where(IngestIssue.batch_id == batch.batch_id)
            .order_by(IngestIssue.issue_id)
            .limit(20)
        )
    ).all()
    saved = await session.scalar(select(func.count()).select_from(Review).where(Review.batch_id == batch.batch_id)) or 0
    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "rows_total": batch.rows_total,
        "accepted": batch.rows_ok,
        "repaired": batch.rows_repaired,
        "rejected": batch.rows_rejected,
        "adds_up": batch.rows_total == batch.rows_ok + batch.rows_repaired + batch.rows_rejected,
        "reviews_saved": saved,
        "problems": [{"problem": p, "action": a, "count": c} for p, a, c in breakdown],
        "sample_issues": [
            {"row_no": r, "field": f, "problem": p, "action": a, "original": o} for r, f, p, a, o in sample
        ],
    }


@router.put("/{batch_id}/mapping")
async def confirm_mapping(
    batch_id: int,
    body: MappingBody | None = None,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    if batch.status == "done" and not force:
        return {"already_ingested": True, **await build_report(session, batch)}

    saved = (await session.execute(select(ColumnMapping).where(ColumnMapping.batch_id == batch_id))).scalars().all()
    old = {m.role: m for m in saved}
    if body and body.mapping:
        mapping = {k: v for k, v in body.mapping.items() if v}
    else:
        mapping = {m.role: m.column_name for m in saved}
    if not mapping:
        raise HTTPException(409, "No mapping yet. Call GET /uploads/{id}/mapping first, or send a mapping in the body.")

    try:
        if force:
            await session.execute(delete(Review).where(Review.batch_id == batch_id))
        batch.status = "ingesting"
        result = await run_ingest(session, batch, mapping)

        await session.execute(delete(ColumnMapping).where(ColumnMapping.batch_id == batch_id))
        rows = []
        for role, col in mapping.items():
            o = old.get(role)
            same = o is not None and o.column_name == col
            rows.append({
                "batch_id": batch_id, "role": role, "column_name": col,
                "confidence": o.confidence if same else 1.0,
                "method": o.method if same else "user",
                "evidence": o.evidence if same else {"source": "user"},
                "confirmed": True,
            })
        await session.execute(insert(ColumnMapping), rows)

        fingerprint = hashlib.sha256(
            "|".join(re.sub(r"\s+", " ", h.lower().strip()) for h in result["header"]).encode("utf-8")
        ).hexdigest()
        await session.execute(
            pg_insert(SourceTemplate)
            .values(workspace_id=batch.workspace_id, fingerprint=fingerprint, mapping=mapping)
            .on_conflict_do_update(index_elements=["workspace_id", "fingerprint"], set_={"mapping": mapping})
        )
        await session.commit()
    except IngestError as e:
        await session.rollback()
        raise HTTPException(422, str(e))
    except Exception as e:
        await session.rollback()
        await session.execute(update(UploadBatch).where(UploadBatch.batch_id == batch_id).values(status="failed"))
        await session.commit()
        raise HTTPException(500, f"Ingest failed and was rolled back: {e}")

    return {"already_ingested": False, **await build_report(session, batch)}


@router.get("/{batch_id}/report")
async def get_report(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    return await build_report(session, batch)


@router.get("/{batch_id}/rejects.csv")
async def get_rejects(batch_id: int, session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(IngestIssue.row_no, IngestIssue.field, IngestIssue.problem, IngestIssue.original_value)
            .where(IngestIssue.batch_id == batch_id, IngestIssue.action == "quarantined")
            .order_by(IngestIssue.row_no)
        )
    ).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["row_no", "field", "problem", "original_value"])
    for r in rows:
        w.writerow(list(r))
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rejects_{batch_id}.csv"},
    )
