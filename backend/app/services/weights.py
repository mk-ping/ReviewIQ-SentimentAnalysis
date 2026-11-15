
"""Ensemble weights recomputed from hand-labelled gold reviews (final pipeline document, section 5).
Pure functions. Weight = macro F1 of the model on the gold reviews of that route group, floored above zero."""
from app.services import evaluation as E
from app.services.routing import MEMBERS

MIN_GOLD_TOTAL = 200   # below this the stored validation weights stay in force
WEIGHT_FLOOR = 0.01    # model_weight.weight must be > 0


def model_weights(gold: dict[int, str], group_of_review: dict[int, str],
                  preds: dict[str, dict[int, tuple]]) -> dict[str, dict]:
    """Returns {group: {'n': gold reviews in the group, 'weights': {model key: weight}}} for groups with any gold review."""
    out: dict[str, dict] = {}
    for g, members in MEMBERS.items():
        ids = [i for i, grp in group_of_review.items() if grp == g and i in gold]
        if not ids:
            continue
        ws = {}
        for k in members:
            have = [i for i in ids if i in preds.get(k, {})]
            f1 = E.macro_f1([gold[i] for i in have], [E.argmax_label(*preds[k][i][:3]) for i in have]) if have else None
            if f1 is not None:
                ws[k] = round(max(f1, WEIGHT_FLOOR), 4)
        if ws:
            out[g] = {"n": len(ids), "weights": ws}
    return out
