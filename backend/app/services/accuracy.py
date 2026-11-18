"""Accuracy experiment helpers (final pipeline document sections 5 and 14). Pure functions: no database, no models,
so they test offline. Every method is judged out-of-fold: weights and model choices are fitted on some of the labelled
reviews and scored on the rest."""
import itertools
import random
from collections import defaultdict

from app.core import thresholds as T
from app.services import ablation as A
from app.services import evaluation as E
from app.services import tuning as U
from app.services.fusion import ensemble

EQUAL = "ensemble, equal weights"
STORED = "ensemble, stored weights (current pipeline)"
WEIGHTED = "ensemble, gold-fitted weights"
SELECTED = "gold weights + model selection"
ENSEMBLES = (EQUAL, STORED, WEIGHTED, SELECTED)


def folds(ids, labels, k, seed=7):
    """Stratified k folds by label, as lists of ids."""
    rng = random.Random(seed)
    by = defaultdict(list)
    for i in ids:
        by[labels[i]].append(i)
    out = [[] for _ in range(k)]
    j = 0
    for lab in sorted(by):
        rows = by[lab][:]
        rng.shuffle(rows)
        for i in rows:
            out[j % k].append(i)
            j += 1
    return out


def _complete(weights, keys):
    """The pipeline's rule: if any model has no weight, every model gets weight 1."""
    return weights if weights and all(k in weights for k in keys) else {k: 1.0 for k in keys}


def predict_ensemble(ids, probs, keys, weights):
    out = {}
    for i in ids:
        use = [k for k in keys if i in probs.get(k, {})]
        if not use:
            continue
        n, u, p = ensemble([probs[k][i][:3] for k in use], [weights.get(k, 1.0) for k in use])
        out[i] = E.argmax_label(n, u, p)
    return out


def fit_weights(ids, gold, probs, keys, floor=0.01):
    """Weight = macro F1 of each model on these labelled reviews."""
    w = {}
    for k in keys:
        have = [i for i in ids if i in probs.get(k, {})]
        if len(have) < 5:
            continue
        f1 = E.macro_f1([gold[i] for i in have], [E.argmax_label(*probs[k][i][:3]) for i in have])
        if f1 is not None:
            w[k] = max(f1, floor)
    return w


def best_subset(ids, gold, probs, keys, weights):
    """Ablation rule: the subset of models with the highest macro F1. A smaller set must be strictly better to win."""
    best, best_f1 = list(keys), -1.0
    for r in range(len(keys), 0, -1):
        for sub in itertools.combinations(keys, r):
            pred = predict_ensemble(ids, probs, sub, weights)
            f1 = E.macro_f1([gold[i] for i in pred], list(pred.values()))
            if f1 is not None and f1 > best_f1 + 1e-9:
                best, best_f1 = list(sub), f1
    return best


def cross_validate(gold, group, probs, members, stored=None, k=5, min_fit=100, seed=7):
    """Out-of-fold predictions per system. A route group with fewer than min_fit fit reviews keeps equal weights."""
    ids = sorted(gold)
    out = {EQUAL: {}, WEIGHTED: {}, SELECTED: {}}
    if stored:
        out = {STORED: {}, **out}
    for fold in folds(ids, gold, k, seed):
        held = set(fold)
        fit = [i for i in ids if i not in held]
        for g, all_keys in members.items():
            keys = [m for m in all_keys if m in probs]
            test_g = [i for i in fold if group.get(i) == g]
            if not keys or not test_g:
                continue
            equal = {m: 1.0 for m in keys}
            out[EQUAL].update(predict_ensemble(test_g, probs, keys, equal))
            if stored:
                out[STORED].update(predict_ensemble(test_g, probs, keys, _complete(stored.get(g), keys)))
            fit_g = [i for i in fit if group.get(i) == g]
            if len(fit_g) >= min_fit:
                w = _complete(fit_weights(fit_g, gold, probs, keys), keys)
                use = best_subset(fit_g, gold, probs, keys, w)
            else:
                w, use = equal, keys
            out[WEIGHTED].update(predict_ensemble(test_g, probs, keys, w))
            out[SELECTED].update(predict_ensemble(test_g, probs, use, w))
    return out


def summarise(gold, systems, before):
    rows = []
    base = systems.get(before)
    for name, pred in systems.items():
        ids = A.common_ids(gold, pred)
        g, p = [gold[i] for i in ids], [pred[i] for i in ids]
        d = A.paired_bootstrap_diff(gold, pred, base) if base is not None and name != before else None
        rows.append({"system": name, "n": len(ids), "macro_f1": E.macro_f1(g, p), "accuracy": E.accuracy(g, p),
                     "ci": E.bootstrap_macro_f1(g, p),
                     "vs_before": None if d is None else {k: d[k] for k in ("diff", "lo", "hi", "verdict")}})
    return rows


