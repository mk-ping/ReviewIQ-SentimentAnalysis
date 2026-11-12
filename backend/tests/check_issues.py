from app.services.embeddings import embed
from app.services.issues import cluster, lift

T = ["the pump broke after two days", "pump stopped working", "parcel arrived very late", "delivery was delayed by a week"]
sim = embed(T) @ embed(T).T
print(sim.round(2))
labels = cluster(T)
print("clusters:", labels)
assert labels[0] == labels[1] and labels[2] == labels[3] and labels[0] != labels[2], labels

old, new, n = lift({1: 5.0, 2: 1.0, 3: 1.0, 4: 3.0}, {2, 3})
assert old == 2.5 and abs(new - 4.0) < 1e-9 and n == 2, (old, new, n)
old, new, n = lift({1: 5.0, 2: 5.0}, {1})
assert new == old == 5.0 and n == 0, "must never lower a rating"
print("issue checks passed")
