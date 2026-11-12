import json
import sys

a = json.load(open(sys.argv[1]))["blind_spots"]
b = json.load(open(sys.argv[2]))["blind_spots"]
key = lambda d: d["aspect"]
a, b = sorted(a, key=key), sorted(b, key=key)
print("before:", [(x["aspect"], x["negative_mentions"], x["in_4_5_star"]) for x in a])
print("after: ", [(x["aspect"], x["negative_mentions"], x["in_4_5_star"]) for x in b])
assert a == b, "blind spots changed after moving to the view"
print("hidden view check passed")
