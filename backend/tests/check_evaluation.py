from app.services import evaluation as E

gold = ["pos", "pos", "neg", "neg", "neu", "neu", "pos", "neg"]
pred = ["pos", "neg", "neg", "neg", "neu", "pos", "pos", "pos"]

pc = E.per_class(gold, pred)
# neg: tp=2, fp=1 (gold pos predicted neg), fn=1 (gold neg predicted pos)
assert pc["neg"]["precision"] == 2 / 3 and pc["neg"]["recall"] == 2 / 3 and abs(pc["neg"]["f1"] - 2 / 3) < 1e-9, pc["neg"]
assert pc["neu"]["support"] == 2 and pc["neu"]["recall"] == 0.5
assert abs(E.macro_f1(gold, pred) - sum(v["f1"] for v in pc.values()) / 3) < 1e-9
assert E.accuracy(gold, pred) == 5 / 8
assert E.confusion(gold, pred)["pos"]["neg"] == 1 and sum(sum(r.values()) for r in E.confusion(gold, pred).values()) == 8

# a class absent from the gold labels is left out, not scored as zero
assert E.macro_f1(["pos", "pos"], ["pos", "neg"]) == E.per_class(["pos", "pos"], ["pos", "neg"])["pos"]["f1"]
assert E.macro_f1([], []) is None and E.accuracy([], []) is None

assert E.stars_to_label(1) == "neg" and E.stars_to_label(3) == "neu" and E.stars_to_label(4.4) == "pos" and E.stars_to_label(None) is None
assert E.argmax_label(0.1, 0.2, 0.7) == "pos" and E.argmax_label(0.6, 0.3, 0.1) == "neg"

ci = E.bootstrap_macro_f1(gold * 5, pred * 5)
assert ci and 0 <= ci[0] <= E.macro_f1(gold, pred) <= ci[1] <= 1, ci
assert E.bootstrap_macro_f1(gold * 2, pred * 2) is not None and E.bootstrap_macro_f1(gold, pred) is None

b = E.binary_precision_recall([True, True, False, False, True], [True, False, True, False, True])
assert b["precision"] == 2 / 3 and b["recall"] == 2 / 3 and b["flagged"] == 3 and b["true_mismatches"] == 3
assert E.binary_precision_recall([False, False], [False, False])["precision"] is None

# perfectly calibrated, then badly overconfident
cal = E.calibration([0.95] * 20, [True] * 19 + [False])
assert cal["ece"] == 0.0, cal
over = E.calibration([0.95] * 10, [True] * 5 + [False] * 5)
assert abs(over["ece"] - 0.45) < 1e-6, over
assert E.calibration([], [])["ece"] is None
print("evaluation checks passed")
