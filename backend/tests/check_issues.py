"""Offline checks for issue clustering and the what-if lift. Run: python -m tests.check_issues"""
import numpy as np

from app.services.issue_cluster import c_tfidf, cluster_kmeans, rare_flags
from app.services.issues import lift

rng = np.random.default_rng(0)
dirs = np.eye(8)[:3]
X = np.vstack([d + rng.normal(0, 0.05, (40, 8)) for d in dirs])
X /= np.linalg.norm(X, axis=1, keepdims=True)
labels, centers = cluster_kmeans(X)
assert len(set(labels)) == 3, set(labels)                                   # silhouette picks k = 3 from 2..4
assert len({tuple(labels[i * 40:(i + 1) * 40]) for i in range(3)}) == 3 and all(len(set(labels[i * 40:(i + 1) * 40])) == 1 for i in range(3))
print("KMeans picked k =", len(set(labels)))

# one point pushed away from its centre is flagged as rare
Y = X.copy()
Y[0] = Y[0] + np.array([0.6, 0, 0, 0, 0, 0, 0, 0.6])
flags = rare_flags(Y, labels, centers)
assert flags[0] and sum(flags) <= 6, (flags[0], sum(flags))
print("rare complaints flagged:", sum(flags))

texts = ["the pump broke", "pump stopped working", "pump leaks badly", "parcel arrived late", "delivery was delayed", "late delivery again"]
kw = c_tfidf(texts, [0, 0, 0, 1, 1, 1])
assert "pump" in kw[0] and any(w in kw[1] for w in ("late", "delivery")), kw
print("c-TF-IDF:", kw)

old, new, n = lift({1: 5.0, 2: 1.0, 3: 1.0, 4: 3.0}, {2, 3})
assert old == 2.5 and abs(new - 4.0) < 1e-9 and n == 2, (old, new, n)
old, new, n = lift({1: 5.0, 2: 5.0}, {1})
assert new == old == 5.0 and n == 0, "must never lower a rating"
print("issue checks passed")
