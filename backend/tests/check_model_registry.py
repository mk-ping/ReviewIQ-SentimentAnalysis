
from types import SimpleNamespace as NS

from app.services.model_registry import configured, label_to_polarity, label_to_star, runs_on

cfg = NS(sentiment_model="p/primary", star_model="s/star", cardiff_model="")
ms = configured(cfg)
assert [m["name"] for m in ms] == ["p/primary", "s/star"], ms
assert ms[0]["role"] == "core" and ms[0]["languages"] is None

assert [m["name"] for m in configured(NS(sentiment_model="p", star_model="", cardiff_model=""))] == ["p"]
assert [m["name"] for m in configured(NS(sentiment_model="p", star_model="s", cardiff_model="c"))] == ["p", "s", "c"]

star = ms[1]
for lang in ("en", "es", "fr", "de", "it", "nl"):
    assert runs_on(star, lang), lang
for lang in ("hi", "hinglish", "und", "ar", "pt", None):
    assert not runs_on(star, lang), lang
assert runs_on(ms[0], "hi") and runs_on(ms[0], None)

assert [label_to_star(x) for x in ["1 star", "2 stars", "3 stars", "4 stars", "5 stars"]] == [1, 2, 3, 4, 5]
assert [label_to_star(x) for x in ["Very Negative", "Negative", "Neutral", "Positive", "Very Positive"]] == [1, 2, 3, 4, 5]
assert label_to_star("LABEL_9") is None
assert [label_to_polarity(x) for x in ["negative", "neutral", "positive"]] == [0, 1, 2]
print("model registry checks passed")
