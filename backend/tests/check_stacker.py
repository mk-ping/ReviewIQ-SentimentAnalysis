"""Offline checks for the stacker: it learns model habits, is gated honestly, and production falls back safely.
Run: python -m tests.check_stacker  (needs scikit-learn and numpy; no database, no model downloads)"""
import json
import math
import random
import tempfile
from pathlib import Path

from app.services import metrics as M
from app.services import stacker as S

L = list(M.LABELS)


def simulate(n, seed, habits):
    """Fake model outputs. habits[model] = (signal strength, bias towards neg, neu, pos). Class mix is realistic: few neutrals."""
    rng = random.Random(seed)
    gold = rng.choices(L, weights=[0.3, 0.15, 0.55], k=n)
    probs = {k: [] for k in habits}
    for y in gold:
        for k, (strength, bias) in habits.items():
            z = [rng.gauss(0, 1) + bias[c] for c in range(3)]
            z[L.index(y)] += strength
            e = [math.exp(v) for v in z]
            probs[k].append(tuple(v / sum(e) for v in e))
    return gold, probs


HABITS = {"a": (1.2, [0.0, -1.2, 0.3]), "b": (0.9, [0.2, 0.8, -0.2]), "c": (0.6, [0.0, 0.0, 0.0])}
members = list(HABITS)
vg, vp = simulate(2400, 1, HABITS)
tg, tp = simulate(900, 2, HABITS)
w = {k: M.report(vg, [L[max(range(3), key=lambda c: p[c])] for p in vp[k]])["macro_f1"] for k in members}

res = S.train_group(members, vp, vg, w)
assert res["model"] is not None and res["applied"], res["reason"]
cmp = S.compare(res["model"], members, tp, tg, w)
base, st = cmp["weighted_average"], cmp["stacker"]
assert st["macro_f1"] > base["macro_f1"], (st["macro_f1"], base["macro_f1"])
assert st["per_class"]["neu"]["recall"] > base["per_class"]["neu"]["recall"]      # the neutral class is where it helps most
assert cmp["paired"]["verdict"] == "beats" and cmp["mcnemar"]["p_value"] < 0.05
assert abs(sum(S.predict(res["model"], {k: tp[k][0] for k in members})) - 1) < 1e-9
print(f"simulated: macro F1 {base['macro_f1']:.3f} -> {st['macro_f1']:.3f}, neutral recall {base['per_class']['neu']['recall']:.2f} -> {st['per_class']['neu']['recall']:.2f}")

# honesty gate: small validation set, and models that are already well balanced, must NOT be applied
sg, sp = simulate(120, 3, HABITS)
small = S.train_group(members, sp, sg, w)
assert not small["applied"] and "validation reviews" in small["reason"]
flat = {"a": (1.4, [0, 0, 0]), "b": (1.4, [0, 0, 0])}
fg, fp = simulate(900, 4, flat)
fw = {k: M.report(fg, [L[max(range(3), key=lambda c: p[c])] for p in fp[k]])["macro_f1"] for k in flat}
bal = S.train_group(list(flat), fp, fg, fw)
assert bal["model"] is None or not bal["applied"] or bal["model"]["cv_diff"] >= S.MIN_GAIN
assert S.train_group(members, {k: v[:20] for k, v in vp.items()}, vg[:20], w)["applied"] is False
two = S.train_group(members, {k: v[:50] for k, v in vp.items()}, ["pos"] * 50, w)
assert two["model"] is None and not two["applied"]

# production hook: used only when applied, falls back for missing files, missing members and not-applied models
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    fallback = (0.2, 0.3, 0.5)
    assert S.refine("english", {k: tp[k][0] for k in members}, fallback, d) == fallback            # no file
    (d / "stacker_english.json").write_text(json.dumps(res["model"]))
    S._cache.clear()
    out = S.refine("english", {k: tp[k][0] for k in members}, fallback, d)
    assert out != fallback and abs(sum(out) - 1) < 1e-9
    assert S.refine("english", {"a": tp["a"][0]}, fallback, d) == fallback                           # a member model did not run
    (d / "stacker_multi.json").write_text(json.dumps({**res["model"], "applied": False}))
    S._cache.clear()
    assert S.refine("multi", {k: tp[k][0] for k in members}, fallback, d) == fallback                # not gated in
    (d / "stacker_european.json").write_text("{broken")
    S._cache.clear()
    assert S.refine("european", {k: tp[k][0] for k in members}, fallback, d) == fallback             # corrupt file
print("stacker checks passed")
