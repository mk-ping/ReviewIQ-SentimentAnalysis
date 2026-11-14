from app.services.listing import validate_claims, verdict

TEXT = "Long-lasting fragrance. Easy to use pump. Hypoallergenic formula!"
ok = validate_claims([
    {"claim": "fragrance lasts", "aspect": "scent", "quote": "Long-lasting fragrance"},
    {"claim": "invented", "aspect": "scent", "quote": "Clinically proven"},      # quote not in listing
    {"claim": "easy pump", "aspect": "nonsense", "quote": "easy to use pump"},   # unknown aspect becomes None
    {"claim": "fragrance lasts", "aspect": "scent", "quote": "Long-lasting fragrance"},  # duplicate
], TEXT)
assert [c["claim"] for c in ok] == ["fragrance lasts", "easy pump"], ok
assert ok[1]["aspect"] is None
assert validate_claims("not a list", TEXT) == []

assert verdict(2, 1) == "not_enough_evidence"
assert verdict(6, 1) == "confirmed"
assert verdict(1, 6) == "contradicted"
assert verdict(3, 3) == "mixed"
print("listing checks passed")
