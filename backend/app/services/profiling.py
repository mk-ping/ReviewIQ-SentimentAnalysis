import re
from dataclasses import dataclass, field
from datetime import datetime

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M"]
STOPWORDS = {"the", "and", "is", "it", "to", "of", "a", "i", "this", "was", "but", "for", "very", "hai", "ka", "ki", "ko", "ho", "nahi", "bahut"}
RATING_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*(\d+))?\s*(?:stars?)?\s*$", re.I)


@dataclass
class Profile:
    name: str
    n: int
    null_rate: float
    unique_ratio: float
    avg_len: float
    avg_words: float
    letter_share: float
    stopword_density: float
    numeric_share: float
    int_share: float
    min_val: float | None
    max_val: float | None
    distinct: int
    rating_share: float
    date_share: float
    zero_share: float
    values: list[str] = field(default_factory=list)


def _num(s: str):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_date(s: str):
    s = s.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def profile_column(name: str, values: list[str]) -> Profile:
    n = len(values)
    filled = [v for v in values if v.strip()]
    m = max(len(filled), 1)
    nums = [(_num(v)) for v in filled]
    numeric = [x for x in nums if x is not None]
    words = [len(v.split()) for v in filled]
    toks = [w for v in filled for w in re.findall(r"[a-zA-Z]+", v.lower())]
    letters = sum(ch.isalpha() for v in filled for ch in v)
    chars = max(sum(len(v) for v in filled), 1)
    rating_hits = sum(1 for v in filled if RATING_RE.match(v) or v.strip().lower() in {"\u2605", "thumbs up", "thumbs down"} or set(v.strip()) <= {"\u2605", "\u2606"} and v.strip())
    date_hits = sum(1 for v in filled if parse_date(v) is not None)
    return Profile(
        name=name,
        n=n,
        null_rate=1 - len(filled) / max(n, 1),
        unique_ratio=len(set(filled)) / m,
        avg_len=sum(len(v) for v in filled) / m,
        avg_words=sum(words) / m,
        letter_share=letters / chars,
        stopword_density=(sum(1 for t in toks if t in STOPWORDS) / max(len(toks), 1)),
        numeric_share=len(numeric) / m,
        int_share=sum(1 for x in numeric if float(x).is_integer()) / m,
        min_val=min(numeric) if numeric else None,
        max_val=max(numeric) if numeric else None,
        distinct=len(set(filled)),
        rating_share=rating_hits / m,
        date_share=date_hits / m,
        zero_share=sum(1 for x in numeric if x == 0) / m,
        values=filled[:300],
    )
