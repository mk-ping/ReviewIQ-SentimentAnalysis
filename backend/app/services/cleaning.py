import hashlib
import html
import re

import emoji

TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w])")
REPEAT_RE = re.compile(r"([A-Za-z!?])\1{3,}")  # 4 or more in a row become 2
MASK_RE = re.compile(r"\[(?:URL|EMAIL|PHONE)\]")

SLANG = {"u": "you", "ur": "your", "pls": "please", "plz": "please", "thx": "thanks", "thnx": "thanks",
         "gr8": "great", "luv": "love", "awsm": "awesome", "bcz": "because", "bcoz": "because",
         "bekar": "useless", "bakwas": "nonsense"}
SLANG_RE = re.compile(r"\b(" + "|".join(SLANG) + r")\b", re.I)

# Starting list (the document does not name the words). Narrow on purpose: "free shipping" is a normal review phrase.
PROMO_RE = re.compile(r"\b(click here|buy now|order now|limited time|discount code|coupon|promo code|whatsapp|subscribe|giveaway)\b", re.I)


def _phone(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[PHONE]" if 10 <= len(digits) <= 15 else m.group(0)


def clean_text(raw: str) -> str:
    """Document section 6, in order: decode HTML and strip tags, mask contacts, emojis to words,
    shorten repeats, expand slang. Stopwords are kept and nothing is lemmatised."""
    t = html.unescape(raw)
    t = TAG_RE.sub(" ", t)
    t = EMAIL_RE.sub("[EMAIL]", t)
    t = URL_RE.sub("[URL]", t)
    t = PHONE_RE.sub(_phone, t)
    t = emoji.demojize(t, delimiters=(" ", " ")).replace("_", " ")
    t = REPEAT_RE.sub(lambda m: m.group(1) * 2, t)
    t = SLANG_RE.sub(lambda m: SLANG[m.group(0).lower()], t)
    return re.sub(r"\s+", " ", t).strip()


def spam_score(raw: str, clean: str) -> float:
    """Points: link, email or phone 0.4; promo words 0.3; many repeated words 0.2; mostly capitals 0.1.
    (Copied 3 or more times, 0.3, is added in ingest because it needs the whole file.)
    One sign alone never reaches the 0.7 spam line."""
    s = 0.0
    if MASK_RE.search(clean):
        s += 0.4
    if PROMO_RE.search(clean):
        s += 0.3
    words = re.findall(r"[a-z]+", clean.lower())
    if len(words) >= 6 and len(set(words)) / len(words) < 0.5:
        s += 0.2
    letters = [c for c in MASK_RE.sub("", clean) if c.isalpha()]
    if len(letters) >= 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        s += 0.1
    return round(min(s, 1.0), 2)


def norm_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def content_hash(product: str, text: str, date_iso: str, rating_raw: str) -> str:
    key = "|".join([norm_for_hash(product), norm_for_hash(text), date_iso, rating_raw.strip()])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
