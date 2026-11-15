
import random

from app.services.weights import model_weights

rng = random.Random(3)
labels = ["neg", "neu", "pos"]
gold = {i: rng.choice(labels) for i in range(90)}
groups = {i: "english" if i < 60 else "multi" for i in gold}


def onehot(lbl, acc):
    t = lbl if rng.random() < acc else rng.choice(labels)
    return tuple(0.9 if l == t else 0.05 for l in labels)


preds = {"tfidf": {i: onehot(g, 0.5) for i, g in gold.items()},
         "roberta": {i: onehot(g, 0.95) for i, g in gold.items() if i < 60},
         "xlmr": {i: onehot(g, 0.8) for i, g in gold.items() if i >= 60}}
w = model_weights(gold, groups, preds)
assert set(w) == {"english", "multi"} and w["english"]["n"] == 60 and w["multi"]["n"] == 30
assert w["english"]["weights"]["roberta"] > w["english"]["weights"]["tfidf"]
assert "nlptown" not in w["english"]["weights"], "a model with no predictions gets no weight"
assert all(v > 0 for g in w.values() for v in g["weights"].values())
assert model_weights({}, {}, {}) == {}
print("weights checks passed")