def mismatch_cv(rows, k=5, seed=7, diff=T.MISMATCH_DIFF, conf=T.MISMATCH_MIN_CONF):
    """rows: (id, is_mismatch, text_score, star_score, confidence). Thresholds are tuned on the fit folds and scored on the held-out fold."""
    ids = [r[0] for r in rows]
    lab = {r[0]: ("yes" if r[1] else "no") for r in rows}
    by = {r[0]: r[1:] for r in rows}
    flags_default, flags_tuned, chosen = {}, {}, []
    for fold in folds(ids, lab, k, seed):
        held = set(fold)
        res = U.tune([by[i] for i in ids if i not in held])
        d, c = (res["best"]["diff"], res["best"]["conf"]) if res["ok"] else (diff, conf)
        chosen.append((d, c, res["ok"]))
        for i in fold:
            _m, t, s, cf = by[i]
            flags_default[i] = cf >= conf and abs(t - s) >= diff
            flags_tuned[i] = cf >= c and abs(t - s) >= d
    gold = [by[i][0] for i in ids]
    return {"default": E.binary_precision_recall(gold, [flags_default[i] for i in ids]),
            "tuned": E.binary_precision_recall(gold, [flags_tuned[i] for i in ids]), "fold_thresholds": chosen}


def _f(x, d=3):
    return "n/a" if x is None else f"{x:.{d}f}"


def conclusion(rows, before):
    ens = [r for r in rows if r["system"] in ENSEMBLES and r["macro_f1"] is not None]
    base = next((r for r in rows if r["system"] == before), None)
    if not ens or base is None:
        return "No ensemble result could be computed."
    best = max(ens, key=lambda r: r["macro_f1"])
    if best["system"] == before:
        return f"No method beat the current setup ({before}, macro F1 {_f(base['macro_f1'])}). Keep it as it is."
    v = best["vs_before"]
    if v is None:
        return "Too few shared reviews to compare the methods."
    head = (f"{best['system']} moved macro F1 from {_f(base['macro_f1'])} to {_f(best['macro_f1'])} ({v['diff']:+.3f}); "
            f"the 95% paired-bootstrap range is {v['lo']:+.3f} to {v['hi']:+.3f}.")
    if v["verdict"] == "beats":
        return head + " The range excludes zero, so the gain is real on this label set."
    if v["verdict"] == "worse":
        return head + " The range is below zero, so this method is worse and must not be adopted."
    return head + " The range includes zero, so the gain is within noise and must not be claimed as an improvement."


def render_markdown(meta, rows, mismatch, before):
    out = [f"## Accuracy experiment, {meta['date']}", "",
           f"- Labels: {meta['label_note']}",
           f"- Reviews: {meta['n']} ({meta['classes']})",
           f"- Method: {meta['folds']}-fold cross-validation. Weights and model choices are fitted on the training folds and scored "
           f"only on the held-out fold. A route group with fewer than {meta['min_fit']} fit reviews keeps equal weights.",
           f"- Before = {before}. Verdicts are a paired bootstrap of the macro-F1 difference (500 resamples) on the reviews both systems cover.",
           "", "| System | Reviews | Macro F1 (95% range) | Accuracy | Change vs before | Verdict |",
           "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        ci = f"{r['ci'][0]:.2f} to {r['ci'][1]:.2f}" if r["ci"] else "-"
        v = r["vs_before"]
        if r["system"] == before:
            chg, ver = "(before)", ""
        elif v is None:
            chg, ver = "-", "-"
        else:
            chg, ver = f"{v['diff']:+.3f}", v["verdict"]
        out.append(f"| {r['system']} | {r['n']} | {_f(r['macro_f1'])} ({ci}) | {_f(r['accuracy'])} | {chg} | {ver} |")
    if mismatch:
        d, t = mismatch["default"], mismatch["tuned"]
        picks = "; ".join(f"{a}, {b}, {'tuned' if c else 'default'}" for a, b, c in mismatch["fold_thresholds"])
        out += ["", "### Mismatch flags (thresholds tuned on the training folds)", "",
                "| Setting | Reviews | Flagged | Real mismatches | Precision | Recall |", "| --- | --- | --- | --- | --- | --- |",
                f"| Starting values (difference {T.MISMATCH_DIFF}, confidence {T.MISMATCH_MIN_CONF}) | {d['n']} | {d['flagged']} | {d['true_mismatches']} | {_f(d['precision'])} | {_f(d['recall'])} |",
                f"| Tuned per fold | {t['n']} | {t['flagged']} | {t['true_mismatches']} | {_f(t['precision'])} | {_f(t['recall'])} |",
                "", f"Thresholds chosen per fold (difference, confidence, source): {picks}"]
    out += ["", "### Conclusion", "", conclusion(rows, before), "", "### Limits", "",
            "- Only the TF-IDF baseline is trained by us. The other models are pretrained and used as downloaded; this experiment changes how their outputs are combined, not the models.",
            "- Small label sets give wide ranges. Quote the range, not just the point value.",
            "- Labels come from the people who labelled them; no second labeller was checked."]
    if meta.get("note"):
        out.append("- " + meta["note"])
    return "\n".join(out)
