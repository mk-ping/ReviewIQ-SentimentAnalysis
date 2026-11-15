"""Issue clustering (final pipeline document, section 10). Pure functions, so they test offline.

Per aspect: KMeans for k from ISSUE_K_MIN to ISSUE_K_MAX, the silhouette score picks k, each cluster is named with
c-TF-IDF, and a sentence farther from its cluster centre than mean + ISSUE_RARE_STD x std is flagged as a rare complaint."""
import numpy as np

from app.core import thresholds as T


def cluster_kmeans(X):
    """Returns (labels, centers). Falls back to one cluster when no k gives two real clusters."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    X = np.asarray(X, dtype=float)
    n = len(X)
    best = None
    for k in range(T.ISSUE_K_MIN, min(T.ISSUE_K_MAX, n - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=T.KMEANS_SEED).fit(X)
        if len(set(km.labels_.tolist())) < 2:
            continue
        score = silhouette_score(X, km.labels_)
        if best is None or score > best[0]:
            best = (score, km)
    if best is None:
        return [0] * n, X.mean(axis=0, keepdims=True)
    return [int(v) for v in best[1].labels_], best[1].cluster_centers_


def rare_flags(X, labels, centers) -> list[bool]:
    """True for sentences farther from their cluster centre than mean + 2 std (clusters of 5 or more only)."""
    X = np.asarray(X, dtype=float)
    lab = np.asarray(labels)
    dist = np.linalg.norm(X - np.asarray(centers)[lab], axis=1)
    out = np.zeros(len(X), dtype=bool)
    for c in set(lab.tolist()):
        idx = np.where(lab == c)[0]
        if len(idx) >= 5:
            cut = dist[idx].mean() + T.ISSUE_RARE_STD * dist[idx].std()
            out[idx] = dist[idx] > cut
    return [bool(v) for v in out]


def c_tfidf(texts: list[str], labels, top: int = 3) -> dict[int, list[str]]:
    """Class-based TF-IDF: each cluster is one document. Returns the top words per cluster label."""
    from sklearn.feature_extraction.text import CountVectorizer

    labs = sorted(set(int(v) for v in labels))
    docs = [" ".join(t for t, l in zip(texts, labels) if int(l) == c) for c in labs]
    cv = CountVectorizer(stop_words="english", token_pattern=r"(?u)\b[^\W\d_]{3,}\b")
    try:
        counts = cv.fit_transform(docs).toarray().astype(float)
    except ValueError:
        return {}
    words = cv.get_feature_names_out()
    tf = counts / np.clip(counts.sum(axis=1, keepdims=True), 1, None)
    avg_words = counts.sum() / len(labs)
    idf = np.log(1 + avg_words / np.clip(counts.sum(axis=0), 1, None))
    score = tf * idf
    return {c: [str(words[j]) for j in score[i].argsort()[::-1][:top] if score[i][j] > 0] for i, c in enumerate(labs)}
