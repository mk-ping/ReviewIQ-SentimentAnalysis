
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.services.model_registry import configured, label_to_polarity, label_to_star, runs_on  # noqa: F401

MAX_LEN = 256
_device = "cuda" if torch.cuda.is_available() else "cpu"
_cache: dict = {}


class Scorer:
    def __init__(self, cfg: dict):
        src = cfg["source"]
        self.tok = AutoTokenizer.from_pretrained(src)
        self.model = AutoModelForSequenceClassification.from_pretrained(src).eval().to(_device)
        id2 = self.model.config.id2label
        self.n = len(id2)
        if self.n == 5:
            self.vals = [label_to_star(id2[i]) for i in range(5)]
            ok = None not in self.vals and sorted(self.vals) == [1, 2, 3, 4, 5]
        elif self.n == 3:
            self.vals = [label_to_polarity(id2[i]) for i in range(3)]
            ok = None not in self.vals and sorted(self.vals) == [0, 1, 2]
        else:
            ok = False
        if not ok:
            raise RuntimeError(f"Cannot map the labels of {src}: {id2}")
        self.mapping = {id2[i]: self.vals[i] for i in range(self.n)}

    def predict(self, texts: list[str], batch_size: int = 32):
        out = []
        for i in range(0, len(texts), batch_size):
            enc = self.tok(texts[i : i + batch_size], truncation=True, max_length=MAX_LEN, padding=True,
                           return_tensors="pt").to(_device)
            with torch.no_grad():
                probs = torch.softmax(self.model(**enc).logits, dim=-1).cpu().tolist()
            for row in probs:
                by = dict(zip(self.vals, row))
                if self.n == 5:
                    out.append((by[1] + by[2], by[3], by[4] + by[5], sum(s * p for s, p in by.items())))
                else:
                    out.append((by[0], by[1], by[2], None))
        return out


def get_scorer(cfg: dict) -> Scorer:
    if cfg["name"] not in _cache:
        _cache[cfg["name"]] = Scorer(cfg)
    return _cache[cfg["name"]]


def load():
    """Primary model only (kept for older callers). Returns (device, label -> value mapping)."""
    return _device, get_scorer(configured()[0]).mapping


def predict(texts: list[str], batch_size: int = 32, model: str | None = None):
    """Returns (p_neg, p_neu, p_pos, expected_stars or None) per text. Default is the primary model."""
    cfgs = configured()
    cfg = next((c for c in cfgs if c["name"] == model), cfgs[0]) if model else cfgs[0]
    return get_scorer(cfg).predict(texts, batch_size)
