"""Offline checks for the ABSA agreement and topic summary helpers. Run: python -m tests.check_extras"""
from app.services.extras import absa_label, agreement, band, kappa, summarise_topics

assert band(0.6) == "pos" and band(-0.25) == "neg" and band(0.1) == "neu" and band(0.25) == "pos"
assert absa_label("Positive") == "pos" and absa_label(" NEGATIVE ") == "neg" and absa_label("LABEL_1") is None and absa_label(None) is None

perfect = [("p", "pos", "pos"), ("p", "neg", "neg"), ("q", "neu", "neu"), ("q", "pos", "pos")]
a = agreement(perfect)
assert a["n"] == 4 and a["agree_rate"] == 1.0 and a["kappa"] == 1.0
mixed = [("price", "pos", "pos"), ("price", "pos", "neg"), ("scent", "neg", "neg"), ("scent", "neu", "pos"), ("scent", "neg", "neg"), ("x", "weird", "pos")]
m = agreement(mixed)
assert m["n"] == 5 and m["agree_rate"] == 0.6                        # the unknown label is not counted
assert m["confusion"]["pos"]["neg"] == 1 and m["confusion"]["neu"]["pos"] == 1
assert [d["aspect"] for d in m["by_aspect"]] == ["scent", "price"] and m["by_aspect"][0]["agree_rate"] == 0.667
assert kappa([("pos", "neg"), ("neg", "pos")]) < 0                    # worse than chance
assert kappa([]) is None and agreement([])["agree_rate"] is None

docs = ["box crushed", "arrived damaged", "scent too strong", "smell faint", "app keeps crashing", "login fails", "weird", "?"]
ids = [0, 0, 1, 1, 2, 2, -1, -1]
asp = ["packaging", "packaging", "scent", "scent", "general", "general", "general", "general"]
t = summarise_topics(docs, ids, asp, {0: ["box", "damaged"], 1: ["scent"], 2: ["app", "crash"]})
assert t["outliers"] == 2 and t["outlier_share"] == 0.25 and len(t["topics"]) == 3
by = {x["topic"]: x for x in t["topics"]}
assert by[2]["emerging"] is True and by[0]["emerging"] is False and by[0]["dominant_aspect"] == "packaging"
assert by[2]["words"] == ["app", "crash"] and len(by[0]["examples"]) == 2
print("extras checks passed")
