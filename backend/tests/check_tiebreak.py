from app.services.detection import RoleResult
from app.services.profiling import profile_column
from app.services.tiebreak import candidates, decide

PROFILES = {
    "a": profile_column("a", ["0", "0", "3", "0", "1", "0", "0", "2"]),  # vote-like
    "b": profile_column("b", ["5", "1", "4", "2", "5", "1", "3", "4"]),  # rating-like
}


def rr(role, col=None, conf=0.0, hs=0.0, alts=()):
    return RoleResult(role, col, conf, "header+values" if col else "none",
                      {"header_score": hs} if col else {},
                      [{"column": a, "confidence": 0.7} for a in alts], "accept" if col else "none")


def mk(rating=None, helpful=None):
    return [rr("text", "t", 0.9, 1.0), rr("rating", *(rating or ())), rr("helpful", *(helpful or ()))]


def by(res):
    return {r.role: r for r in res}


# 1. columns picked the wrong way round: swap, and ask the user
r = by(res := mk(("a", 0.72, 0.0), ("b", 0.56, 0.0)))
decide(res, {"a": 0.02, "b": 0.8}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "ask", r["rating"]
assert r["helpful"].column == "a", r["helpful"]

# 2. rating tracks sentiment: accepted
r = by(res := mk(("b", 0.72, 0.0), ("a", 0.56, 0.0)))
decide(res, {"b": 0.7, "a": 0.0}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "accept" and r["rating"].confidence >= 0.85

# 3. flat "rating" that looks like votes becomes helpful, rating is empty
r = by(res := mk(("a", 0.72, 0.0)))
decide(res, {"a": 0.02}, PROFILES)
assert r["rating"].column is None and r["helpful"].column == "a"

# 3b. flat but not vote-like: stays, but the user is asked
r = by(res := mk(("b", 0.72, 0.0)))
decide(res, {"b": 0.02}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "ask" and r["rating"].confidence <= 0.45

# 3c. flat rating with a better alternative: the alternative wins
r = by(res := mk(("a", 0.72, 0.0, ["b"])))
decide(res, {"a": 0.02, "b": 0.8}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "ask" and r["helpful"].column == "a"

# 4. middle correlation: no change
r = by(res := mk(("b", 0.72, 0.0)))
decide(res, {"b": 0.2}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "accept" and r["rating"].confidence == 0.72

# 5. a strong header is never tested
assert candidates(mk(("b", 0.95, 1.0), ("a", 0.6, 0.0))) == ["a"]
assert candidates(mk(("b", 0.95, 1.0))) == []
# 6. middle correlation but a clearly better alternative: swap and ask
r = by(res := mk(("a", 0.72, 0.0, ["b"])))
decide(res, {"a": 0.2, "b": 0.8}, PROFILES)
assert r["rating"].column == "b" and r["rating"].action == "ask" and r["helpful"].column == "a", r
print("tiebreak checks passed")
