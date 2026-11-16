from app.services import sentiment

SAMPLES = ["Great scent, but the pump broke after a week.", "Absolutely love it, best purchase this year",
           "Terrible. Broke on day one and support ignored me.", "Very nice product",
           "Bahut accha product hai but price thoda zyada hai", "Producto malo, llego roto y muy tarde"]
for key in sentiment.registry():
    if not sentiment.available(key):
        print(f"\n== {key}: not available yet")
        continue
    print(f"\n== {key}: {sentiment.registry()[key]['name']}")
    sc = sentiment.get_scorer(key)
    print("labels:", sc.mapping)
    out = sc.predict(SAMPLES)
    for t, (n, u, p, e) in zip(SAMPLES, out):
        assert abs(n + u + p - 1) < 1e-4
        print(f"  neg={n:.2f} neu={u:.2f} pos={p:.2f} stars={'-' if e is None else format(e, '.2f')}  {t}")
    if key != "tfidf":   # ordering guard on the English samples: a wrong label order would flip these
        assert out[2][0] > out[2][2], f"{key}: 'Terrible' should lean negative"
        assert out[1][2] > out[1][0], f"{key}: 'love it' should lean positive"
print("\nsentiment checks passed")
