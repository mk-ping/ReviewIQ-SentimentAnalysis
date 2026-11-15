"""Offline checks for sentence-level aspects (no models, no database). Run: python -m tests.check_sentence_aspects"""
from app.core import thresholds as T
from app.core.aspect_config import CATEGORIES, SEEDS, STEMS
from app.services import sentence_aspects as SA

assert len(CATEGORIES) == 7 and set(SEEDS) == set(CATEGORIES) == set(STEMS)
assert all(len(v) == 6 for v in SEEDS.values())

# splitting drops fragments under 2 words and keeps 'very nice'
s = SA.split_sentences("Great scent. Ok. The pump broke after a week! Very nice")
assert "Great scent." in s and "Ok." not in s and any("pump broke" in x for x in s) and any("Very nice" in x for x in s), s
assert SA.split_sentences("very nice") == ["very nice"]      # two words are kept
assert SA.split_sentences("Good") == []                       # one word is dropped

# threshold is inclusive at 0.35; a sentence can get several aspects
sims = {a: 0.1 for a in CATEGORIES}
sims["scent"], sims["packaging"] = 0.35, 0.5
got = SA.tag(sims, "the smell is nice but the box was crushed")
assert [g[0] for g in got] == ["packaging", "scent"] and all(g[1] == "sbert" for g in got), got

# keyword fallback when nothing passes, on word starts
low = {a: 0.05 for a in CATEGORIES}
assert SA.tag(low, "Delivery was slow") == [("delivery", "keyword", 0.05)]
assert SA.tag(low, "A latest model")[0][0] == "general"          # 'late' must not match 'latest'
assert SA.tag(low, "I bought it last week")[0][0] == "general"

# term
assert SA.term_of("The pump broke", "packaging") == "pump"
assert SA.term_of("Nothing here", "price") == "price"

# review-level rows are derived from sentence rows; general and unscored sentences are skipped
ids = {a: i for i, a in enumerate(CATEGORIES, 1)}
sent = [
    {"sentence": "The pump broke", "aspect": "packaging", "method": "sbert", "sent_score": -0.8, "conf": 0.9},
    {"sentence": "I bought it", "aspect": "general", "method": "general", "sent_score": None, "conf": 0.0},
]
rows = SA.review_rows(7, sent, ids)
assert len(rows) == 1 and rows[0]["aspect_id"] == ids["packaging"] and rows[0]["sentiment"] == -0.8 and rows[0]["method"] == "sbert"

# coverage and centroid/similarity maths with a fake embedder
assert SA.coverage(0, 0) is None and abs(SA.coverage(1484, 2678) - 0.554) < 0.001
import numpy as np
fake = lambda texts: np.tile(np.array([1.0, 0.0]), (len(texts), 1))
c = SA.centroids(fake)
assert abs(np.linalg.norm(c["price"]) - 1) < 1e-9
assert abs(SA.similarities([[1.0, 0.0]], c)[0]["price"] - 1) < 1e-9

assert SA.sentiment_model_for("en") == "roberta" and SA.sentiment_model_for("hi") == "xlmr" and SA.sentiment_model_for(None) == "xlmr"
assert T.ASPECT_SIM == 0.35
print("sentence aspect checks passed")
