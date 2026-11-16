"""Offline checks for the own-data retraining gate and training. Run: python -m tests.check_retrain_own"""
import random
from collections import Counter

from scripts.retrain_own import check_ready, label3, train

assert label3(1) == "neg" and label3(3) == "neu" and label3(4.6) == "pos"
assert "needs 2000" in check_ready(1500, Counter(neg=500, neu=500, pos=500))
assert "neu" in check_ready(2100, Counter(neg=1000, neu=10, pos=1090))
assert check_ready(2100, Counter(neg=700, neu=700, pos=700)) is None
assert check_ready(300, Counter(neg=100, neu=100, pos=100), min_rated=300) is None

rnd = random.Random(1)
words = {"neg": ["awful", "broken", "refund", "waste"], "neu": ["okay", "average", "fine", "decent"], "pos": ["great", "love", "perfect", "excellent"]}
texts, labels = [], []
for _ in range(600):
    y = rnd.choice(["neg", "neu", "pos"])
    texts.append(" ".join(rnd.choices(words[y], k=4) + ["the", "product"])); labels.append(y)
pipe, f1, acc = train(texts, labels)
assert f1 > 0.9 and acc > 0.9
assert list(pipe.predict(["great love perfect"])) == ["pos"]
print("retrain_own checks passed")
