"""Offline checks for the multi-domain aspect profiles. Run: python -m tests.check_domains"""
import numpy as np

from app.core import domains as D
from app.core.action_rules import RULES
from app.services import replies, sentence_aspects as SA

# every profile is complete and every aspect has an action rule
for name, p in D.PROFILES.items():
    assert set(p["seeds"]) == set(p["categories"]) == set(p["stems"]), name
    assert all(len(v) >= 6 for v in p["seeds"].values()), name
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
