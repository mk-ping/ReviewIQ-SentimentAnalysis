"""Results CSV for one upload. Pure functions, so they test offline."""
import csv
import io

BASE = ["review_id", "product", "stars_raw", "stars", "language", "date", "text", "spam_score",
        "sentiment", "confidence", "text_adjusted_stars", "expected_stars", "star_gap", "mismatch"]


def safe_cell(v):
    """Stops a spreadsheet from running a review that starts with = + - or @ as a formula."""
    if v is None:
        return ""
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") and not _is_number(s) else s


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def short_model(name: str) -> str:
    return (name or "model").split("/")[-1]


def vote_label(p_neg: float, p_neu: float, p_pos: float) -> str:
    """Same tie rule as fusion: negative wins ties, then neutral."""
    conf = max(p_neg, p_neu, p_pos)
    return "neg" if conf == p_neg else ("neu" if conf == p_neu else "pos")


def build_csv(rows: list[tuple], votes: dict[int, dict[str, str]]) -> str:
    """rows follow BASE order. votes maps review_id -> {model short name: label}."""
    models = sorted({m for v in votes.values() for m in v})
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(BASE + [f"vote_{m}" for m in models])
    for r in rows:
        v = votes.get(r[0], {})
        w.writerow([safe_cell(c) for c in r] + [v.get(m, "") for m in models])
    return chr(0xFEFF) + out.getvalue()
