import asyncio
import json
import re

import httpx

from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES, KEYWORDS
from app.core.config import settings

EXAMPLES = [
    ("Love the fragrance, but the cap cracked within a week.", [
        {"term": "fragrance", "category": "scent", "sentiment": 1, "evidence": "Love the fragrance"},
        {"term": "cap", "category": "packaging", "sentiment": -1, "evidence": "the cap cracked within a week"}]),
    ("Parcel reached three days late and the carton was crushed.", [
        {"term": "parcel", "category": "delivery", "sentiment": -1, "evidence": "Parcel reached three days late"},
        {"term": "carton", "category": "packaging", "sentiment": -1, "evidence": "the carton was crushed"}]),
    ("Bahut badhiya cream hai lekin paisa thoda zyada lagta hai", [
        {"term": "cream", "category": "quality", "sentiment": 1, "evidence": "Bahut badhiya cream hai"},
        {"term": "paisa", "category": "price", "sentiment": -0.5, "evidence": "paisa thoda zyada lagta hai"}]),
    ("ok", []),
    ("Smooth texture and the staff replaced it quickly.", [
        {"term": "texture", "category": "texture", "sentiment": 1, "evidence": "Smooth texture"},
        {"term": "staff", "category": "customer service", "sentiment": 1, "evidence": "the staff replaced it quickly"}]),
    ("Works as described, nothing special.", [
        {"term": "works", "category": "effectiveness", "sentiment": 0.5, "evidence": "Works as described"}]),
]


def _prompt() -> str:
    cats = ", ".join(CATEGORIES)
    shots = "\n\n".join(
        f"Review: {t}\nJSON: {json.dumps({'aspects': a}, ensure_ascii=False)}" for t, a in EXAMPLES
    )
    return (
        "You extract aspect-level opinions from ONE customer review (English, Hindi or Hinglish).\n"
        "Return ONLY a JSON object: {\"aspects\": [{\"term\", \"category\", \"sentiment\", \"evidence\"}]}.\n"
        f"- category must be exactly one of: {cats}.\n"
        "- term is the specific thing mentioned (for example pump, scent, box).\n"
        "- sentiment is a number from -1 (very negative) to 1 (very positive); use 0 for neutral.\n"
        "- evidence must be copied word for word from the review. Never paraphrase it.\n"
        "- Return one entry per distinct opinion. If the review has no opinion about anything specific, return {\"aspects\": []}.\n\n"
        + shots
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip(" .,!?\"'")


def validate(items, text: str) -> tuple[list[dict], int]:
    """Keeps only aspects whose category is on the list and whose evidence appears in the review.
    Returns (valid_items, number_rejected)."""
    if not isinstance(items, list):
        return [], 1
    t = _norm(text)
    ok, bad, seen = [], 0, set()
    for it in items:
        try:
            term = str(it["term"]).strip()[:100]
            cat = str(it["category"]).strip().lower()
            sent = float(it["sentiment"])
            ev = str(it["evidence"]).strip()
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        if not term or cat not in CATEGORIES or not -1 <= sent <= 1 or len(ev) < 3 or _norm(ev) not in t:
            bad += 1
            continue
        key = (cat, term.lower())
        if key in seen:
            continue
        seen.add(key)
        ok.append({"category": cat, "term": term, "sentiment": round(sent, 2), "evidence_span": ev,
                   "confidence": T.ASPECT_LLM_CONF, "method": "llm"})
    return ok, bad


async def llm_available(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{settings.llm_url}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m.get("name", "") for m in r.json().get("models", [])]
        return any(n == settings.llm_model or n.startswith(settings.llm_model) for n in names)
    except Exception:
        return False


async def _ask(client: httpx.AsyncClient, text: str):
    r = await client.post(
        f"{settings.llm_url}/api/chat",
        json={
            "model": settings.llm_model, "stream": False, "format": "json", "keep_alive": "10m",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": _prompt()},
                {"role": "user", "content": f"Review: {text}\nJSON:"},
            ],
        },
    )
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


_PATTERNS = {
    cat: re.compile(r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b", re.I) for cat, kws in KEYWORDS.items()
}
_CLAUSE = re.compile(r"[.!?;\n]+|,?\s+\b(?:but|however|though|lekin|par)\b\s*", re.I)


def keyword_aspects(text: str) -> list[dict]:
    """Fallback: match category keywords per clause, then score the clause with the sentiment model."""
    from app.services import sentiment

    clauses = [c.strip() for c in _CLAUSE.split(text) if c and len(c.strip()) >= 3]
    hits = []
    for c in clauses:
        for cat, rx in _PATTERNS.items():
            m = rx.search(c)
            if m:
                hits.append((cat, m.group(0).lower(), c))
    if not hits:
        return []
    probs = sentiment.predict([c for _, _, c in hits])
    out, seen = [], set()
    for (cat, term, c), (n, u, p, _e) in zip(hits, probs):
        if (cat, term) in seen:
            continue
        seen.add((cat, term))
        out.append({"category": cat, "term": term, "sentiment": round(p - n, 2), "evidence_span": c,
                    "confidence": round(max(n, u, p), 3), "method": "keyword"})
    return out


async def extract(client: httpx.AsyncClient | None, text: str) -> tuple[list[dict], str]:
    """Returns (aspects, method). Tries the LLM twice, then the keyword fallback."""
    if client is not None:
        for _ in range(2):
            try:
                data = await _ask(client, text)
            except Exception:
                continue
            raw = data.get("aspects") if isinstance(data, dict) else None
            if not isinstance(raw, list):
                continue
            ok, _bad = validate(raw, text)
            if ok or not raw:
                return ok, "llm"
    return await asyncio.to_thread(keyword_aspects, text), "keyword"
