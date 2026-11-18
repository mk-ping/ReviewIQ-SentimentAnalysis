"""Mixed-genre stacker: learns from reviews, tweets, movie sentences and finance headlines together, with text clues
(length, hashtags, social flag) so each model can be trusted differently per kind of text. Pure functions, no downloads.
Used by scripts/train_mixed.py. The result is applied only when it beats today's weighted average and does not hurt reviews."""
from datetime import datetime, timezone

from app.services import metrics as M
from app.services import stacker as S
from app.services.ablation import paired_bootstrap_diff

REVIEW_SOURCE = "reviews"
MAX_REVIEW_DROP = 0.01   # the new stacker may not lose more than this macro F1 on star-derived reviews


def label_of(p) -> str:
    return M.LABELS[max(range(3), key=lambda c: p[c])]


def per_source(gold, pred, sources) -> dict:
    out = {}
    for s in sorted(set(sources)):
        idx = [i for i, x in enumerate(sources) if x == s]
        g, p = [gold[i] for i in idx], [pred[i] for i in idx]
        out[s] = {"n": len(idx), "accuracy": M.f_acc(g, p), "macro_f1": M.f_macro(g, p)}
    return out


def _oof(members, probs, texts, gold, meta, cfg, seed):
    X = [S.features(members, {k: probs[k][i] for k in members}, texts[i], meta) for i in range(len(gold))]
    return X, S.cv_labels(X, gold, members, 5, seed, *cfg)


def fit_mixed(members: list[str], probs: dict, texts: list[str], gold: list[str], sources: list[str], weights: dict) -> dict:
    """probs[member] = list of (p_neg, p_neu, p_pos) per row. Returns the stacker (with the evidence) plus per-source tables."""
    n = len(gold)
    if n < 60 or len(set(gold)) < 3:
        return {"model": None, "applied": False, "reason": "needs 60+ rows with all three classes"}
    base = [label_of(S.weighted_average(members, {k: probs[k][i] for k in members}, weights)) for i in range(n)]
    # choose settings on one set of folds, judge on different folds
    best = max(S.GRID, key=lambda cfg: M.f_macro(gold, _oof(members, probs, texts, gold, True, cfg, 7)[1]))
    X, oof = _oof(members, probs, texts, gold, True, best, 11)
    _, oof_plain = _oof(members, probs, texts, gold, False, best, 11)
    d = paired_bootstrap_diff(dict(enumerate(gold)), dict(enumerate(oof)), dict(enumerate(base)))
    ps_base, ps_new, ps_plain = per_source(gold, base, sources), per_source(gold, oof, sources), per_source(gold, oof_plain, sources)
    table = {s: {"weighted_average": ps_base[s], "stacker": ps_new[s], "stacker_without_text_clues": ps_plain[s]} for s in ps_base}
    rv = ps_new.get(REVIEW_SOURCE), ps_base.get(REVIEW_SOURCE)
    hurts_reviews = bool(rv[0] and rv[1] and rv[0]["macro_f1"] < rv[1]["macro_f1"] - MAX_REVIEW_DROP)
    ok_gain = bool(d) and n >= S.MIN_ROWS and d["lo"] > 0 and d["diff"] >= S.MIN_GAIN
    applied = ok_gain and not hurts_reviews
    reason = ("beats the weighted average across genres without hurting reviews" if applied else
              "it lowers macro F1 on reviews, so it is not used" if ok_gain and hurts_reviews else
              f"only {n} rows (need {S.MIN_ROWS})" if n < S.MIN_ROWS else
              f"no clear gain ({d['diff']:+.3f}, interval {d['lo']:+.3f} to {d['hi']:+.3f})" if d else "could not compare")
    model = S.fit(X, gold, members, *best, meta=True)
    model.update({"applied": applied, "reason": reason, "n_val": n, "cv_macro_f1_stacker": d["f1_a"] if d else None,
                  "cv_macro_f1_weighted_average": d["f1_b"] if d else None, "cv_diff": d["diff"] if d else None,
                  "cv_interval": [d["lo"], d["hi"]] if d else None, "sources": sorted(set(sources)), "trained_on": "mixed genres",
                  "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"model": model, "applied": applied, "reason": reason, "per_source": table, "overall": {
        "weighted_average": M.report(gold, base), "stacker": M.report(gold, oof), "paired": d}}


def md_table(res: dict) -> list[str]:
    L = ["| Source | Rows | Weighted avg acc | Stacker acc | Weighted avg F1 | Stacker F1 | Stacker without text clues F1 |", "|---|---|---|---|---|---|---|"]
    for s, t in res["per_source"].items():
        a, b, c = t["weighted_average"], t["stacker"], t["stacker_without_text_clues"]
        L.append(f"| {s} | {a['n']} | {a['accuracy']:.3f} | {b['accuracy']:.3f} | {a['macro_f1']:.3f} | {b['macro_f1']:.3f} | {c['macro_f1']:.3f} |")
    return L
