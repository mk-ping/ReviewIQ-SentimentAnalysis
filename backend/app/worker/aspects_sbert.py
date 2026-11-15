"""aspects stage: sentence-level aspects. Replaces the review-level LLM stage; the LLM no longer tags anything."""
import asyncio

from sqlalchemy import delete, func, select, text as sql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import thresholds as T
from app.db.session import SessionLocal
from app.models import Review, ReviewAspect, ReviewAspectRun, UploadBatch
from app.services import embeddings, sentence_aspects as SA, sentiment
from app.services.queue import set_progress
from app.worker.handlers import CHUNK, _aspect_ids

_cents: dict = {}


def _cents_for(model: str) -> dict:
    if model not in _cents:
        _cents[model] = SA.centroids(lambda t: embeddings.embed(t, model))
    return _cents[model]


def _analyse(part: list[tuple]) -> list[dict]:
    """part = [(review_id, text, language)]. Returns sentence dicts with aspect, method, sim, sent_score, conf."""
    items = []
    for rid, text, lang in part:
        for idx, s in enumerate(SA.split_sentences(text or "")):
            items.append({"review_id": rid, "idx": idx, "sentence": s, "lang": lang,
                          "english": SA.sentiment_model_for(lang) == "roberta"})
    out = []
    for english in (True, False):
        grp = [i for i in items if i["english"] == english]
        if not grp:
            continue
        model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
        vecs = embeddings.embed([i["sentence"] for i in grp], model)
        sims = SA.similarities(vecs, _cents_for(model))
        tagged = []
        for i, sm in zip(grp, sims):
            for aspect, method, sim in SA.tag(sm, i["sentence"]):
                tagged.append({**i, "aspect": aspect, "method": method, "sim": sim, "sent_score": None, "conf": 0.0})
        need = [t for t in tagged if t["aspect"] != SA.GENERAL]
        if need:
            probs = sentiment.predict([t["sentence"] for t in need], model="roberta" if english else "xlmr")
            for t, (n, u, p, _e) in zip(need, probs):
                t["sent_score"], t["conf"] = p - n, max(n, u, p)
        out.extend(tagged)
    return out


async def handle_aspects(job_id: int, batch_id: int) -> None:
    async with SessionLocal() as s:
        await set_progress(s, job_id, 0)
        ws = await s.scalar(select(UploadBatch.workspace_id).where(UploadBatch.batch_id == batch_id))
        ids = await _aspect_ids(s, ws)
        pending = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean, r.language FROM review r
            LEFT JOIN sentence_aspect_run u ON u.review_id = r.review_id
            WHERE r.batch_id = :b AND u.review_id IS NULL ORDER BY r.review_id"""), {"b": batch_id})).all()
    total = len(pending)
    for i in range(0, total, CHUNK):
        part = pending[i : i + CHUNK]
        rows = await asyncio.to_thread(_analyse, [tuple(p) for p in part])
        by: dict[int, list[dict]] = {}
        for r in rows:
            by.setdefault(r["review_id"], []).append(r)
        rids = [p[0] for p in part]
        async with SessionLocal() as s:
            await s.execute(delete(ReviewAspect).where(ReviewAspect.review_id.in_(rids)))
            await s.execute(sql("DELETE FROM sentence_aspect WHERE review_id = ANY(CAST(:ids AS bigint[]))"), {"ids": rids})
            sent_rows = [{"review_id": r["review_id"], "sent_idx": r["idx"], "sentence": r["sentence"], "aspect": r["aspect"],
                          "method": r["method"], "sim": r["sim"], "sent_score": r["sent_score"]} for r in rows]
            if sent_rows:
                await s.execute(sql("""INSERT INTO sentence_aspect (review_id, sent_idx, sentence, aspect, method, sim, sent_score)
                    VALUES (:review_id, :sent_idx, :sentence, :aspect, :method, :sim, :sent_score)"""), sent_rows)
            derived = [d for rid in rids for d in SA.review_rows(rid, by.get(rid, []), ids)]
            if derived:
                await s.execute(pg_insert(ReviewAspect), derived)
            for rid in rids:
                n = len(by.get(rid, []))
                await s.execute(sql("""INSERT INTO sentence_aspect_run (review_id, n_sentences) VALUES (:r, :n)
                    ON CONFLICT (review_id) DO UPDATE SET n_sentences = :n, processed_at = now()"""), {"r": rid, "n": n})
                await s.execute(pg_insert(ReviewAspectRun).values(review_id=rid, method="sbert", n_found=sum(1 for d in derived if d["review_id"] == rid))
                                .on_conflict_do_update(index_elements=["review_id"], set_={"method": "sbert"}))
            await s.commit()
            await set_progress(s, job_id, int(100 * min(i + CHUNK, total) / total))
    async with SessionLocal() as s:
        n_all, n_tag = (await s.execute(sql("""SELECT count(*), count(*) FILTER (WHERE aspect <> 'general') FROM sentence_aspect sa
            JOIN review r ON r.review_id = sa.review_id WHERE r.batch_id = :b"""), {"b": batch_id})).one()
    print(f"[aspects] sentences tagged: {n_tag} of {n_all} ({SA.coverage(n_tag, n_all)})")
