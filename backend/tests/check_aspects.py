import asyncio

import httpx

from app.core.config import settings
from app.services import aspects

TEXT = "Great scent, but the pump broke after a week."
ITEMS = [
    {"term": "scent", "category": "scent", "sentiment": 1, "evidence": "Great scent"},
    {"term": "pump", "category": "packaging", "sentiment": -1, "evidence": "the pump broke after a week."},
    {"term": "x", "category": "packaging", "sentiment": -1, "evidence": "never said this"},   # invented quote
    {"term": "y", "category": "nonsense", "sentiment": -1, "evidence": "Great scent"},        # unknown category
    {"term": "z", "category": "price", "sentiment": 5, "evidence": "Great scent"},            # sentiment out of range
]
ok, bad = aspects.validate(ITEMS, TEXT)
assert len(ok) == 2 and bad == 3, (ok, bad)
assert aspects.validate("not a list", TEXT) == ([], 1)
print("validation checks passed:", [(o["category"], o["term"]) for o in ok])


async def live():
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as c:
        if not await aspects.llm_available(c):
            print(f"LLM '{settings.llm_model}' not reachable at {settings.llm_url}: skipping the live test")
            return
        for t in [TEXT, "Delivery was late and the box was damaged.", "Bahut accha product hai but price thoda zyada hai", "ok"]:
            items, method = await aspects.extract(c, t)
            print(method, "|", t)
            for i in items:
                print("   ", i["category"], "|", i["term"], "|", i["sentiment"], "|", i["evidence_span"])

    print("keyword fallback on the first review:")
    for i in aspects.keyword_aspects(TEXT):
        print("   ", i["category"], "|", i["term"], "|", i["sentiment"], "|", i["evidence_span"])


asyncio.run(live())
print("aspect checks passed")
