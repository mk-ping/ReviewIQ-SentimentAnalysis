import asyncio

import httpx
from sqlalchemy import and_, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.aspect_config import CATEGORIES
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Aspect, MLModel, Prediction, Review, ReviewAspect, ReviewAspectRun, UploadBatch,
)
from app.services import aspects, sentiment
from app.services.fusion import score_batch
from app.services.queue import set_progress

CHUNK = 32


async def _aspect_ids(s, workspace_id: int, names: list[str] | None = None) -> dict[str, int]:
    names = list(CATEGORIES) if names is None else names
    if names:
        await s.execute(
            pg_insert(Aspect)
            .values([{"workspace_id": workspace_id, "name": n} for n in names])
            .on_conflict_do_nothing(index_elements=["workspace_id", "name"])
        )
        await s.commit()
    rows = (await s.execute(select(Aspect.name, Aspect.aspect_id).where(Aspect.workspace_id == workspace_id))).all()
    return {name: aid for name, aid in rows}


async def handle_issues(job_id: int, batch_id: int) -> None:
    from app.services.issues import rebuild_issues

    async with SessionLocal() as s:
        ws = await s.scalar(select(UploadBatch.workspace_id).where(UploadBatch.batch_id == batch_id))
        await set_progress(s, job_id, 5)
    async with SessionLocal() as s:
        n = await rebuild_issues(s, ws)
    print(f"[issues] {n} issues built for workspace {ws}")


from app.worker.scoring import handle_score_all

from app.worker.aspects_sbert import handle_aspects as handle_aspects_sentences
from app.worker.embed_models import handle_embed as handle_embed_models


HANDLERS = {"score": handle_score_all, "aspects": handle_aspects_sentences, "issues": handle_issues, "embed": handle_embed_models}
# retired-handlers-removed: the review-level LLM aspect stage, single-model score and old embed stage live in scoring.py, aspects_sbert.py, embed_models.py

from app.worker.scoring import handle_score_all  # noqa: E402
HANDLERS["score"] = handle_score_all
