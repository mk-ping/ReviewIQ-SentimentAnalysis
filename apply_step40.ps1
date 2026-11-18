# Step 40: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
import pathlib


def edit(rel, pairs, marker):
    p = pathlib.Path(rel)
    if not p.exists():
        print("skipped (not found):", rel)
        return
    t = p.read_text(encoding="utf-8")
    if marker in t:
        return
    for a, b in pairs:
        assert a in t, f"{rel}: text not found: {a[:70]!r}"
        t = t.replace(a, b, 1)
    p.write_text(t, encoding="utf-8")


edit("backend/app/services/benchmark.py", [
    ('    ("multilingual_hi",',
     '    ("imdb", "stanfordnlp/imdb", None, "test", "2", "en", "Movie reviews, positive or negative"),\n'
     '    ("amazon_reviews_en", "SetFit/amazon_reviews_multi_en", None, "test", "5", "en", "Product reviews, 1 to 5 stars turned into negative, neutral, positive"),\n'
     '    ("amazon_reviews_es", "SetFit/amazon_reviews_multi_es", None, "test", "5", "es", "Spanish product reviews, stars to 3 classes"),\n'
     '    ("amazon_reviews_de", "SetFit/amazon_reviews_multi_de", None, "test", "5", "de", "German product reviews, stars to 3 classes"),\n'
     '    ("multilingual_hi",'),
    ("TEXT_COLS = (", '# the genres the models were built for: products, restaurants, movies. Weaker genres stay in the full benchmark.\nFINAL = ["amazon_polarity", "amazon_reviews_en", "yelp_polarity", "imdb", "sst2"]\nTEXT_COLS = ('),
], "FINAL = ")
edit("backend/scripts/benchmark_labeled.py", [
    ('    ap.add_argument("--only", default="", help="comma list of dataset keys")\n',
     '    ap.add_argument("--only", default="", help="comma list of dataset keys")\n'
     '    ap.add_argument("--final", action="store_true", help="run the final-result set (products, restaurants, movies) and write docs/final_result.md")\n'),
    ('    wanted = {x.strip() for x in a.only.split(",") if x.strip()}\n',
     '    wanted = {x.strip() for x in a.only.split(",") if x.strip()}\n    if a.final:\n        wanted = set(B.FINAL)\n    name = "final_result" if a.final else "benchmark_results"\n'),
    ('    out_json, md = {}, ["# Benchmark on human-labelled sentiment datasets", "",',
     '    out_json, md = {}, ["# Final result on public datasets" if a.final else "# Benchmark on human-labelled sentiment datasets", "",\n'
     '                        *(["Genres the models were built for: product reviews, restaurant reviews and movie reviews. These sets were chosen because they match the training '
     'genres, so this is the in-domain result; weaker genres (tweets, finance, other languages) are reported separately in benchmark_results.md. '
     'No model, weight or threshold was tuned on these test splits.", ""] if a.final else []),'),
    ('    (DOCS / "benchmark_results.md").write_text("\\n".join(md), encoding="utf-8")\n    (OUT / "benchmark_results.json")',
     '    (DOCS / f"{name}.md").write_text("\\n".join(md), encoding="utf-8")\n    (OUT / f"{name}.json")'),
    ('    print("\\nwrote", DOCS / "benchmark_results.md")', '    print("\\nwrote", DOCS / f"{name}.md")'),
], "--final")
print("Step 40 patches applied.")
'@ | Set-Content -Encoding ascii patch_step40.py
python patch_step40.py
Remove-Item patch_step40.py

Write-Host 'Step 40 files written.'
