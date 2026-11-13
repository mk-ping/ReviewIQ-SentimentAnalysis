import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.db.session import get_session
from app.models import IngestIssue, RawReviewStaging, UploadBatch, Workspace
from app.services.file_detect import detect
from app.services.readers import UnsupportedFormat, read_table

router = APIRouter(prefix="/uploads", tags=["uploads"])

EXT = {"csv": ".csv", "tsv": ".tsv", "xlsx": ".xlsx", "json": ".json", "jsonl": ".jsonl", "txt": ".txt", "pdf": ".pdf", "xml": ".xml"}


async def default_workspace_id(session: AsyncSession) -> int:
    ws = (
        await session.execute(select(Workspace).order_by(Workspace.workspace_id).limit(1))
    ).scalar_one_or_none()
    if ws is None:
        ws = Workspace(name=settings.default_workspace_name)
        session.add(ws)
        await session.flush()
    return ws.workspace_id


@router.post("")
async def create_upload(
    file: UploadFile | None = File(None),
    pasted_text: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    if file is None and not pasted_text:
        raise HTTPException(400, "Send a file, or pasted text in the 'pasted_text' field.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if file is not None:
        data = await file.read(max_bytes + 1)
        name = file.filename or "upload"
    else:
        data = pasted_text.encode("utf-8")
        name = "pasted.txt"

    if len(data) > max_bytes:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")

    det = detect(data)
    if det.error:
        raise HTTPException(422, det.error)

    try:
        result = await run_in_threadpool(read_table, data, det)
    except UnsupportedFormat as e:
        raise HTTPException(422, str(e))
    except Exception as e:  # never crash: report what went wrong
        raise HTTPException(422, f"Could not read this {det.format} file: {e}")

    if not result.rows:
        raise HTTPException(422, "No rows could be read from this file.")

    file_hash = hashlib.sha256(data).hexdigest()
    workspace_id = await default_workspace_id(session)

    existing = (
        await session.execute(
            select(UploadBatch)
            .where(
                UploadBatch.workspace_id == workspace_id,
                UploadBatch.file_hash == file_hash,
                UploadBatch.status != "failed",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        await session.commit()
        return {
            "batch_id": existing.batch_id,
            "duplicate": True,
            "message": "This exact file was already uploaded.",
            "format": existing.format,
            "rows_total": existing.rows_total,
        }

    batch = UploadBatch(
        workspace_id=workspace_id,
        file_name=name,
        file_hash=file_hash,
        format=det.format,
        status="uploaded",
        rows_total=len(result.rows),
    )
    session.add(batch)
    await session.flush()

    rows = [
        {"batch_id": batch.batch_id, "row_no": i, "raw": {"cells": r}}
        for i, r in enumerate(result.rows, start=1)
    ]
    for i in range(0, len(rows), 2000):
        await session.execute(insert(RawReviewStaging), rows[i : i + 2000])

    if result.issues:
        await session.execute(
            insert(IngestIssue),
            [
                {
                    "batch_id": batch.batch_id,
                    "row_no": row_no,
                    "problem": problem,
                    "action": "quarantined",
                    "original_value": original,
                }
                for row_no, problem, original in result.issues
            ],
        )
        batch.rows_rejected = len(result.issues)

    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{batch.batch_id}_{file_hash[:12]}{EXT.get(det.format, '.bin')}").write_bytes(data)

    await session.commit()

    return {
        "batch_id": batch.batch_id,
        "duplicate": False,
        "file_name": name,
        "format": det.format,
        "encoding": det.encoding,
        "delimiter": det.delimiter,
        "rows_total": len(result.rows),
        "issues": len(result.issues),
        "notes": getattr(result, "notes", []),
        "preview": result.rows[:6],
    }


@router.get("/{batch_id}")
async def get_upload(batch_id: int, session: AsyncSession = Depends(get_session)):
    batch = await session.get(UploadBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "Upload not found.")
    rows = (
        await session.execute(
            select(RawReviewStaging.row_no, RawReviewStaging.raw)
            .where(RawReviewStaging.batch_id == batch_id)
            .order_by(RawReviewStaging.row_no)
            .limit(6)
        )
    ).all()
    return {
        "batch_id": batch.batch_id,
        "file_name": batch.file_name,
        "format": batch.format,
        "status": batch.status,
        "rows_total": batch.rows_total,
        "rows_rejected": batch.rows_rejected,
        "preview": [r.raw["cells"] for r in rows],
    }
