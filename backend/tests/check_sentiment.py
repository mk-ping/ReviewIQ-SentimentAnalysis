from app.services import sentiment

SAMPLES = ["Great scent, but the pump broke after a week.", "Absolutely love it, best purchase this year",
           "Terrible. Broke on day one and support ignored me.", "Very nice product",
           "Bahut accha product hai but price thoda zyada hai", "Producto malo, llego roto y muy tarde"]
for key, cfg in sentiment.registry().items():
    if not sentiment.available(key):
        print(f"\n== {key}: not available yet")
        continue
    print(f"\n== {key}: {cfg['name']}")
    try:
        sc = sentiment.get_scorer(key)
        print("labels:", sc.mapping)
        for t, (n, u, p, e) in zip(SAMPLES, sc.predict(SAMPLES)):
            assert abs(n + u + p - 1) < 1e-4
            print(f"  neg={n:.2f} neu={u:.2f} pos={p:.2f} stars={'-' if e is None else format(e, '.2f')}  {t}")
    except Exception as ex:
        print("  FAILED:", type(ex).__name__, str(ex)[:300])
print("\ndone")
