from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import ColumnMapping, ColumnProfile, IngestIssue, RawReviewStaging, UploadBatch
from app.services.detection import assign
from app.services.profiling import profile_column
from app.services.structure import repair

router = APIRouter(prefix="/uploads", tags=["mapping"])


async def load_table(session: AsyncSession, batch_id: int):
    rows = (
        await session.execute(
            select(RawReviewStaging.raw).where(RawReviewStaging.batch_id == batch_id).order_by(RawReviewStaging.row_no)
        )
    ).scalars().all()
    return [r["cells"] for r in rows]


@router.get("/{batch_id}/mapping")
async def get_mapping(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")

    if batch.status == "done":
        saved = (await session.execute(select(ColumnMapping).where(ColumnMapping.batch_id == batch_id))).scalars().all()
        return {"batch_id": batch_id, "already_ingested": True, "mapping": [
            {"role": x.role, "column": x.column_name, "confidence": x.confidence, "confirmed": x.confirmed} for x in saved]}

    raw = await load_table(session, batch_id)
    header, data, issues = repair(raw)
    if not header or not data:
        raise HTTPException(422, "The file has a header but no data rows.")

    profiles = [profile_column(name, [r[i] for r in data]) for i, name in enumerate(header)]
    results = assign(profiles)

    text_result = next(r for r in results if r.role == "text")

    # replace earlier detection output for this batch (re-running is safe)
    await session.execute(delete(ColumnMapping).where(ColumnMapping.batch_id == batch_id))
    await session.execute(delete(ColumnProfile).where(ColumnProfile.batch_id == batch_id))
    await session.execute(
        delete(IngestIssue).where(IngestIssue.batch_id == batch_id, IngestIssue.problem != "Line is not valid JSON")
    )

    mapped = [r for r in results if r.column]
    if mapped:
        await session.execute(
            insert(ColumnMapping),
            [{"batch_id": batch_id, "role": r.role, "column_name": r.column, "confidence": r.confidence,
              "method": r.method, "evidence": r.evidence, "confirmed": False} for r in mapped],
        )
    await session.execute(
        insert(ColumnProfile),
        [{"batch_id": batch_id, "column_name": p.name, "dtype": "numeric" if p.numeric_share > 0.9 else "text",
          "null_rate": p.null_rate, "unique_ratio": p.unique_ratio, "avg_len": p.avg_len} for p in profiles],
    )
    if issues:
        await session.execute(
            insert(IngestIssue),
            [{"batch_id": batch_id, "row_no": i["row_no"], "field": i["field"], "problem": i["problem"],
              "action": i["action"], "original_value": i["original"]} for i in issues],
        )
    batch.status = "mapping_needed" if text_result.action != "accept" else "uploaded"
    await session.commit()

    if text_result.column is None:
        raise HTTPException(
            422,
            detail={"message": "No review text column found. Pick one of these columns:", "columns": header},
        )

    return {
        "batch_id": batch_id,
        "columns": header,
        "data_rows": len(data),
        "repairs": [{"row_no": i["row_no"], "problem": i["problem"]} for i in issues],
        "needs_confirmation": any(r.action == "ask" for r in results),
        "mapping": [
            {"role": r.role, "column": r.column, "confidence": r.confidence, "action": r.action,
             "evidence": r.evidence, "alternatives": r.alternatives}
            for r in results
        ],
        "preview": data[:3],
    }
