import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.services.profiling import Profile

ROLES = ["text", "rating", "date", "product", "title", "helpful", "id", "author"]
REQUIRED = {"text"}

ALIASES = {
    "text": ["review", "review text", "review_text", "reviewtext", "comment", "comments", "feedback", "body", "content", "text", "description", "opinion", "review body", "remarks", "samiksha", "tippani"],
    "rating": ["rating", "stars", "star", "score", "star rating", "star_rating", "overall", "rate", "ratings", "grade", "reviewer rating"],
    "date": ["date", "posted", "time", "created", "timestamp", "review date", "review_date", "reviewed at", "posted on", "created at", "datetime", "tarikh"],
    "product": ["product", "product name", "item", "asin", "sku", "brand", "product_name", "product title", "app", "model", "business"],
    "title": ["title", "headline", "summary", "subject", "review title", "review_title"],
    "helpful": ["helpful", "votes", "helpful votes", "helpful_votes", "thumbs up", "likes", "upvotes", "useful", "helpfulness"],
    "id": ["id", "review id", "review_id", "reviewid", "uuid", "order id", "order_id", "serial", "sr no", "s no", "index"],
    "author": ["author", "reviewer", "user", "username", "name", "customer", "reviewer name", "profile", "user name", "user.name", "customer name"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("_", " ")).strip()


def header_score(header: str, role: str) -> tuple[float, str | None]:
    h = _norm(header.split(".")[-1]) if "." in header and role == "author" else _norm(header)
    full = _norm(header)
    best, hit = 0.0, None
    for alias in ALIASES[role]:
        a = _norm(alias)
        if h == a or full == a:
            return 1.0, alias
        if a in h.split() or a in full.split():
            s = 0.8
        elif len(a) >= 4 and (a in h or h in a and len(h) >= 4):
            s = 0.65
        else:
            s = SequenceMatcher(None, h, a).ratio()
            s = s if s >= 0.8 else 0.0
        if s > best:
            best, hit = s, alias
    return best, hit


def value_score(p: Profile, role: str) -> float:
    if p.n == 0 or p.null_rate > 0.95:
        return 0.0
    if role == "text":
        s = 0.0
        s += min(p.avg_words / 8, 1) * 0.4
        s += min(p.avg_len / 60, 1) * 0.15
        s += (1 if p.unique_ratio > 0.8 else p.unique_ratio) * 0.15
        s += (1 if p.letter_share > 0.6 else p.letter_share) * 0.15
        s += min(p.stopword_density / 0.15, 1) * 0.15
        return s if p.numeric_share < 0.5 else 0.0
    if role == "rating":
        if p.rating_share < 0.8 or p.max_val is None and p.rating_share < 0.8:
            return 0.0
        mx = p.max_val or 5
        fits = 2 <= p.distinct <= 11 and (mx <= 5 or mx in (10, 100) or mx <= 11)
        return 0.9 if fits else 0.4
    if role == "date":
        return 0.95 if p.date_share >= 0.8 else (p.date_share if p.date_share >= 0.5 else 0.0)
    if role == "product":
        return 0.7 if p.avg_len <= 60 and p.distinct >= 1 and p.unique_ratio < 0.5 and p.numeric_share < 0.3 else 0.0
    if role == "title":
        return 0.6 if 1 <= p.avg_words <= 10 and p.numeric_share < 0.3 and p.unique_ratio > 0.5 else 0.0
    if role == "helpful":
        return 0.7 if p.int_share > 0.95 and p.numeric_share > 0.95 and p.zero_share >= 0.3 and (p.max_val or 0) > 1 else 0.0
    if role == "id":
        return 0.8 if p.unique_ratio > 0.98 and p.avg_len <= 40 and p.n > 2 else 0.0
    if role == "author":
        return 0.5 if p.avg_len <= 40 and p.unique_ratio > 0.3 and p.numeric_share < 0.2 and p.avg_words <= 4 else 0.0
    return 0.0


@dataclass
class Candidate:
    column: str
    score: float
    header_hit: str | None
    header_part: float
    value_part: float


@dataclass
class RoleResult:
    role: str
    column: str | None
    confidence: float
    method: str
    evidence: dict
    alternatives: list[dict] = field(default_factory=list)
    action: str = "none"  # accept | ask | missing


def combine(h: float, v: float) -> float:
    if h == 0:
        return v * 0.8
    if v == 0:
        return h * 0.45
    return min(1.0, 0.45 * h + 0.55 * v + 0.1 * min(h, v))


def score_all(profiles: list[Profile]) -> dict[str, list[Candidate]]:
    table: dict[str, list[Candidate]] = {r: [] for r in ROLES}
    for role in ROLES:
        for p in profiles:
            h, hit = header_score(p.name, role)
            v = value_score(p, role)
            table[role].append(Candidate(p.name, combine(h, v), hit, h, v))
        table[role].sort(key=lambda c: c.score, reverse=True)
    return table


def assign(profiles: list[Profile]) -> list[RoleResult]:
    table = score_all(profiles)
    taken: dict[str, str] = {}
    results: dict[str, RoleResult] = {}
    order = ["text", "rating", "date", "helpful", "title", "product", "author", "id"]

    pairs = sorted(((c.score, role, c) for role in order for c in table[role]), key=lambda t: -t[0])
    for score, role, c in pairs:
        if role in results or c.column in taken or score < 0.3:
            continue
        taken[c.column] = role
        results[role] = RoleResult(
            role=role, column=c.column, confidence=round(score, 3), method="header+values",
            evidence={"header_match": c.header_hit, "header_score": round(c.header_part, 2), "value_score": round(c.value_part, 2)},
        )

    out: list[RoleResult] = []
    for role in ROLES:
        r = results.get(role)
        if r is None:
            out.append(RoleResult(role, None, 0.0, "none", {}, [], "missing" if role in REQUIRED else "none"))
            continue
        alts = [
            {"column": c.column, "confidence": round(c.score, 3)}
            for c in table[role]
            if c.column != r.column and c.score >= 0.3
        ][:2]
        r.alternatives = alts
        close = alts and (r.confidence - alts[0]["confidence"]) < 0.1
        if r.confidence >= 0.85 and not close:
            r.action = "accept"
        elif role in REQUIRED:
            r.action = "ask"
        else:
            r.action = "accept" if r.confidence >= 0.6 and not close else "ask"
        out.append(r)
    return out
