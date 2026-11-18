"""Offline checks for the benchmark helpers (no downloads)."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import benchmark as B

assert B.polarity(0, ["negative", "neutral", "positive"], "3") == "neg"
assert B.polarity(2, ["negative", "neutral", "positive"], "3") == "pos"
assert B.polarity(1, None, "3") == "neu"
assert B.polarity(0, None, "5") == "neg" and B.polarity(3, None, "5") == "pos" and B.polarity(2, None, "5") == "neu"
assert B.polarity(1, None, "2") == "pos" and B.polarity("Bearish", None, "3") == "neg"
assert B.polarity("positive", None, "3") == "pos" and B.polarity(9, None, "3") is None
assert B.pick_columns(["idx", "Sentence", "label"]) == ("Sentence", "label")
assert B.pick_columns(["a", "b"]) == (None, None)

rng = random.Random(1)
rows = [("t%d" % i, rng.choice(["neg", "pos", "pos", "neu"])) for i in range(2000)]
s = B.stratified(rows, 400)
assert len(s) <= 400 and abs(sum(1 for r in s if r[1] == "pos") / len(s) - 0.5) < 0.06
assert len(B.stratified(rows[:50], 400)) == 50

assert B.decide((0.5, 0.4, 0.1), True) == "neg" and B.decide((0.3, 0.6, 0.1), False) == "neu"
gold = ["pos"] * 60 + ["neg"] * 40
good = [(0.1, 0.1, 0.8)] * 54 + [(0.8, 0.1, 0.1)] * 6 + [(0.8, 0.1, 0.1)] * 36 + [(0.1, 0.1, 0.8)] * 4
r = B.score_system(gold, good, True)
assert abs(r["accuracy"] - 0.9) < 1e-9 and r["accuracy_ci"][0] < 0.9 < r["accuracy_ci"][1] + 1e-9
assert r["per_class"]["neu"]["support"] == 0
# a model that predicts mostly neutral is not penalised on binary sets: only neg/pos compete
r2 = B.score_system(gold, [(0.2, 0.7, 0.1)] * 100, True)
assert r2["confusion"][1] == [0, 0, 0]
md = "\n".join(B.table_for("demo", "Demo set", 100, {"pos": 60, "neg": 40}, {"a": r, "b": r2}))
assert "| a |" in md and "| b |" in md
print("benchmark checks ok")
