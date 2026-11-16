"""Offline check for the ownership guard with a fake session. Run: python -m tests.check_ownership"""
import asyncio
import sys
import types

sys.modules.setdefault("sqlalchemy", types.SimpleNamespace(text=lambda s: s))
from app.core.ownership import OWNER_SQL, belongs_elsewhere  # noqa: E402


class Fake:
    def __init__(self, owners): self.owners = owners
    async def scalar(self, sql, params):
        table = "batch" if "upload_batch WHERE" in sql else "job" if "scoring_job" in sql else "review" if "FROM review" in sql else "other"
        return self.owners.get((table, params["i"]))


def run(owners, params, ws=1): return asyncio.run(belongs_elsewhere(Fake(owners), params, ws))

assert run({("batch", 5): 2}, {"batch_id": "5"}) is True          # someone else's upload
assert run({("batch", 5): 1}, {"batch_id": "5"}) is False         # my own upload
assert run({}, {"batch_id": "999"}) is False                      # does not exist: the endpoint answers 404
assert run({("job", 7): 2}, {"job_id": "7"}) is True              # a job is owned through its upload
assert run({("review", 3): 2}, {"review_id": "3"}) is True
assert run({}, {"batch_id": "abc"}) is False                      # not a number: FastAPI answers 422
assert run({}, {}) is False
assert set(OWNER_SQL) == {"batch_id", "product_id", "review_id", "action_id", "job_id"}
print("ownership checks passed")
