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
