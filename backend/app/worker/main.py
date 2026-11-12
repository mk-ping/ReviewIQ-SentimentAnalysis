import asyncio
import os

from app.db.session import SessionLocal
from app.services.queue import claim_next, fail, finish, requeue_stale
from app.worker.handlers import HANDLERS

POLL_SECONDS = 2


async def main() -> None:
    me = os.getpid()
    print(f"[worker {me}] started, waiting for jobs")
    while True:
        async with SessionLocal() as s:
            await requeue_stale(s)
            claimed = await claim_next(s)
        if claimed is None:
            await asyncio.sleep(POLL_SECONDS)
            continue
        job_id, batch_id, stage = claimed
        print(f"[worker {me}] claimed job {job_id} (batch {batch_id}, stage {stage})")
        try:
            handler = HANDLERS.get(stage)
            if handler is None:
                raise RuntimeError(f"No handler for stage '{stage}'")
            await handler(job_id, batch_id)
            try:
                from app.services.views import refresh_views
                await refresh_views()
            except Exception as e:
                print(f"[worker {me}] view refresh failed (job kept): {e}")
            async with SessionLocal() as s:
                await finish(s, job_id)
            print(f"[worker {me}] finished job {job_id}")
        except Exception as e:
            async with SessionLocal() as s:
                await fail(s, job_id, f"{type(e).__name__}: {e}")
            print(f"[worker {me}] job {job_id} failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("worker stopped")
