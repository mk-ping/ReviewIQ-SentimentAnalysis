import sys

import httpx

BASE = "http://127.0.0.1:8010"
bad = []
with httpx.Client(base_url=BASE, timeout=60) as c:
    rvt = c.get("/rating-vs-text").json()
    mm = c.get("/mismatches?limit=1").json()
    summ = c.get("/summary").json()
    dist = c.get("/distribution").json()
    hid = c.get("/hidden-dissatisfaction?limit=1").json()

    print("rating-vs-text mismatches:", rvt["mismatches"], "| /mismatches total:", mm["total"])
    if rvt["mismatches"] != mm["total"]:
        bad.append("mismatch counts differ between /rating-vs-text and /mismatches")

    print("summary rated:", summ["rated_reviews"], "| distribution n:", dist["n"])
    if summ["rated_reviews"] != dist["n"]:
        bad.append("rated review counts differ between /summary and /distribution")

    print("hidden:", hid["hidden_reviews"], "of", hid["rated_4plus_analysed"])
    if hid["hidden_reviews"] > hid["rated_4plus_analysed"]:
        bad.append("more hidden reviews than analysed reviews rated 4 or 5")

if bad:
    print("FAILURES:")
    for b in bad:
        print(" -", b)
    sys.exit(1)
print("consistency checks passed")
