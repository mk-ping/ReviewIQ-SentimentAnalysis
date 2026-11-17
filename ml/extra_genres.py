"""More genres for training: hotel reviews (TripAdvisor) and app reviews (Google Play). Both give 1 to 5 stars.
Every loader skips itself with a message if the download fails. Streams the data, so nothing huge is stored."""
import random

SEED = 7

# (hf id, source name, text column, star column, star offset, group column, language)
GENRES = [
    ("jniimi/tripadvisor-review-rating", "tripadvisor", "review", "overall", 1, "hotel_id", "en"),
    ("sealuzh/app_reviews", "app_reviews", "review", "star", 1, "package_name", "en"),
]


def load_genres(per_star, row, norm, keep):
    from datasets import load_dataset

    out = []
    for hid, name, tcol, scol, off, gcol, lang in GENRES:
        try:
            ds = load_dataset(hid, split="train", streaming=True).shuffle(seed=SEED, buffer_size=20000)
        except Exception as e:
            print(f"  skip {name}: {type(e).__name__}: {str(e)[:100]}")
            continue
        got = [0] * 5
        scanned = 0
        try:
            for ex in ds:
                scanned += 1
                if scanned > 400000 or all(g >= per_star for g in got):
                    break
                try:
                    star = int(round(float(ex[scol]))) - off
                except (TypeError, ValueError, KeyError):
                    continue
                if not 0 <= star <= 4 or got[star] >= per_star:
                    continue
                t = norm(str(ex.get(tcol) or ""))
                if not keep(t):
                    continue
                out.append(row(t, star=star, src=name, group=f"{name}:{ex.get(gcol, '')}" if gcol else "", lang=lang))
                got[star] += 1
        except Exception as e:
            print(f"  {name}: stopped early: {type(e).__name__}: {str(e)[:100]}")
        print(f"  {name}: {sum(got)} rows, per star {got}")
    return out
