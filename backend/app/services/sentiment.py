import re
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.core.config import settings

MAX_LEN = 256
DEFAULT = "roberta"
_device = "cuda" if torch.cuda.is_available() else "cpu"
_cache: dict = {}


def registry() -> dict[str, dict]:
    reg = {
        "roberta": {"name": settings.roberta_model, "version": "pretrained", "kind": "sentiment"},
        "nlptown": {"name": settings.nlptown_model, "version": "pretrained", "kind": "sentiment"},
        "xlmr": {"name": settings.xlmr_model, "version": "pretrained", "kind": "sentiment"},
    }
    if settings.distil_model:
        reg["distil"] = {"name": settings.distil_model, "version": "pretrained", "kind": "sentiment"}
    reg["tfidf"] = {"name": "reviewiq-tfidf-lr", "version": "trained", "kind": "baseline"}
    return reg


def available(key: str) -> bool:
    """The TF-IDF baseline is trained in Fix 3, so it is not available yet."""
    return key in registry() and key != "tfidf"


def _star(label: str):
    m = re.search(r"(\d)\s*star", label.lower())
    return int(m.group(1)) if m else None


def _pol(label: str):
    low = label.lower()
    if "neg" in low:
        return 0
    if "neu" in low:
        return 1
    if "pos" in low:
        return 2
    m = re.fullmatch(r"label_(\d)", low)
    return int(m.group(1)) if m and int(m.group(1)) < 3 else None


class Scorer:
    def __init__(self, source: str):
        self.tok = AutoTokenizer.from_pretrained(source)
        self.model = AutoModelForSequenceClassification.from_pretrained(source).eval().to(_device)
        id2 = self.model.config.id2label
        self.n = len(id2)
        if self.n == 5:
            self.vals = [_star(id2[i]) for i in range(5)]
            ok = None not in self.vals and sorted(self.vals) == [1, 2, 3, 4, 5]
        elif self.n == 3:
            self.vals = [_pol(id2[i]) for i in range(3)]
            ok = None not in self.vals and sorted(self.vals) == [0, 1, 2]
        else:
            ok = False
        if not ok:
            raise RuntimeError(f"Cannot map the labels of {source}: {id2}")
        self.mapping = {id2[i]: self.vals[i] for i in range(self.n)}

    def predict(self, texts: list[str], batch_size: int = 32):
        """Returns (p_neg, p_neu, p_pos, expected_stars or None) per text. Expected stars only for 5-class models."""
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok(texts[i : i + batch_size], truncation=True, max_length=MAX_LEN, padding=True, return_tensors="pt").to(_device)
            with torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits, dim=-1).cpu().tolist()
            for row in probs:
                by = dict(zip(self.vals, row))
                if self.n == 5:
                    out.append((by[1] + by[2], by[3], by[4] + by[5], sum(s * p for s, p in by.items())))
                else:
                    out.append((by[0], by[1], by[2], None))
        return out


def get_scorer(key: str) -> Scorer:
    if key not in _cache:
        if not available(key):
            raise RuntimeError(f"Model '{key}' is not available yet.")
        _cache[key] = Scorer(registry()[key]["name"])
    return _cache[key]


def load():
    """Default model only (kept for older callers). Returns (device, label -> value mapping)."""
    return _device, get_scorer(DEFAULT).mapping


def predict(texts: list[str], batch_size: int = 32, model: str = DEFAULT):
    return get_scorer(model).predict(texts, batch_size)
