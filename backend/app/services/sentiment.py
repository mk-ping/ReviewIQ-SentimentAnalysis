import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import settings

MAX_LEN = 256
_tok = None
_model = None
_stars: list[int] = []
_device = "cuda" if torch.cuda.is_available() else "cpu"


def _label_to_star(label: str):
    low = label.lower().replace("_", " ")
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


def load():
    """Loads the model once per process. Returns (device, label_to_star mapping)."""
    global _tok, _model, _stars
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(settings.sentiment_model)
        _model = AutoModelForSequenceClassification.from_pretrained(settings.sentiment_model).eval().to(_device)
        id2label = _model.config.id2label
        if len(id2label) != 5:
            raise RuntimeError(f"Expected a 5-class model, got {len(id2label)} classes: {id2label}")
        stars = [_label_to_star(id2label[i]) for i in range(5)]
        if None in stars or sorted(stars) != [1, 2, 3, 4, 5]:
            raise RuntimeError(f"Could not map labels to stars: {id2label}")
        _stars = stars
    return _device, dict(zip(_model.config.id2label.values(), _stars))


def predict(texts: list[str], batch_size: int = 32) -> list[tuple[float, float, float, float]]:
    """Returns (p_neg, p_neu, p_pos, expected_stars) per text."""
    load()
    out = []
    for i in range(0, len(texts), batch_size):
        enc = _tok(texts[i : i + batch_size], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt").to(_device)
        with torch.no_grad():
            probs = torch.softmax(_model(**enc).logits, dim=-1).cpu().tolist()
        for row in probs:
            by_star = {s: p for s, p in zip(_stars, row)}
            out.append((
                by_star[1] + by_star[2],
                by_star[3],
                by_star[4] + by_star[5],
                sum(s * p for s, p in by_star.items()),
            ))
    return out
