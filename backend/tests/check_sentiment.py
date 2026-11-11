from app.services.sentiment import load, predict

device, mapping = load()
print("device:", device)
print("label -> stars:", mapping)

SAMPLES = [
    "Great scent, but the pump broke after a week.",
    "Absolutely love it, best purchase this year",
    "Terrible. Broke on day one and support ignored me.",
    "Very nice product",
    "Bahut accha product hai but price thoda zyada hai",
    "Producto malo, llego roto y muy tarde",
]
for text, (n, u, p, e) in zip(SAMPLES, predict(SAMPLES)):
    print(f"neg={n:.2f} neu={u:.2f} pos={p:.2f} stars={e:.2f}  {text}")
    assert abs(n + u + p - 1) < 1e-4
print("sentiment checks passed")
