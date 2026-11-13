"""Vector search and audit trigger checks. Needs the database; run after `alembic upgrade head`.
For the similarity part, queue an embed job first:  POST /uploads/{id}/embed  with the worker running."""
import asyncio

from sqlalchemy import text

from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as s:
        idx = (await s.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_review_embedding_hnsw'"))).scalar()
        assert idx and "hnsw" in idx and "vector_cosine_ops" in idx, idx
        print("HNSW index present")

        trig = {r[0] for r in (await s.execute(text(
            "SELECT tgname FROM pg_trigger WHERE tgname LIKE 'trg_audit_%' AND NOT tgisinternal"))).all()}
        assert trig == {"trg_audit_action", "trg_audit_upload_batch", "trg_audit_source_template"}, trig
        print("audit triggers present")

        batch = (await s.execute(text("SELECT min(batch_id) FROM upload_batch"))).scalar()
        if batch is not None:
            before = (await s.execute(text("SELECT count(*) FROM audit_log WHERE entity = 'upload_batch'"))).scalar()
            await s.execute(text("UPDATE upload_batch SET rows_ok = rows_ok + 1 WHERE batch_id = :b"), {"b": batch})
            await s.execute(text("UPDATE upload_batch SET rows_ok = rows_ok - 1 WHERE batch_id = :b"), {"b": batch})
            await s.commit()
            rows = (await s.execute(text(
                "SELECT detail FROM audit_log WHERE entity = 'upload_batch' AND entity_id = :b ORDER BY audit_id DESC LIMIT 2"),
                {"b": str(batch)})).scalars().all()
            after = (await s.execute(text("SELECT count(*) FROM audit_log WHERE entity = 'upload_batch'"))).scalar()
            assert after == before + 2, (before, after)
            assert all("rows_ok" in d and set(d["rows_ok"]) == {"old", "new"} for d in rows), rows
            print("audit trigger records field changes (old and new)")

        n = (await s.execute(text("SELECT count(*) FROM review_embedding"))).scalar()
        if n < 2:
            print(f"{n} embeddings so far: queue POST /uploads/{{id}}/embed with the worker running, then re-run for the similarity check")
            return
        src = (await s.execute(text("SELECT review_id, embedding::text FROM review_embedding ORDER BY review_id LIMIT 1"))).one()
        near = (await s.execute(text("""
            SELECT review_id, embedding <=> CAST(:q AS vector) AS d FROM review_embedding
            WHERE review_id <> :id ORDER BY embedding <=> CAST(:q AS vector) LIMIT 5"""), {"q": src[1], "id": src[0]})).all()
        assert near and all(a[1] <= b[1] for a, b in zip(near, near[1:])), near
        assert all(r[0] != src[0] for r in near)
        print(f"nearest neighbours of review {src[0]}: {[(r[0], round(1 - r[1], 3)) for r in near]}")
    print("search checks passed")


asyncio.run(main())
