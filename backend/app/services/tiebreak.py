import numpy as np
from scipy.stats import spearmanr

from app.core import thresholds as T
from app.services.parsing import parse_rating_cell


def rating_value(s: str):
    p = parse_rating_cell(s)
    if not p:
        return None
    return p[0] if p[1] is None else 5.0 * p[0] / p[1]


def candidates(results) -> list[str]:
    """Columns worth testing: chosen without header evidence, plus the rating's alternatives."""
    by = {r.role: r for r in results}
    out: list[str] = []

    def add(c):
        if c and c not in out:
            out.append(c)

    rat_weak = False
    for role in ("rating", "helpful"):
        r = by[role]
        if r.column and r.evidence.get("header_score", 0) < T.TIEBREAK_WEAK_HEADER:
            add(r.column)
            rat_weak = rat_weak or role == "rating"
    if rat_weak:
        for a in by["rating"].alternatives:
            add(a["column"])
    return out


def corr_with_sentiment(texts: list[str], nums: list):
    pairs = [(t, v) for t, v in zip(texts, nums) if v is not None and t.strip()][: T.TIEBREAK_SAMPLE]
    if len(pairs) < 10 or len({v for _, v in pairs}) < 2:
        return None
    from app.services import sentiment

    probs = sentiment.predict([t for t, _ in pairs])
    s = [p - n for n, _u, p, _e in probs]
    c = float(spearmanr(s, [v for _, v in pairs])[0])
    return None if np.isnan(c) else c


def _fits_helpful(p) -> bool:
    return p is not None and p.int_share > 0.95 and p.zero_share >= 0.3 and (p.max_val or 0) > 1


def _set(r, col, conf, action, corr):
    r.column, r.confidence, r.action = col, conf, action
    r.method = "header+values+corr"
    r.evidence = {"sentiment_corr": round(corr, 3)}
    r.alternatives = []


def _clear(r):
    r.column, r.confidence, r.action = None, 0.0, "none"
    r.method, r.evidence, r.alternatives = "none", {}, []


def decide(results, corrs: dict, profiles: dict) -> None:
    """Adjusts the rating and helpful results in place from the measured correlations."""
    by = {r.role: r for r in results}
    rat, hel = by["rating"], by["helpful"]
    alts = [a["column"] for a in rat.alternatives]
    cr = corrs.get(rat.column) if rat.column else None
    ch = corrs.get(hel.column) if hel.column else None

    # the helpful column follows sentiment better than the rating column: swap them
    if hel.column and ch is not None and ch >= T.TIEBREAK_TRACKS and (
        rat.column is None or (cr is not None and cr < ch - 0.2)
    ):
        old = rat.column
        _set(rat, hel.column, 0.7, "ask", ch)
        if old and cr is not None and abs(cr) < T.TIEBREAK_FLAT and _fits_helpful(profiles.get(old)):
            _set(hel, old, 0.6, "accept", cr)
        else:
            _clear(hel)
        return

    if rat.column and cr is not None and cr < T.TIEBREAK_TRACKS:
        best = max(((corrs[a], a) for a in alts if a in corrs), default=None)
        if best and best[0] >= T.TIEBREAK_TRACKS and best[0] >= cr + 0.2:
            old = rat.column
            _set(rat, best[1], 0.7, "ask", best[0])
            if hel.column is None and _fits_helpful(profiles.get(old)):
                _set(hel, old, 0.6, "accept", cr)
            return

    if rat.column and cr is not None:
        if cr >= T.TIEBREAK_TRACKS:
            rat.confidence = max(rat.confidence, 0.85)
            rat.action = "accept"
            rat.method = "header+values+corr"
            rat.evidence = {**rat.evidence, "sentiment_corr": round(cr, 3)}
        elif abs(cr) < T.TIEBREAK_FLAT:
            old = rat.column
            if hel.column is None and _fits_helpful(profiles.get(old)):
                _set(hel, old, 0.6, "accept", cr)
                _clear(rat)
            else:
                rat.confidence = min(rat.confidence, 0.45)
                rat.action = "ask"
                rat.method = "header+values+corr"
                rat.evidence = {**rat.evidence, "sentiment_corr": round(cr, 3),
                                "note": "does not move with text sentiment"}
            best = max(((corrs[a], a) for a in alts if a in corrs and a != hel.column), default=None)
            if best and best[0] >= T.TIEBREAK_TRACKS:
                _set(rat, best[1], 0.7, "ask", best[0])


def apply_tiebreak(results, profiles, header: list[str], data: list[list[str]]) -> dict:
    by = {r.role: r for r in results}
    text = by["text"]
    cols = candidates(results)
    if not cols or text.column is None:
        return {}
    texts = [r[header.index(text.column)] for r in data]
    corrs = {}
    for name in cols:
        i = header.index(name)
        c = corr_with_sentiment(texts, [rating_value(r[i]) for r in data])
        if c is not None:
            corrs[name] = c
    decide(results, corrs, {p.name: p for p in profiles})
    return corrs
