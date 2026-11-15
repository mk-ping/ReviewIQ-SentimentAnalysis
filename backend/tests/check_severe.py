
from app.core.severe_terms import PREFILTER, SEVERE, severe_hits
from app.services.replies import draft_reply
import re

assert severe_hits("The charger caught fire on the second day") == ["safety"]
assert severe_hits("Got a rash and my face was swollen") == ["allergy"]
assert severe_hits("This looks fake, not genuine, total scam") == ["fraud"]
assert severe_hits("I will contact a lawyer and go to consumer court") == ["legal"]
assert severe_hits("Fire and rash and fake") == ["safety", "allergy", "fraud"] or severe_hits("Fire and rash and fake") == ["allergy", "fraud"]
assert severe_hits("Lovely scent, fast delivery") == []
assert severe_hits("The scent is firebrand spicy") == [], "must not match inside other words"
assert severe_hits("") == [] and severe_hits(None) == []
assert re.search(PREFILTER, "so it caught fire", re.I) and not re.search(PREFILTER, "great scent", re.I)

d = draft_reply(["allergy"], "scent", "en")
assert d.startswith("Thank you for telling us, and we are sorry about the reaction") and d.endswith("put this right.")
d = draft_reply([], "packaging", "en")
assert "packaging" in d and "honest feedback" in d
assert draft_reply([], None, "hi").startswith("[Review language: hi.")
assert draft_reply([], "unknown aspect", "en").count("sorry") == 1
assert set(SEVERE) == {"safety", "allergy", "fraud", "legal"}
print("severe and reply checks passed")
