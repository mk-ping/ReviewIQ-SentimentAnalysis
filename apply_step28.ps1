# Step 28: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Stops one account from opening another account's records by changing the id in the address."""

OWNER_SQL = {
    "batch_id": "SELECT workspace_id FROM upload_batch WHERE batch_id = :i",
    "product_id": "SELECT workspace_id FROM product WHERE product_id = :i",
    "review_id": "SELECT workspace_id FROM review WHERE review_id = :i",
    "action_id": "SELECT workspace_id FROM action WHERE action_id = :i",
    "job_id": "SELECT b.workspace_id FROM scoring_job j JOIN upload_batch b ON b.batch_id = j.batch_id WHERE j.job_id = :i",
}


async def belongs_elsewhere(session, path_params: dict, workspace_id: int) -> bool:
    """True when an id in the path names a record that exists but belongs to a different workspace.
    A record that does not exist is left to the endpoint, which answers 404 itself."""
    from sqlalchemy import text
    for key, sql in OWNER_SQL.items():
        raw = path_params.get(key)
        if raw is None:
            continue
        try:
            i = int(raw)
        except (TypeError, ValueError):
            continue
        owner = await session.scalar(text(sql), {"i": i})
        if owner is not None and owner != workspace_id:
            return True
    return False
'@ | Set-Content -Encoding ascii backend\app\core\ownership.py

@'
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
'@ | Set-Content -Encoding ascii backend\tests\check_ownership.py

@'
"""Retrain the TF-IDF baseline on one workspace's own rated reviews (document rule: from 2000 rated reviews).
Held-out validation and test reviews (the split column) are never used for training.
Run from backend:  python -m scripts.retrain_own [--workspace 3] [--min-rated 2000]
It saves ../ml/out/tfidf_lr_ws<N>.joblib and prints how to use it. It never replaces the shared baseline by itself."""
import argparse
import asyncio
from collections import Counter
from pathlib import Path

MIN_RATED = 2000


def label3(star: float) -> str:
    s = round(star)
    return "neg" if s <= 2 else "neu" if s == 3 else "pos"


def check_ready(n_rated: int, labels: Counter, min_rated: int = MIN_RATED) -> str | None:
    """None when training can go ahead, otherwise the plain reason it cannot."""
    if n_rated < min_rated:
        return f"Only {n_rated} rated reviews are available for training; the rule needs {min_rated}. Upload {min_rated - n_rated} more."
    thin = [k for k in ("neg", "neu", "pos") if labels.get(k, 0) < 50]
    if thin:
        return "Too few reviews in class(es): " + ", ".join(thin) + " (need at least 50 each)."
    return None


def make_pipe():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000, token_pattern=r"[^\s.,!?;:()\[\]\"]+"),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )


def train(texts, labels):
    """Fits on 90%, reports on the other 10%, then refits on everything. Returns (pipeline, macro_f1, accuracy)."""
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split
    xa, xb, ya, yb = train_test_split(texts, labels, test_size=0.1, random_state=7, stratify=labels)
    check = make_pipe().fit(xa, ya)
    pred = check.predict(xb)
    return make_pipe().fit(texts, labels), f1_score(yb, pred, average="macro"), accuracy_score(yb, pred)


async def load(ws: int | None):
    from sqlalchemy import text
    from app.core import thresholds as T
    from app.db.session import SessionLocal
    async with SessionLocal() as s:
        if ws is None:
            ws = (await s.execute(text("SELECT min(workspace_id) FROM workspace"))).scalar()
        rows = (await s.execute(text(
            "SELECT text_clean, rating_norm FROM review WHERE workspace_id = :ws AND spam_score <= :spam "
            "AND rating_norm IS NOT NULL AND split IS NULL AND length(text_clean) > 0"), {"ws": ws, "spam": T.SPAM_MAX})).all()
    return ws, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=int, default=None)
    ap.add_argument("--min-rated", type=int, default=MIN_RATED)
    a = ap.parse_args()
    ws, rows = asyncio.run(load(a.workspace))
    texts = [t for t, _ in rows]
    labels = [label3(float(r)) for _, r in rows]
    why = check_ready(len(rows), Counter(labels), a.min_rated)
    if why:
        print(why)
        return 1
    import joblib
    pipe, f1, acc = train(texts, labels)
    print(f"Workspace {ws}: trained on {len(rows)} rated reviews. Check on 10%: macro F1 {f1:.3f}, accuracy {acc:.3f}")
    print("(a sanity check on star-derived labels, not a reported score: your gold labels decide that)")
    from app.core.config import settings
    out = Path(settings.tfidf_path).with_name(f"tfidf_lr_ws{ws}.joblib")
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out)
    print("saved", out)
    print("To use it, set TFIDF_PATH to that file in backend/.env, restart the API and worker, then run the held-out evaluation again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'@ | Set-Content -Encoding ascii backend\scripts\retrain_own.py

@'
"""Offline checks for the own-data retraining gate and training. Run: python -m tests.check_retrain_own"""
import random
from collections import Counter

from scripts.retrain_own import check_ready, label3, train

assert label3(1) == "neg" and label3(3) == "neu" and label3(4.6) == "pos"
assert "needs 2000" in check_ready(1500, Counter(neg=500, neu=500, pos=500))
assert "neu" in check_ready(2100, Counter(neg=1000, neu=10, pos=1090))
assert check_ready(2100, Counter(neg=700, neu=700, pos=700)) is None
assert check_ready(300, Counter(neg=100, neu=100, pos=100), min_rated=300) is None

rnd = random.Random(1)
words = {"neg": ["awful", "broken", "refund", "waste"], "neu": ["okay", "average", "fine", "decent"], "pos": ["great", "love", "perfect", "excellent"]}
texts, labels = [], []
for _ in range(600):
    y = rnd.choice(["neg", "neu", "pos"])
    texts.append(" ".join(rnd.choices(words[y], k=4) + ["the", "product"])); labels.append(y)
pipe, f1, acc = train(texts, labels)
assert f1 > 0.9 and acc > 0.9
assert list(pipe.predict(["great love perfect"])) == ["pos"]
print("retrain_own checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_retrain_own.py

@'
"""Step 28 patcher. Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s)
    assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2)
    print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

def auth(s):
    s = once(s, "from app.core.tenant import set_workspace\n", "from app.core.ownership import belongs_elsewhere\nfrom app.core.tenant import set_workspace\n")
    return once(s, '''async def require_user(user: AppUser | None = Depends(current_user)) -> AppUser | None:
    if settings.auth_required and user is None:
        raise HTTPException(401, "Please log in.")
''', '''async def require_user(request: Request, user: AppUser | None = Depends(current_user),
                       session: AsyncSession = Depends(get_session)) -> AppUser | None:
    if settings.auth_required and user is None:
        raise HTTPException(401, "Please log in.")
    if user is not None and await belongs_elsewhere(session, request.path_params, user.workspace_id):
        raise HTTPException(404, "Not found.")   # same answer as a missing record, so ids cannot be probed
''')
edit("backend/app/api/auth.py", "belongs_elsewhere", auth)
'@ | Set-Content -Encoding ascii patch_step28.py
python patch_step28.py
Remove-Item patch_step28.py

Write-Host 'Step 28 files written.'
