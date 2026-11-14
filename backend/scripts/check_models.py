from app.services import sentiment

SAMPLES = ["Great scent, but the pump broke after a week.", "Absolutely love it", "Terrible, broke on day one",
           "Bahut accha product hai but price thoda zyada hai"]
for cfg in sentiment.configured():
    print("\n==", cfg["name"], cfg["version"], cfg["role"])
    try:
        sc = sentiment.get_scorer(cfg)
        print("labels:", sc.mapping)
        for t, (n, u, p, e) in zip(SAMPLES, sc.predict(SAMPLES)):
            print(f"  neg={n:.2f} neu={u:.2f} pos={p:.2f} stars={'-' if e is None else format(e, '.2f')}  {t}")
    except Exception as ex:
        print("  FAILED:", type(ex).__name__, str(ex)[:300])
