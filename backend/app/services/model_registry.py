
"""Which sentiment models run, which languages each one is routed to, and how their labels parse.

No torch import here, so it can be tested offline.
"""
import re

from app.core.config import settings

# nlptown was trained on product reviews in these languages only.
STAR_LANGUAGES = ("en", "es", "fr", "de", "it", "nl")


def configured(cfg=settings) -> list[dict]:
    """Models to run, primary first. languages=None means every language."""
    out = [{"name": cfg.sentiment_model, "source": cfg.sentiment_model, "version": "pretrained",
            "role": "core", "languages": None}]
    if cfg.star_model:
        out.append({"name": cfg.star_model, "source": cfg.star_model, "version": "pretrained",
                    "role": "core", "languages": STAR_LANGUAGES})
    if cfg.cardiff_model:
        out.append({"name": cfg.cardiff_model, "source": cfg.cardiff_model, "version": "pretrained",
                    "role": "optional", "languages": None})
    return out


def runs_on(model_cfg: dict, language: str | None) -> bool:
    """True if this model should vote on a review in this language."""
    langs = model_cfg.get("languages")
    if langs is None:
        return True
    return (language or "und") in langs


def label_to_star(label: str):
    """'1 star', '5 stars', 'LABEL_3' style (1-5), 'Very Negative' ... 'Very Positive'. None if unknown."""
    low = label.lower().replace("_", " ").strip()
    m = re.search(r"\b([1-5])\s*stars?\b", low) or re.search(r"\bstars?\s*([1-5])\b", low)
    if m:
        return int(m.group(1))
    if "very" in low and "neg" in low:
        return 1
    if "very" in low and "pos" in low:
        return 5
    if "neg" in low:
        return 2
    if "neu" in low:
        return 3
    if "pos" in low:
        return 4
    return None


def label_to_polarity(label: str):
    low = label.lower()
    return 0 if "neg" in low else 1 if "neu" in low else 2 if "pos" in low else None
