# Step 31: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Aspect profiles for different kinds of reviews: products, restaurants, hotels, movies, apps and a general fallback.
Each profile has aspect names, 6 seed phrases per aspect (good and bad examples mixed) and word starts for the keyword
fallback. The domain is detected per product from the review text, so one upload can mix restaurants and gadgets.
Set ASPECT_DOMAIN in .env to force one profile. Add a new profile by adding one entry to PROFILES."""
import re

from app.core.aspect_config import CATEGORIES as P_CATS, SEEDS as P_SEEDS, STEMS as P_STEMS

PROFILES: dict[str, dict] = {
    "product": {"label": "Products", "categories": P_CATS, "seeds": P_SEEDS, "stems": P_STEMS,
                "hints": ["product", "bought", "purchase", "ordered", "delivery", "delivered", "packag", "parcel", "amazon", "flipkart",
                          "seller", "refund", "return", "warranty", "bottle", "cream", "battery", "charger", "shipping", "courier"]},
    "restaurant": {
        "label": "Restaurants and food", "categories": ["food", "service", "ambience", "cleanliness", "price", "wait time", "portions"],
        "seeds": {
            "food": ["the food was delicious", "tasteless and bland dish", "fresh and flavourful", "the curry was too salty", "undercooked and cold food", "best biryani I have had"],
            "service": ["the waiter was friendly and attentive", "rude staff", "excellent service", "the server ignored our table", "staff was polite and helpful", "they got our order wrong"],
            "ambience": ["lovely cosy atmosphere", "too noisy to talk", "great decor and music", "the place felt gloomy", "nice view and seating", "crowded and uncomfortable"],
            "cleanliness": ["the restaurant was spotless", "dirty tables and washroom", "very hygienic kitchen", "found a hair in my food", "clean cutlery and plates", "flies everywhere"],
            "price": ["very reasonable prices", "overpriced for what you get", "good value for money", "the bill was too high", "affordable and tasty", "not worth the price"],
            "wait time": ["we waited an hour for food", "quick service, food came fast", "very slow kitchen", "no wait at all", "took forever to get the bill", "the order arrived promptly"],
            "portions": ["generous portions", "tiny portion for the price", "plenty of food", "the serving was too small", "huge helping, could share", "left hungry after the meal"],
        },
        "stems": {
            "food": ["food", "dish", "taste", "tasty", "delicious", "flavo", "bland", "salty", "spicy", "cooked", "fresh", "menu", "biryani", "pizza", "burger", "curry", "pasta", "dessert", "khana", "swad"],
            "service": ["service", "waiter", "waitress", "staff", "server", "rude", "polite", "manager", "attentive", "host"],
            "ambience": ["ambien", "atmospher", "decor", "music", "noisy", "seating", "view", "cosy", "cozy", "vibe", "crowded", "interior"],
            "cleanliness": ["clean", "dirty", "hygien", "hair in", "washroom", "toilet", "filthy", "spotless", "cockroach", "flies"],
            "price": ["price", "expens", "overpriced", "bill", "afford", "value", "costly", "worth", "paisa"],
            "wait time": ["wait", "slow", "quick", "long time", "forever", "prompt", "delay", "took an hour"],
            "portions": ["portion", "serving", "helping", "quantity", "small amount", "generous", "filling"],
        },
        "hints": ["restaurant", "food", "waiter", "menu", "dish", "ordered", "chef", "tasty", "delicious", "dinner", "lunch", "breakfast", "cafe", "biryani", "pizza", "buffet", "takeaway", "dine"]},
    "hotel": {
        "label": "Hotels and travel", "categories": ["room", "cleanliness", "staff", "location", "food", "amenities", "value"],
        "seeds": {
            "room": ["the room was spacious and comfortable", "tiny room with a broken AC", "comfortable bed and pillows", "the room smelled damp", "lovely room with a view", "noisy room, could not sleep"],
            "cleanliness": ["spotless room and bathroom", "dirty sheets and stained carpet", "very clean property", "found bugs in the room", "bathroom was not cleaned", "housekeeping did a great job"],
            "staff": ["friendly and helpful staff", "reception was rude", "the staff went out of their way", "check in took very long", "concierge was very helpful", "nobody answered our requests"],
            "location": ["perfect location near everything", "far from the city centre", "close to the beach and station", "hard to find, remote area", "great neighbourhood", "short walk to attractions"],
            "food": ["the breakfast buffet was great", "poor breakfast choices", "tasty food at the restaurant", "room service was cold", "good variety at breakfast", "the food was bland"],
            "amenities": ["the pool was lovely", "wifi did not work", "great gym and spa", "no hot water", "good parking and facilities", "the lift was broken"],
            "value": ["great value for the price", "overpriced for the quality", "worth every rupee", "hidden charges at checkout", "good deal for the stay", "too expensive for what it offers"],
        },
        "stems": {
            "room": ["room", "bed", "pillow", "mattress", "suite", r"ac\b", "air condition", "balcony", "view", "bathroom"],
            "cleanliness": ["clean", "dirty", "stain", "hygien", "housekeep", "bug", "smell", "dust", "spotless", "towel"],
            "staff": ["staff", "reception", "front desk", "concierge", "manager", "check in", "check-in", "helpful", "rude", "hospitalit"],
            "location": ["location", "near", "close to", "far from", "walk", "beach", "station", "airport", "neighbourhood", "central"],
            "food": ["breakfast", "buffet", "restaurant", "food", "dinner", "room service", "meal", "menu"],
            "amenities": ["pool", "wifi", "wi-fi", "gym", "spa", "parking", "lift", "elevator", "hot water", "amenit", "facilit"],
            "value": ["price", "value", "expens", "overpriced", "worth", "charge", "cost", "afford", "deal", "paisa"],
        },
        "hints": ["hotel", "room", "stay", "stayed", "check in", "checkout", "check-in", "reception", "resort", "booking", "night", "breakfast", "bed", "airbnb", "hostel", "suite"]},
    "movie": {
        "label": "Movies and shows", "categories": ["story", "acting", "direction", "visuals", "music", "pacing", "ending"],
        "seeds": {
            "story": ["a gripping and original story", "the plot made no sense", "predictable storyline", "wonderful script and dialogue", "weak screenplay full of holes", "a touching story"],
            "acting": ["brilliant performances by the cast", "wooden and unconvincing acting", "the lead actor was superb", "terrible overacting", "great chemistry between the actors", "the cast was miscast"],
            "direction": ["masterful direction", "the director lost control of the film", "tightly directed and well made", "poorly directed", "a visionary director", "the direction felt confused"],
            "visuals": ["stunning cinematography and visual effects", "the CGI looked fake", "beautiful shots and colours", "cheap looking special effects", "gorgeous visuals on the big screen", "poor editing and dark scenes"],
            "music": ["the soundtrack is wonderful", "forgettable background score", "great songs and music", "the music was too loud", "a haunting musical score", "the songs felt out of place"],
            "pacing": ["perfectly paced from start to end", "the film dragged in the second half", "slow and boring", "fast and thrilling", "too long and stretched", "kept me engaged throughout"],
            "ending": ["a satisfying ending", "the ending was disappointing", "great twist at the end", "the climax felt rushed", "an unforgettable finale", "the ending ruined the film"],
        },
        "stems": {
            "story": ["story", "plot", "script", "screenplay", "dialogue", "storyline", "writing", "narrative", "twist", "predictab"],
            "acting": ["act", "perform", "cast", "actor", "actress", "role", "chemistry", "portray", "lead"],
            "direction": ["direct", "filmmak", "film-mak", "vision"],
            "visuals": ["visual", "cinematograph", "graphic", "cgi", "effects", "shots", "scenes", "edit", "camera", "colour", "color"],
            "music": ["music", "song", "soundtrack", "score", "background score", "bgm", "sound"],
            "pacing": ["pace", "pacing", "slow", "boring", "drag", "fast", "gripping", "engaging", "too long", "runtime", "stretch"],
            "ending": ["ending", "climax", "finale", "twist", "conclusion", "last scene"],
        },
        "hints": ["movie", "film", "plot", "actor", "actress", "director", "scene", "cinema", "watched", "soundtrack", "sequel", "episode", "season", "cast", "screenplay", "climax"]},
    "app": {
        "label": "Apps and software", "categories": ["performance", "usability", "features", "reliability", "customer support", "price", "design"],
        "seeds": {
            "performance": ["fast and smooth", "very slow and laggy", "the app takes ages to load", "runs without any lag", "drains my battery", "quick and responsive"],
            "usability": ["easy to use and intuitive", "confusing menus", "hard to find anything", "simple clean interface to navigate", "the login is a pain", "very user friendly"],
            "features": ["packed with useful features", "missing basic features", "wish it had dark mode", "great tools and options", "the feature I need is gone", "does everything I need"],
            "reliability": ["keeps crashing", "never had a bug", "the app freezes constantly", "stable and dependable", "lost all my data after the update", "sync fails every time"],
            "customer support": ["support replied quickly and solved it", "no response from customer care", "helpful support team", "support was useless", "they ignored my emails", "fixed my issue the same day"],
            "price": ["worth the subscription", "too expensive for what it does", "fair pricing", "forced to pay for basic things", "good free version", "the subscription is a rip off"],
            "design": ["beautiful design", "ugly and cluttered layout", "clean modern look", "the new update looks terrible", "nice colours and icons", "hard to read tiny text"],
        },
        "stems": {
            "performance": ["fast", "slow", "lag", "load", "speed", "responsive", "battery", "smooth", "performan"],
            "usability": ["easy to use", "intuitive", "confus", "interface", "navigat", "user friendly", "user-friendly", "login", "sign in", "usab"],
            "features": ["feature", "option", "tool", "missing", "dark mode", "functional"],
            "reliability": ["crash", "bug", "freez", "stable", "glitch", "data loss", "lost my", "sync", "error", "reliab", "hang"],
            "customer support": ["support", "customer care", "customer service", "helpdesk", "replied", "response", "ticket"],
            "price": ["price", "subscription", "expens", "worth", "pay", "free version", "cost", "premium", "afford"],
            "design": ["design", "layout", "ui\\b", "look", "theme", "colour", "color", "icon", "clutter", "font"],
        },
        "hints": ["app", "update", "login", "crash", "download", "install", "subscription", "ui", "interface", "version", "software", "bug", "notification", "play store", "android", "ios", "account"]},
    "general": {
        "label": "General", "categories": ["quality", "price", "service", "speed", "cleanliness", "reliability", "experience"],
        "seeds": {
            "quality": ["excellent quality", "poor quality work", "very well done", "sloppy and careless", "top notch standard", "not up to the mark"],
            "price": ["very reasonable cost", "far too expensive", "good value", "overcharged us", "affordable and fair", "not worth the money"],
            "service": ["helpful and friendly service", "rude and unhelpful", "they took care of everything", "terrible customer service", "very professional team", "no one listened to us"],
            "speed": ["quick and efficient", "took far too long", "done on time", "delays and waiting", "very prompt", "slow response"],
            "cleanliness": ["very clean place", "dirty and untidy", "well maintained", "poorly maintained", "neat and tidy", "unhygienic conditions"],
            "reliability": ["always dependable", "unreliable and inconsistent", "never let us down", "failed when we needed it", "consistent every time", "cancelled at the last minute"],
            "experience": ["a wonderful experience", "a disappointing experience", "would recommend to everyone", "will never come back", "really enjoyed it", "a waste of time"],
        },
        "stems": {
            "quality": ["quality", "standard", "well done", "sloppy", "craft", "professional"],
            "price": ["price", "cost", "expens", "afford", "value", "worth", "charge", "fee", "overpriced"],
            "service": ["service", "staff", "team", "helpful", "rude", "friendly", "support", "polite"],
            "speed": ["quick", "slow", "fast", "wait", "prompt", "delay", "time", "efficient"],
            "cleanliness": ["clean", "dirty", "hygien", "tidy", "maintain", "filthy"],
            "reliability": ["reliab", "depend", "consisten", "cancel", "unreliable", "trust"],
            "experience": ["experience", "recommend", "enjoy", "disappoint", "waste", "love", "visit"],
        },
        "hints": []},
}

DEFAULT = "product"
FALLBACK = "general"
MIN_RATE = 0.08      # share of reviews that must match a profile's hint words before it is chosen
MARGIN = 1.3         # the best profile must beat the runner-up by this factor, otherwise the general profile is used

# Next-step rules for aspects that only exist in the newer profiles (action_rules.py merges these in).
EXTRA_RULES = {
    "food": ("Review the recipes, ingredients and kitchen consistency for the dishes customers criticise", "Kitchen and menu"),
    "service": ("Retrain front-line staff on the repeated complaints and set response-time targets", "Operations"),
    "ambience": ("Review noise, seating, lighting and music against what customers say", "Operations and design"),
    "cleanliness": ("Add a cleaning checklist with daily sign-off and spot checks", "Operations"),
    "wait time": ("Find the slowest step in the process and set a target time for it", "Operations"),
    "portions": ("Review portion sizes against the price and what the menu promises", "Kitchen and menu"),
    "room": ("Inspect and repair the rooms customers mention, starting with the ones named most often", "Property and maintenance"),
    "staff": ("Coach staff on the repeated complaints and recognise the people customers praise", "Guest services"),
    "location": ("Describe the location accurately on the listing, with distances and transport", "Marketing"),
    "amenities": ("Repair or fix the amenities customers report as broken or missing", "Property and maintenance"),
    "value": ("Compare pricing with competitors and make clear what is included", "Pricing and marketing"),
    "story": ("Share the story feedback with the writers and note which plot points confused viewers", "Content team"),
    "acting": ("Share the performance feedback with the casting and direction team", "Content team"),
    "direction": ("Review the direction feedback with the production team", "Content team"),
    "visuals": ("Review the visual effects and editing issues viewers point out", "Post production"),
    "music": ("Review the music and sound mix against the audience feedback", "Post production"),
    "pacing": ("Check the runtime and the slow sections viewers mention", "Editing"),
    "ending": ("Review the ending feedback with the writers before the next release", "Content team"),
    "performance": ("Profile the slow screens and fix the worst delays first", "Engineering"),
    "usability": ("Run a short usability test on the screens users find confusing", "Product and design"),
    "features": ("Add the most requested missing features to the roadmap", "Product"),
    "reliability": ("Fix the crashes and sync failures users report before adding anything new", "Engineering"),
    "customer support": ("Set response-time targets and retrain support on the repeated complaints", "Customer support"),
    "design": ("Review the layout and readability issues users mention", "Product and design"),
    "speed": ("Find the slowest step in the process and set a target time for it", "Operations"),
    "experience": ("Read the comments behind the low ratings and assign an owner", "Manager"),
}
EXTRA_REPLY_LINES = {
    "food": "We are sorry the food did not meet your expectations.",
    "service": "We are sorry about the service you received.",
    "ambience": "We are sorry the atmosphere was not what you hoped for.",
    "cleanliness": "We are sorry the place did not feel clean enough. We are taking this seriously.",
    "wait time": "We are sorry you had to wait so long.",
    "portions": "We hear you on portion size and are reviewing it.",
    "room": "We are sorry about your room.",
    "staff": "We are sorry about your experience with our team.",
    "location": "Thank you for telling us about the location.",
    "amenities": "We are sorry the facilities did not work as they should.",
    "value": "We hear you on value for money and are reviewing our pricing.",
    "performance": "We are sorry the app was slow for you.",
    "usability": "We are sorry it was hard to use. We are working on making it simpler.",
    "features": "Thank you for the feature feedback. It goes to our product team.",
    "reliability": "We are sorry about the crashes and problems you ran into.",
    "customer support": "We are sorry about the support you received.",
    "design": "Thank you for the design feedback.",
    "speed": "We are sorry it took longer than it should.",
    "experience": "We are sorry your experience did not meet your expectations.",
}


def categories_of(domain: str) -> list[str]:
    return PROFILES[domain]["categories"]


def all_categories() -> list[str]:
    seen: list[str] = []
    for p in PROFILES.values():
        seen += [c for c in p["categories"] if c not in seen]
    return seen


def detect_domain(texts: list[str], forced: str | None = None) -> str:
    """Picks the profile whose hint words appear in the most reviews. Unclear or mixed text gets the general profile."""
    if forced and forced != "auto" and forced in PROFILES:
        return forced
    sample = [t.lower() for t in texts[:500] if t]
    if len(sample) < 3:
        return DEFAULT if not sample else FALLBACK
    rates = {}
    for name, p in PROFILES.items():
        if not p["hints"]:
            continue
        rx = re.compile(r"(?<![a-z])(?:" + "|".join(re.escape(h) for h in p["hints"]) + ")")
        rates[name] = sum(1 for t in sample if rx.search(t)) / len(sample)
    ranked = sorted(rates.items(), key=lambda kv: -kv[1])
    best, rate = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if rate >= MIN_RATE and rate >= MARGIN * second:
        return best
    return FALLBACK
'@ | Set-Content -Encoding ascii backend\app\core\domains.py

@'
"""Offline checks for the multi-domain aspect profiles. Run: python -m tests.check_domains"""
import numpy as np

from app.core import domains as D
from app.core.action_rules import RULES
from app.services import replies, sentence_aspects as SA

# every profile is complete and every aspect has an action rule
for name, p in D.PROFILES.items():
    assert set(p["seeds"]) == set(p["categories"]) == set(p["stems"]), name
    assert all(len(v) == 6 for v in p["seeds"].values()), name
missing = [c for c in D.all_categories() if c not in RULES]
assert not missing, missing
assert D.categories_of("product") == D.PROFILES["product"]["categories"]

# detection picks the right kind of review
R = ["The food was delicious and the waiter was friendly", "Great biryani, tasty dish, quick service", "Nice menu and good dinner",
     "Loved the restaurant ambience", "The chef made a lovely dessert", "Lunch was ok", "Average pizza"]
H = ["The room was clean and the reception staff were helpful", "Great hotel, we stayed three nights", "Breakfast buffet was good",
     "Check in was quick, the bed was comfortable", "Loved the resort pool", "Booking was easy"]
M = ["The plot was gripping and the actor was brilliant", "Great film, the climax was amazing", "The director did a fine job",
     "Loved the soundtrack and the cast", "Slow second half of the movie", "The sequel is better"]
A = ["The app keeps crashing after the update", "Login does not work on Android", "Great software but the subscription is costly",
     "The new version has a bug", "Notifications stopped after I installed it", "Nice interface"]
P = ["Bought this cream, the packaging was damaged", "Delivery was late, the parcel was crushed", "Good product, fast shipping",
     "Ordered twice, seller sent a refund", "Battery charger works well", "The bottle leaked in transit"]
assert D.detect_domain(R) == "restaurant" and D.detect_domain(H) == "hotel" and D.detect_domain(M) == "movie"
assert D.detect_domain(A) == "app" and D.detect_domain(P) == "product"
assert D.detect_domain(["ok", "fine", "good", "nice", "bad", "meh", "so so"]) == "general"
assert D.detect_domain(["x"]) == "general" and D.detect_domain([]) == "product"
assert D.detect_domain(R, forced="movie") == "movie" and D.detect_domain(R, forced="auto") == "restaurant"
assert D.detect_domain(R, forced="nonsense") == "restaurant"
assert D.detect_domain(R + M) in ("general", "restaurant", "movie")      # a mixed pile never crashes

# keyword tagging per profile (low similarity forces the keyword path)
def tag(domain, sentence):
    low = {a: 0.05 for a in D.categories_of(domain)}
    return [a for a, _m, _s in SA.tag(low, sentence, domain)]

assert "food" in tag("restaurant", "The biryani was bland and too salty")
assert "wait time" in tag("restaurant", "We had to wait an hour")
assert "service" in tag("restaurant", "The waiter was rude")
assert "story" in tag("movie", "The plot made no sense") and "ending" in tag("movie", "The climax was weak")
assert "acting" in tag("movie", "Brilliant performances by the cast")
assert "reliability" in tag("app", "It keeps crashing after the update")
assert "customer support" in tag("app", "Customer care never replied")
assert "room" in tag("hotel", "The room was tiny and the bed was hard")
assert "location" in tag("hotel", "Close to the beach and station")
assert tag("restaurant", "I bought it last week") == ["general"]
assert tag("product", "Delivery was slow") == ["delivery"]              # old behaviour is unchanged

# term, centroids and review rows follow the domain
assert SA.term_of("The waiter was rude", "service", "restaurant") == "waiter"
assert SA.term_of("The waiter was rude", "service") == "service"          # product profile has no such stem
fake = lambda texts: np.array([[float(len(t) % 5 + i + 1) for i in range(4)] for t in texts])
c = SA.centroids(fake, "movie")
assert set(c) == set(D.categories_of("movie")) and abs(np.linalg.norm(c["story"]) - 1) < 1e-9
ids = {a: i for i, a in enumerate(D.categories_of("restaurant"), 1)}
rows = SA.review_rows(1, [{"sentence": "The waiter was rude", "aspect": "service", "method": "keyword", "sent_score": -0.8,
                           "conf": 0.9, "domain": "restaurant"}], ids)
assert rows[0]["term"] == "waiter" and rows[0]["aspect_id"] == ids["service"]

# replies and actions cover the new aspects
assert "wait" in replies.draft_reply([], "wait time").lower()
assert "slow" in replies.draft_reply([], "performance").lower()
print("domain checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_domains.py

@'
import pathlib

B = pathlib.Path("backend/app")


def edit(rel, pairs, marker):
    p = B / rel
    t = p.read_text(encoding="utf-8")
    if marker in t:
        return
    for a, b in pairs:
        assert a in t, f"{rel}: text not found: {a[:60]!r}"
        t = t.replace(a, b, 1)
    p.write_text(t, encoding="utf-8")


# 1. sentence aspects take a domain (default stays the product profile, so old calls behave the same)
edit("services/sentence_aspects.py", [
    ("from app.core.aspect_config import CATEGORIES, SEEDS, STEMS\n",
     "from app.core import domains as D\nfrom app.core.aspect_config import CATEGORIES, SEEDS, STEMS\n"),
    ("def keyword_hits(sentence: str) -> list[str]:\n    return [a for a in CATEGORIES if _STEM_RX[a].search(sentence)]\n",
     "_RX_CACHE: dict = {}\n\n\ndef _rx_for(domain: str) -> dict:\n"
     "    if domain not in _RX_CACHE:\n"
     "        st = D.PROFILES[domain][\"stems\"]\n"
     "        _RX_CACHE[domain] = {a: re.compile(r\"\\b(?:\" + \"|\".join(st[a]) + \")\", re.I) for a in D.categories_of(domain)}\n"
     "    return _RX_CACHE[domain]\n\n\n"
     "def keyword_hits(sentence: str, domain: str = \"product\") -> list[str]:\n"
     "    return [a for a, rx in _rx_for(domain).items() if rx.search(sentence)]\n"),
    ("def term_of(sentence: str, aspect: str) -> str:\n    m = _STEM_RX[aspect].search(sentence)\n",
     "def term_of(sentence: str, aspect: str, domain: str = \"product\") -> str:\n    rx = _rx_for(domain).get(aspect)\n    m = rx.search(sentence) if rx else None\n"),
    ("def tag(sims: dict[str, float], sentence: str) -> list[tuple[str, str, float]]:",
     "def tag(sims: dict[str, float], sentence: str, domain: str = \"product\") -> list[tuple[str, str, float]]:"),
    ("    kw = keyword_hits(sentence)\n", "    kw = keyword_hits(sentence, domain)\n"),
    ("def centroids(embed_fn) -> dict:", "def centroids(embed_fn, domain: str = \"product\") -> dict:"),
    ("    for a in CATEGORIES:\n        v = np.asarray(embed_fn(SEEDS[a]), dtype=float).mean(axis=0)",
     "    seeds = D.PROFILES[domain][\"seeds\"]\n    for a in D.categories_of(domain):\n        v = np.asarray(embed_fn(seeds[a]), dtype=float).mean(axis=0)"),
    ('"term": term_of(s["sentence"], s["aspect"]),', '"term": term_of(s["sentence"], s["aspect"], s.get("domain", "product")),'),
], "_rx_for")

# 2. the worker detects the domain per product and uses that profile
edit("worker/aspects_sbert.py", [
    ("from app.core import thresholds as T\n", "from app.core import domains as D, thresholds as T\nfrom app.core.config import settings\n"),
    ("def _cents_for(model: str) -> dict:\n    if model not in _cents:\n        _cents[model] = SA.centroids(lambda t: embeddings.embed(t, model))\n    return _cents[model]\n",
     "def _cents_for(model: str, domain: str = \"product\") -> dict:\n    if (model, domain) not in _cents:\n        _cents[(model, domain)] = SA.centroids(lambda t: embeddings.embed(t, model), domain)\n    return _cents[(model, domain)]\n"),
    ('    """part = [(review_id, text, language)]. Returns',
     '    """part = [(review_id, text, language, domain)]. Returns'),
    ("    for rid, text, lang in part:", "    for rid, text, lang, dom in part:"),
    ('items.append({"review_id": rid, "idx": idx, "sentence": s, "lang": lang,',
     'items.append({"review_id": rid, "idx": idx, "sentence": s, "lang": lang, "domain": dom,'),
    ("""    for english in (True, False):
        grp = [i for i in items if i["english"] == english]
        if not grp:
            continue
        model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
        vecs = embeddings.embed([i["sentence"] for i in grp], model)
        sims = SA.similarities(vecs, _cents_for(model))
        tagged = []
        for i, sm in zip(grp, sims):
            for aspect, method, sim in SA.tag(sm, i["sentence"]):""",
     """    for english, dom in sorted({(i["english"], i["domain"]) for i in items}):
        grp = [i for i in items if i["english"] == english and i["domain"] == dom]
        model = T.SBERT_EN_MODEL if english else T.EMBED_MODEL
        vecs = embeddings.embed([i["sentence"] for i in grp], model)
        sims = SA.similarities(vecs, _cents_for(model, dom))
        tagged = []
        for i, sm in zip(grp, sims):
            for aspect, method, sim in SA.tag(sm, i["sentence"], dom):"""),
    ("        ids = await _aspect_ids(s, ws)\n        pending = (await s.execute(sql(\"\"\"\n            SELECT r.review_id, r.text_clean, r.language FROM review r",
     "        pending = (await s.execute(sql(\"\"\"\n            SELECT r.review_id, r.text_clean, r.language, r.product_id FROM review r"),
    ("    total = len(pending)\n",
     "    by_prod: dict = {}\n    for p in pending:\n        by_prod.setdefault(p[3], []).append(p[1])\n"
     "    dom_of = {pid: D.detect_domain(txts, settings.aspect_domain) for pid, txts in by_prod.items()}\n"
     "    names = sorted({c for d in set(dom_of.values()) for c in D.categories_of(d)})\n"
     "    print(f\"[aspects] review types detected: {sorted(set(dom_of.values())) or 'none'}\")\n"
     "    async with SessionLocal() as s:\n        ids = await _aspect_ids(s, ws, names)\n    total = len(pending)\n"),
    ("[tuple(p) for p in part]", "[(p[0], p[1], p[2], dom_of[p[3]]) for p in part]"),
], "detect_domain")

