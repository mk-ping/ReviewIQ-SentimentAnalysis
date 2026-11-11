from app.services.detection import assign
from app.services.profiling import profile_column

header = ["Product", "Stars", "Review", "Posted"]
rows = [
    ["Lip balm", "5/5", "Smooth and lasting", "14/03/2026"],
    ["Lip balm", "2/5", "Melts in the heat", "18/03/2026"],
    ["Face wash", "4/5", "Gentle on skin", "21/03/2026"],
]
profiles = [profile_column(n, [r[i] for r in rows]) for i, n in enumerate(header)]
res = {r.role: (r.column, r.action) for r in assign(profiles)}
print(res)
assert res["product"][0] == "Product", res
assert res["title"][0] is None, res
assert res["text"][0] == "Review", res
assert res["rating"][0] == "Stars", res
assert res["date"][0] == "Posted", res
print("detection checks passed")
