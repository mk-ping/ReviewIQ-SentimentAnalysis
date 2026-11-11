import re
from datetime import date, datetime

RATING_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?\s*(?:stars?)?\s*$", re.I)
FILLED = {"\u2605", "\u2b50"}
EMPTY = {"\u2606"}
THUMBS_UP = {"thumbs up", "thumbsup"}
THUMBS_DOWN = {"thumbs down", "thumbsdown"}


def parse_rating_cell(s: str):
    """Returns (value, denominator) or None. denominator is None for a plain number."""
    t = s.strip()
    if not t:
        return None
    low = t.lower().replace("_", " ")
    if low in THUMBS_UP:
        return (5.0, 5.0)
    if low in THUMBS_DOWN:
        return (1.0, 5.0)
    if set(t) <= (FILLED | EMPTY):
        n = sum(1 for ch in t if ch in FILLED)
        return (float(n), 5.0) if n > 0 else None
    m = RATING_RE.match(t)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    d = float(m.group(2)) if m.group(2) else None
    if d is not None and d <= 0:
        return None
    return (v, d)


def detect_scale(plain: list[float]):
    """Column scale from plain numbers only. Returns (scale, lowest_value)."""
    if not plain:
        return 5.0, 1.0
    mx, mn = max(plain), min(plain)
    if mx <= 5:
        return 5.0, 1.0
    if mx <= 10:
        return 10.0, (1.0 if mn >= 1 else 0.0)
    if mx <= 100:
        return 100.0, 0.0
    return None, None


def normalize_rating(parsed, col_scale, col_lo):
    """Map to 1-5. Returns None when the value does not fit its scale."""
    v, d = parsed
    if d is not None:
        scale, lo = d, (1.0 if d <= 5 else 0.0)
    else:
        scale, lo = col_scale, col_lo
    if scale is None or scale == lo or v < lo or v > scale:
        return None
    return round(1 + 4 * (v - lo) / (scale - lo), 2)


SLASH_RE = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")

NEUTRAL = ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
           "%Y-%m-%d %H:%M", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%d-%b-%Y",
           "%d-%b-%y", "%Y%m%d"]
DAY_FIRST = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
             "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"]
MONTH_FIRST = ["%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y", "%m/%d/%y", "%m-%d-%y",
               "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p"]


def _plausible(d: date) -> bool:
    return 1990 <= d.year <= date.today().year + 1


def infer_dayfirst(values: list[str]):
    """Look at the whole column. Returns (dayfirst, ambiguous)."""
    day_votes = month_votes = seen = 0
    for s in values:
        m = SLASH_RE.match(s)
        if not m:
            continue
        seen += 1
        a, b = int(m.group(1)), int(m.group(2))
        if a > 12 and b <= 12:
            day_votes += 1
        elif b > 12 and a <= 12:
            month_votes += 1
    ambiguous = seen > 0 and day_votes == 0 and month_votes == 0
    return day_votes >= month_votes, ambiguous


def parse_date_cell(s: str, dayfirst: bool):
    t = s.strip()
    if not t:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}", t):
        try:
            d = datetime.fromisoformat(t.replace("Z", "+00:00")).date()
            return d if _plausible(d) else None
        except ValueError:
            pass
    order = DAY_FIRST + MONTH_FIRST if dayfirst else MONTH_FIRST + DAY_FIRST
    for fmt in NEUTRAL + order:
        try:
            d = datetime.strptime(t, fmt).date()
        except ValueError:
            continue
        if _plausible(d):
            return d
    return None