edit("worker/handlers.py", [
    ("""async def _aspect_ids(s, workspace_id: int) -> dict[str, int]:
    await s.execute(
        pg_insert(Aspect)
        .values([{"workspace_id": workspace_id, "name": n} for n in CATEGORIES])
        .on_conflict_do_nothing(index_elements=["workspace_id", "name"])
    )
    await s.commit()
""", """async def _aspect_ids(s, workspace_id: int, names: list[str] | None = None) -> dict[str, int]:
    names = list(CATEGORIES) if names is None else names
    if names:
        await s.execute(
            pg_insert(Aspect)
            .values([{"workspace_id": workspace_id, "name": n} for n in names])
            .on_conflict_do_nothing(index_elements=["workspace_id", "name"])
        )
        await s.commit()
"""),
], "names: list[str] | None")

edit("core/config.py", [("    app_name: str = \"ReviewIQ\"\n", "    app_name: str = \"ReviewIQ\"\n    aspect_domain: str = \"auto\"   # auto, product, restaurant, hotel, movie, app or general\n")], "aspect_domain")

edit("core/action_rules.py", [
    ("Compare price and pack size with competitors and make the value clearer on the listing", "Compare pricing with competitors and make the value clearer to customers"),
    ("def rule_for(aspect: str) -> tuple[str, str]:\n    return RULES.get(aspect, DEFAULT)\n",
     "from app.core.domains import EXTRA_RULES  # noqa: E402\n\nfor _k, _v in EXTRA_RULES.items():\n    RULES.setdefault(_k, _v)\n\n\ndef rule_for(aspect: str) -> tuple[str, str]:\n    return RULES.get(aspect, DEFAULT)\n"),
], "EXTRA_RULES")

