"""Offline check: with two models that are each good on a different kind of text, the text-aware stacker beats the weighted average."""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import mixed as X
from app.services import stacker as S

rng = random.Random(3)
texts, gold, src = [], [], []
probs = {"a": [], "b": []}


def noisy(label, acc):
    c = ("neg", "neu", "pos").index(label)
    if rng.random() > acc:
        c = rng.choice([i for i in range(3) if i != c])
    z = [rng.gauss(0, 0.6) for _ in range(3)]
    z[c] += 2.0
    e = [math.exp(v) for v in z]
    return tuple(v / sum(e) for v in e)


for i in range(1600):
    social = i % 2 == 0
    lab = rng.choice(["neg", "neu", "pos"])
    texts.append("so good #love @you" if social else "The battery lasts the whole day and the screen is sharp and bright, the speakers are clear and loud, delivery was fast, setup took five minutes, and support answered quickly, so I would buy again for sure.")
    gold.append(lab)
    src.append("tweets" if social else X.REVIEW_SOURCE)
    probs["a"].append(noisy(lab, 0.85 if social else 0.45))   # a: good on tweets
    probs["b"].append(noisy(lab, 0.45 if social else 0.85))   # b: good on reviews
res = X.fit_mixed(["a", "b"], probs, texts, gold, src, {"a": 0.6, "b": 0.6})
t = res["per_source"]
assert res["model"] and res["model"]["meta"] is True
assert res["applied"], res["reason"]
for s in ("tweets", X.REVIEW_SOURCE):
    assert t[s]["stacker"]["macro_f1"] > t[s]["weighted_average"]["macro_f1"] + 0.03, (s, t[s])
assert t["tweets"]["stacker"]["macro_f1"] > t["tweets"]["stacker_without_text_clues"]["macro_f1"]
# the saved model works through the production hook, and falls back when the text is missing
m = res["model"]
p = S.predict(m, {"a": probs["a"][0], "b": probs["b"][0]}, texts[0])
assert p and abs(sum(p) - 1) < 1e-9
assert S.predict(m, {"a": probs["a"][0], "b": probs["b"][0]}) is None
# old review-only stackers still load without text
old = S.fit([S.features(["a", "b"], {"a": probs["a"][i], "b": probs["b"][i]}) for i in range(300)], gold[:300], ["a", "b"])
assert S.predict(old, {"a": probs["a"][0], "b": probs["b"][0]}) is not None
assert len(S.meta_features("Great #phone!")) == 9
print("\n".join(X.md_table(res)))
print("mixed checks ok")
