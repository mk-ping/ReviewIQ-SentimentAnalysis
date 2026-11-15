import asyncio
import json
import re

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES
from app.core.config import settings
from app.services.aspects import _norm
from app.services.embeddings import embed

MAX_CLAIMS = 12


def verdict(supports: int, contradicts: int) -> str:
    if supports + contradicts < T.LISTING_MIN_EVIDENCE:
        return "not_enough_evidence"
    share = supports / (supports + contradicts)
    return "confirmed" if share >= T.LISTING_CONFIRM else "contradicted" if share <= T.LISTING_CONTRADICT else "mixed"


def validate_claims(items, listing_text: str) -> list[dict]:
    """Keeps claims whose quote really appears in the listing. An unknown aspect becomes None."""
    if not isinstance(items, list):
        return []
    t, out, seen = _norm(listing_text), [], set()
    for it in items:
        try:
            claim, quote = str(it["claim"]).strip(), str(it["quote"]).strip()
        except (KeyError, TypeError):
            continue
        aspect = str(it.get("aspect") or "").strip().lower() if isinstance(it, dict) else ""
        if len(claim) < 3 or len(quote) < 3 or _norm(quote) not in t or claim.lower() in seen:
            continue
        seen.add(claim.lower())
        out.append({"claim": claim[:300], "quote": quote[:500], "aspect": aspect if aspect in CATEGORIES else None})
    return out[:MAX_CLAIMS]


async def _chat(client: httpx.AsyncClient, system: str, user: str):
    r = await client.post(f"{settings.llm_url}/api/chat", json={
        "model": settings.llm_model, "stream": False, "format": "json", "keep_alive": "10m",
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


async def extract_claims(client: httpx.AsyncClient, listing_text: str) -> list[dict]:
    system = (
        "You read a product listing and list its checkable promises about the product (for example long-lasting, "
        "easy to use, hypoallergenic, fast delivery). Return ONLY JSON: "
        '{"claims": [{"claim": "short statement", "aspect": "one category", "quote": "exact words copied from the listing"}]}. '
        f"aspect must be one of: {', '.join(CATEGORIES)}. quote must be copied word for word. "
        "Skip slogans that cannot be checked. If there are no checkable promises return {\"claims\": []}."
    )
    for _ in range(2):
        try:
            data = await _chat(client, system, "Listing:\n" + listing_text)
        except Exception:
            continue
        ok = validate_claims(data.get("claims") if isinstance(data, dict) else None, listing_text)
        if ok or (isinstance(data, dict) and data.get("claims") == []):
            return ok
    return []


async def judge(client: httpx.AsyncClient, claim: str, sentence: str):
    system = ("Decide whether a customer review sentence supports, contradicts, or is unrelated to a product claim. "
              'Return ONLY JSON: {"stance": "supports" | "contradicts" | "unrelated"}.')
    for _ in range(2):
        try:
            d = await _chat(client, system, f"Claim: {claim}\nSentence: {sentence}")
            s = str(d.get("stance", "")).lower().strip() if isinstance(d, dict) else ""
            if s in ("supports", "contradicts", "unrelated"):
                return s
        except Exception:
            continue
    return None  # the model failed: skip this sentence rather than guess


def _best_sentences(claim: str, rows) -> list[tuple]:
    """rows: (review_id, text). Returns (review_id, sentence, similarity) for the sentence closest to the claim."""
    q = embed([claim], T.SBERT_EN_MODEL)[0]
    out = []
    for rid, txt in rows:
        parts = [p.strip() for p in re.split(r"[.!?;\n]+", txt or "") if len(p.strip()) >= 3]
        if not parts:
            continue
        sims = embed(parts, T.SBERT_EN_MODEL) @ q
        i = int(sims.argmax())
        if float(sims[i]) >= T.LISTING_MIN_SIM:
            out.append((rid, parts[i][:400], float(sims[i])))
    return out


async def collect_evidence(session: AsyncSession, ws: int, product_id: int, claim: str):
    q = (await asyncio.to_thread(embed, [claim], T.SBERT_EN_MODEL))[0]
    vec = "[" + ",".join(f"{float(x):.6f}" for x in q) + "]"
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    rows = (await session.execute(text("""
        SELECT r.review_id, r.text_clean FROM review_embedding e JOIN review r ON r.review_id = e.review_id
        WHERE r.workspace_id = :ws AND r.product_id = :pid AND r.spam_score <= :spam AND e.model = :m
        ORDER BY e.embedding <=> CAST(:q AS vector) LIMIT :k"""),
        {"ws": ws, "pid": product_id, "spam": T.SPAM_MAX, "q": vec, "k": T.LISTING_TOP_K, "m": T.SBERT_EN_MODEL})).all()
    return await asyncio.to_thread(_best_sentences, claim, [(r[0], r[1]) for r in rows])
