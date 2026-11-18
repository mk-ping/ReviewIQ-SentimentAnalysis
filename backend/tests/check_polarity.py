"""Offline check of the label-orientation detector on synthetic Hindi and Hinglish rows."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import polarity_check as P

rng = random.Random(4)
POSL = ["\u092f\u0939 \u092c\u0939\u0941\u0924 \u0905\u091a\u094d\u091b\u093e \u0939\u0948", "\u092c\u0922\u093c\u093f\u092f\u093e \u092a\u094d\u0930\u094b\u0921\u0915\u094d\u091f", "bahut accha laga", "great phone love it", "\u092e\u0941\u091d\u0947 \u092f\u0939 \u092a\u0938\u0902\u0926 \u0906\u092f\u093e", "ok ok sab theek"]
NEGL = ["\u092f\u0939 \u092c\u0947\u0915\u093e\u0930 \u0939\u0948", "\u092c\u0939\u0941\u0924 \u0916\u0930\u093e\u092c \u0938\u0930\u094d\u0935\u093f\u0938", "ekdum bekar", "worst waste of money", "\u0918\u091f\u093f\u092f\u093e \u0915\u094d\u0935\u093e\u0932\u093f\u091f\u0940", "kuch nahi mila"]
good = [(rng.choice(POSL), 2) for _ in range(100)] + [(rng.choice(NEGL), 0) for _ in range(100)] + [("theek hai", 1)] * 20
flip = [(t, P.swap(y)) for t, y in good]
assert P.orientation(good)["verdict"] == "ok"
assert P.orientation(flip)["verdict"] == "inverted"
assert P.orientation(good[:10])["verdict"] == "unclear"
assert P.orientation([("same text", 2)] * 50 + [("same text", 0)] * 50)["verdict"] == "unclear"
assert P.swap(0) == 2 and P.swap(2) == 0 and P.swap(1) == 1
print("polarity checks ok")
