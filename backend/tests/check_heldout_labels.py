from scripts.eval_heldout import label_of

assert label_of({"star": 0, "pol": -1}) == "neg" and label_of({"star": 1, "pol": -1}) == "neg"
assert label_of({"star": 2, "pol": -1}) == "neu"
assert label_of({"star": 3, "pol": -1}) == "pos" and label_of({"star": 4, "pol": -1}) == "pos"
assert [label_of({"star": -1, "pol": p}) for p in (0, 1, 2)] == ["neg", "neu", "pos"]
print("heldout label checks passed")