edit("services/replies.py", [
    ('GENERIC = "We are sorry your experience did not meet your expectations."\n',
     'GENERIC = "We are sorry your experience did not meet your expectations."\nfrom app.core.domains import EXTRA_REPLY_LINES  # noqa: E402\n\nfor _k, _v in EXTRA_REPLY_LINES.items():\n    ASPECT_LINES.setdefault(_k, _v)\n'),
], "EXTRA_REPLY_LINES")

edit("services/listing.py", [("from app.core.aspect_config import CATEGORIES\n", "from app.core.domains import all_categories\n\nCATEGORIES = all_categories()\n")], "all_categories")

# settings hint for .env.example
env = pathlib.Path(".env.example")
if env.exists() and "ASPECT_DOMAIN" not in env.read_text(encoding="utf-8"):
    with env.open("a", encoding="utf-8") as f:
        f.write("\n# Aspect profile: auto detects restaurants, hotels, movies, apps and products per product. Or force one.\nASPECT_DOMAIN=auto\n")
print("step 31 patched")

# 3. upload page: drop the "Bring in my data" heading
up = pathlib.Path("frontend/src/Upload.tsx")
if up.exists():
    t = up.read_text(encoding="utf-8")
    line = '        <h1 className="text-2xl font-bold">Bring in my data</h1>\n'
    if line in t:
        up.write_text(t.replace(line, "", 1), encoding="utf-8")
'@ | Set-Content -Encoding ascii patch_step31.py
python patch_step31.py
Remove-Item patch_step31.py

Write-Host 'Step 31 files written.'
