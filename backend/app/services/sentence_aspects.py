"""Sentence-level aspects (final pipeline document, section 8). Pure functions first, so they test offline.

Steps: pysbd splits a review into sentences (fragments under 2 words are dropped); SBERT similarity to each aspect
centroid tags a sentence with every aspect at or above ASPECT_SIM; if none passes, a keyword check on word starts
decides; otherwise the sentence is 'general'. Sentence sentiment comes from the model chosen by route group."""
import re

from app.core import thresholds as T
from app.core import domains as D
from app.core.aspect_config import CATEGORIES, SEEDS, STEMS

GENERAL = "general"
_STEM_RX = {a: re.compile(r"\b(?:" + "|".join(STEMS[a]) + ")", re.I) for a in CATEGORIES}
_FALLBACK_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+|\s*[;|]\s*")
_seg = None


def split_sentences(text: str) -> list[str]:
    """pysbd when installed, a simple punctuation splitter otherwise. Fragments under 2 words are dropped."""
    global _seg
    parts = None
    try:
        if _seg is None:
            import pysbd
            _seg = pysbd.Segmenter(language="en", clean=False)
        parts = _seg.segment(text)
    except Exception:
        parts = None
    if parts is None:
        parts = _FALLBACK_SPLIT.split(text or "")
    out = []
    for p in parts:
        p = " ".join(p.split())
        if len(p.split()) >= 2:
            out.append(p)
    return out


_RX_CACHE: dict = {}


def _rx_for(domain: str) -> dict:
    if domain not in _RX_CACHE:
        st = D.PROFILES[domain]["stems"]
        _RX_CACHE[domain] = {a: re.compile(r"\b(?:" + "|".join(st[a]) + ")", re.I) for a in D.categories_of(domain)}
    return _RX_CACHE[domain]


def keyword_hits(sentence: str, domain: str = "product") -> list[str]:
    return [a for a, rx in _rx_for(domain).items() if rx.search(sentence)]


def term_of(sentence: str, aspect: str, domain: str = "product") -> str:
    rx = _rx_for(domain).get(aspect)
    m = rx.search(sentence) if rx else None
    if not m:
        return aspect
    word = re.match(r"\w+", sentence[m.start():])
    return (word.group(0) if word else aspect).lower()[:100]


def tag(sims: dict[str, float], sentence: str, domain: str = "product") -> list[tuple[str, str, float]]:
    """Returns [(aspect, method, sim)]. method is 'sbert', 'keyword' or 'general'."""
    hits = [(a, "sbert", s) for a, s in sims.items() if s >= T.ASPECT_SIM]
    if hits:
        return sorted(hits, key=lambda h: -h[2])
    kw = keyword_hits(sentence, domain)
    if kw:
        return [(a, "keyword", float(sims.get(a, 0.0))) for a in kw]
    return [(GENERAL, GENERAL, float(max(sims.values())) if sims else 0.0)]


def centroids(embed_fn, domain: str = "product") -> dict:
    """Average of each aspect's seed vectors, scaled to length 1. embed_fn(list[str]) -> (n, dim) unit vectors."""
    import numpy as np
    out = {}
    seeds = D.PROFILES[domain]["seeds"]
    for a in D.categories_of(domain):
        v = np.asarray(embed_fn(seeds[a]), dtype=float).mean(axis=0)
        out[a] = v / (np.linalg.norm(v) or 1.0)
    return out


def similarities(vectors, cents: dict) -> list[dict[str, float]]:
    """Cosine similarity of each (unit length) sentence vector to each centroid."""
    import numpy as np
    m = np.asarray(vectors, dtype=float)
    return [{a: float(m[i] @ c) for a, c in cents.items()} for i in range(len(m))]


def sentiment_model_for(language: str | None) -> str:
    """RoBERTa for English, Twitter XLM-RoBERTa for every other route group."""
    from app.services.routing import group_of
    return "roberta" if group_of(language) == "english" else "xlmr"


def coverage(n_tagged: int, n_total: int) -> float | None:
    """Share of sentences that received an aspect. This is coverage, not accuracy."""
    return None if n_total == 0 else n_tagged / n_total


def review_rows(review_id: int, sentences: list[dict], aspect_ids: dict[str, int]) -> list[dict]:
    """Review-level view derived from the sentence rows (one row per tagged sentence), so Hidden Dissatisfaction,
    the issues and the aspect pages keep reading review_aspect. Confidence is the sentiment model's confidence."""
    rows = []
    for s in sentences:
        if s["aspect"] == GENERAL or s["sent_score"] is None:
            continue
        rows.append({"review_id": review_id, "aspect_id": aspect_ids[s["aspect"]], "term": term_of(s["sentence"], s["aspect"], s.get("domain", "product")),
                     "evidence_span": s["sentence"], "sentiment": round(s["sent_score"], 3),
                     "confidence": round(s["conf"], 3), "method": s["method"]})
    return rows
