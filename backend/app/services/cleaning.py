import hashlib
import re

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w])")
REPEAT_RE = re.compile(r"([A-Za-z!?])\1{2,}")

SLANG = {"u": "you", "ur": "your", "pls": "please", "plz": "please", "thx": "thanks", "thnx": "thanks",
         "gr8": "great", "luv": "love", "awsm": "awesome", "bcz": "because", "bcoz": "because"}
SLANG_RE = re.compile(r"\b(" + "|".join(SLANG) + r")\b", re.I)


def _phone(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[phone]" if 10 <= len(digits) <= 15 else m.group(0)


def clean_text(raw: str) -> str:
    t = EMAIL_RE.sub("[email]", raw)
    t = URL_RE.sub("[link]", t)
    t = PHONE_RE.sub(_phone, t)
    t = SLANG_RE.sub(lambda m: SLANG[m.group(0).lower()], t)
    t = REPEAT_RE.sub(r"\1\1", t)
    return re.sub(r"\s+", " ", t).strip()


def spam_score(raw: str, clean: str) -> float:
    s = 0.0
    if "[link]" in clean:
        s += 0.4
    if "[phone]" in clean or "[email]" in clean:
        s += 0.2
    letters = [c for c in clean if c.isalpha()]
    if len(letters) >= 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        s += 0.2
    if raw.count("!") >= 5:
        s += 0.2
    if len(clean.split()) < 3:
        s += 0.2
    return round(min(s, 1.0), 2)


def norm_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def content_hash(product: str, text: str, date_iso: str, rating_raw: str) -> str:
    key = "|".join([norm_for_hash(product), norm_for_hash(text), date_iso, rating_raw.strip()])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
