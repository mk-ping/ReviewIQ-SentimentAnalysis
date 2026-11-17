"""aspects stage: sentence-level aspects. Replaces the review-level LLM stage; the LLM no longer tags anything."""
import asyncio

from sqlalchemy import delete, func, select, text as sql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core import domains as D, thresholds as T
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Review, ReviewAspect, ReviewAspectRun, UploadBatch
from app.services import embeddings, sentence_aspects as SA, sentiment
from app.services.queue import set_progress
from app.worker.handlers import CHUNK, _aspect_ids

_cents: dict = {}


def _cents_for(model: str, domain: str = "product") -> dict:
    if (model, domain) not in _cents:
        _cents[(model, domain)] = SA.centroids(lambda t: embeddings.embed(t, model), domain)
    return _cents[(model, domain)]


def _analyse(part: list[tuple]) -> list[dict]:
    """part = [(review_id, text, language, domain)]. Returns sentence dicts with aspect, method, sim, sent_score, conf."""
    items = []
    for rid, text, lang, dom in part:
        for idx, s in enumerate(SA.split_sentences(text or "")):
            items.append({"review_id": rid, "idx": idx, "sentence": s, "lang": lang, "domain": dom,
                          "english": SA.sentiment_model_for(lang) == "roberta"})
    out = []
    for english, dom in sorted({(i["english"], i["domain"]) for i in items}):
        grp = [i for i in items if i["english"] == english and i["domain"] == dom]
        model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
        vecs = embeddings.embed([i["sentence"] for i in grp], model)
        sims = SA.similarities(vecs, _cents_for(model, dom))
        tagged = []
        for i, sm in zip(grp, sims):
            for aspect, method, sim in SA.tag(sm, i["sentence"], dom):
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
        pending = (await s.execute(sql("""
            SELECT r.review_id, r.text_clean, r.language, r.product_id FROM review r
            LEFT JOIN sentence_aspect_run u ON u.review_id = r.review_id
            WHERE r.batch_id = :b AND u.review_id IS NULL ORDER BY r.review_id"""), {"b": batch_id})).all()
    by_prod: dict = {}
    for p in pending:
        by_prod.setdefault(p[3], []).append(p[1])
    dom_of = {pid: D.detect_domain(txts, settings.aspect_domain) for pid, txts in by_prod.items()}
    names = sorted({c for d in set(dom_of.values()) for c in D.categories_of(d)})
    print(f"[aspects] review types detected: {sorted(set(dom_of.values())) or 'none'}")
    async with SessionLocal() as s:
        ids = await _aspect_ids(s, ws, names)
    total = len(pending)
    for i in range(0, total, CHUNK):
        part = pending[i : i + CHUNK]
        rows = await asyncio.to_thread(_analyse, [(p[0], p[1], p[2], dom_of[p[3]]) for p in part])
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
