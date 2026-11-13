import hashlib
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.session import get_session
from app.models import (
    ColumnMapping, ColumnProfile, IngestIssue, RawReviewStaging, SourceTemplate, UploadBatch,
)
from app.services.detection import ROLES, RoleResult, assign
from app.services.llm_mapping import suggest_mapping
from app.services.profiling import profile_column
from app.services.structure import repair
from app.services.tiebreak import apply_tiebreak

router = APIRouter(prefix="/uploads", tags=["mapping"])


def header_fingerprint(header: list[str]) -> str:
    return hashlib.sha256(
        "|".join(re.sub(r"\s+", " ", h.lower().strip()) for h in header).encode("utf-8")
    ).hexdigest()


def results_from_template(mapping: dict[str, str]) -> list[RoleResult]:
    out = []
    for role in ROLES:
        col = mapping.get(role)
        if col:
            out.append(RoleResult(role=role, column=col, confidence=1.0, method="template",
                                  evidence={"source": "template"}, alternatives=[], action="accept"))
        else:
            out.append(RoleResult(role=role, column=None, confidence=0.0, method="none", evidence={},
                                  alternatives=[], action="missing" if role == "text" else "none"))
    return out


async def load_table(session: AsyncSession, batch_id: int):
    rows = (
        await session.execute(
            select(RawReviewStaging.raw).where(RawReviewStaging.batch_id == batch_id).order_by(RawReviewStaging.row_no)
        )
    ).scalars().all()
    return [r["cells"] for r in rows]


async def llm_fallback(results: list[RoleResult], header: list[str], data: list[list[str]]) -> list[str]:
    """Plan rule: below 0.5 on the required text role, ask the local LLM; validate; still ask the user."""
    by = {r.role: r for r in results}
    text = by["text"]
    if text.column is not None and text.confidence >= 0.5:
        return []
    sug = await suggest_mapping(header, data[:5])
    if not sug:
        return ["The text column is uncertain and the local LLM gave no usable suggestion."]
    taken = {r.column for r in results if r.column and r.confidence >= 0.5 and r.role != "text"}
    changed = []
    for role, col in sug.items():
        r = by[role]
        if col in taken or not (role == "text" or r.column is None):
            continue
        for other in results:  # free the column if a weaker role was holding it
            if other is not r and other.column == col:
                other.column, other.confidence, other.method = None, 0.0, "none"
                other.evidence, other.alternatives = {}, []
                other.action = "missing" if other.role == "text" else "none"
        r.column, r.confidence, r.method, r.action = col, 0.55, "llm", "ask"
        r.evidence, r.alternatives = {"source": "llm"}, []
        taken.add(col)
        changed.append(f"{role} = {col}")
    if not changed:
        return ["The local LLM suggestion matched columns already in use, so it was ignored."]
    return [f"Local LLM suggested: {', '.join(changed)}. Please confirm."]


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

    template = (
        await session.execute(
            select(SourceTemplate).where(
                SourceTemplate.workspace_id == batch.workspace_id,
                SourceTemplate.fingerprint == header_fingerprint(header),
            )
        )
    ).scalar_one_or_none()
    use_template = (
        template is not None
        and "text" in template.mapping
        and all(col in header for col in template.mapping.values())
    )
    results = results_from_template(template.mapping) if use_template else assign(profiles)

    notes: list[str] = []
    if not use_template:
        try:
            corrs = await run_in_threadpool(apply_tiebreak, results, profiles, header, data)
            if corrs:
                notes.append("Checked against text sentiment: " + ", ".join(f"{k} {v:+.2f}" for k, v in corrs.items()))
        except Exception as e:  # never crash the mapping call
            notes.append(f"Sentiment tie-breaker skipped ({type(e).__name__}).")
        notes += await llm_fallback(results, header, data)

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
        "from_template": use_template,
        "repairs": [{"row_no": i["row_no"], "problem": i["problem"]} for i in issues],
        "notes": notes,
        "needs_confirmation": any(r.action == "ask" for r in results),
        "mapping": [
            {"role": r.role, "column": r.column, "confidence": r.confidence, "method": r.method,
             "action": r.action, "evidence": r.evidence, "alternatives": r.alternatives}
            for r in results
        ],
        "preview": data[:3],
    }
