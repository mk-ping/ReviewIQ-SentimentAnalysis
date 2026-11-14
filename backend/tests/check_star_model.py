
"""Downloads nlptown once. Prints the label -> stars mapping and checks ordering on clear examples."""
from app.services.model_registry import STAR_LANGUAGES
from app.services.sentiment import get_scorer

cfg = {"name": "nlptown/bert-base-multilingual-uncased-sentiment",
       "source": "nlptown/bert-base-multilingual-uncased-sentiment", "version": "pretrained",
       "role": "core", "languages": STAR_LANGUAGES}
sc = get_scorer(cfg)
print("label -> stars:", sc.mapping)
assert sorted(sc.mapping.values()) == [1, 2, 3, 4, 5]

bad, ok, good = sc.predict([
    "Terrible. Broke on day one, total waste of money.",
    "It is okay, does the job.",
    "Absolutely fantastic, best purchase I have made this year.",
])
print("expected stars:", round(bad[3], 2), round(ok[3], 2), round(good[3], 2))
assert bad[3] < ok[3] < good[3], "ordering failed - fix label_to_star"
assert bad[0] > bad[2] and good[2] > good[0]
print("star model checks passed")
