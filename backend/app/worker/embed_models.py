"""embed stage with a model per review: all-MiniLM-L6-v2 for English, the multilingual model for everything else.
The model name is stored on every vector, and search only compares vectors from the same model."""
import asyncio

from sqlalchemy import text as sql

from app.db.session import SessionLocal
from app.services.embeddings import embed, embed_model_for
from app.services.queue import set_progress
from app.worker.handlers import CHUNK


async def handle_embed(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        rows = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean, r.language, e.model FROM review r
            LEFT JOIN review_embedding e ON e.review_id = r.review_id
            WHERE r.batch_id = :b ORDER BY r.review_id"""), {"b": batch_id})).all()
    by_model: dict[str, list] = {}
    for rid, text, lang, cur in rows:
        want = embed_model_for(lang)
        if cur != want:
            by_model.setdefault(want, []).append((rid, text or ""))
    total = sum(len(v) for v in by_model.values())
    done = 0
    for model, items in by_model.items():
        for i in range(0, len(items), CHUNK):
            part = items[i : i + CHUNK]
            vectors = await asyncio.to_thread(embed, [t for _, t in part], model)
            batch = [{"rid": rid, "m": model, "v": "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"}
                     for (rid, _), vec in zip(part, vectors)]
            async with SessionLocal() as s:
                await s.execute(sql("""
                    INSERT INTO review_embedding (review_id, model, embedding) VALUES (:rid, :m, CAST(:v AS vector))
                    ON CONFLICT (review_id) DO UPDATE SET model = EXCLUDED.model, embedding = EXCLUDED.embedding, created_at = now()"""), batch)
                await s.commit()
                done += len(part)
                await set_progress(s, job_id, int(100 * done / total))
