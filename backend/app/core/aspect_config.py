"""Aspect configuration (final pipeline document, section 8). Edit here, nothing else needs to change.

Seven aspects, each with 6 seed phrases that mix good and bad examples (8 to 10 are planned per business).
SBERT turns the seeds into a centroid; a sentence gets every aspect whose cosine similarity is ASPECT_SIM or more.
STEMS are the word starts used by the keyword fallback when no aspect passes the similarity test."""

CATEGORIES = ["quality", "price", "scent", "packaging", "delivery", "results", "ease of use"]

SEEDS = {
    "quality": ["great quality product", "poor quality, feels cheap", "well made and sturdy",
                "it broke after a few days", "defective item received", "excellent build and finish"],
    "price": ["very good value for money", "too expensive for what you get", "reasonably priced",
              "completely overpriced", "worth every rupee", "cheap and affordable"],
    "scent": ["lovely fragrance", "the smell is awful", "smells fresh and nice",
              "strong chemical odour", "pleasant mild scent", "the perfume lasts long"],
    "packaging": ["packed very well", "the box was damaged", "the bottle leaked in the parcel",
                  "the pump stopped working", "neat and secure packaging", "the cap was broken on arrival"],
    "delivery": ["arrived on time", "delivery was very late", "fast shipping",
                 "the courier delayed my order", "delivered earlier than expected", "the parcel never reached me"],
    "results": ["it really works, I saw results", "no visible difference after weeks", "my skin feels better after using it",
                "it did not work for me at all", "effective with noticeable results", "it made my problem worse"],
    "ease of use": ["very easy to use", "hard to apply", "simple setup and clear instructions",
                    "confusing and difficult to use", "convenient to use every day", "complicated to open"],
}

# regex word starts for the keyword fallback (a word must START with one of these)
STEMS = {
    "quality": ["quality", "defect", "faulty", "broke", "broken", "build", "durab", "sturdy", "damag", "cheap material"],
    "price": ["price", "expens", "cheap", "costly", "overpriced", "value", "worth", "afford", "mehng", "sast", "paisa", "paise"],
    "scent": ["smell", "scent", "fragran", "perfume", "odor", "odour", "khushbu", "aroma"],
    "packaging": ["packag", "packing", "packed", "box", "bottle", "pump", "leak", r"cap\b", "seal", "wrapper", "carton"],
    "delivery": ["deliver", "shipp", "courier", "arriv", "dispatch", "parcel", r"late\b", "delay"],
    "results": ["result", "work", "effect", "differen", "improv", "skin", "hair", "useless", "bekar", "faayda"],
    "ease of use": ["easy", "difficult", "hard to", "simple", "convenien", "setup", "instruction", "apply", "user friendly"],
}

# plain keyword lists kept for the older keyword helper in services/aspects.py
KEYWORDS = {c: [s.replace("\\b", "") for s in STEMS[c]] for c in CATEGORIES}
