"""Collects every result into docs/final_metrics.md (tables ready to paste into the report) and docs/figures/*.png.
Reads ml/out/heldout_results.json (eval_heldout), ml/out/stack_results.json (train_stacker) and, when the database is up,
your hand-labelled gold set and the star predictions on your own reviews. Anything not run yet is listed at the end.
Run from backend:  python -m scripts.final_report"""
import asyncio
import json
import re
from datetime import date
from pathlib import Path

from app.services import metrics as M

OUT = Path("../ml/out")
DOCS = Path("../docs")
FIG = DOCS / "figures"


def f(x, k=3):
    return "-" if x is None else f"{x:.{k}f}"


def ci(c):
    return "-" if not c else f"{c[0]:.3f} to {c[1]:.3f}"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"] + ["| " + " | ".join(map(str, r)) + " |" for r in rows] + [""]


def fig_confusion(m, title, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    pct = [[(m[i][j] / sum(m[i]) if sum(m[i]) else 0) for j in range(3)] for i in range(3)]
    fig, ax = plt.subplots(figsize=(4, 3.4))
    ax.imshow(pct, cmap="Blues", vmin=0, vmax=1)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{m[i][j]}\n{pct[i][j] * 100:.0f}%", ha="center", va="center", color="white" if pct[i][j] > .5 else "black", fontsize=8)
    ax.set_xticks(range(3), M.LABELS); ax.set_yticks(range(3), M.LABELS)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title(title, fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)
    return True


def fig_reliability(cal, title, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(4, 3.4))
    ax.plot([0, 1], [0, 1], "--", color="grey", lw=1)
    ax.plot([b["confidence"] for b in cal["bins"]], [b["accuracy"] for b in cal["bins"]], "o-", color="#5b4bd6")
    ax.set_xlabel("Confidence"); ax.set_ylabel("Accuracy"); ax.set_title(f"{title} (ECE {cal['ece']})", fontsize=9)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)
    return True


def heldout_section(lines, missing):
    p = OUT / "heldout_results.json"
    if not p.exists():
        missing.append("python -m scripts.eval_heldout --cap 300   (model comparison and ablation on held-out data)")
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    lines += ["## 2. Model comparison on held-out data", "",
              "Each model alone, the ensemble, and the ensemble with one model removed. Intervals are 95% bootstrap ranges.", ""]
    for g, sets in data.items():
        for sname, rows in sets.items():
            lines += [f"**Route group {g}, {sname}**", ""]
            body, note = [], None
            for r in rows:
                if "system" in r:
                    body.append([r["system"], f(r["macro_f1"]), ci(r.get("ci")), f(r["accuracy"])])
                else:
                    note = f"Ensemble minus best single model ({r['ensemble_vs_best_single']}): {r['diff']:+.3f}, {r['verdict']}."
            lines += table(["System", "Macro F1", "95% range", "Accuracy"], body)
            if note:
                lines += [note, ""]


def stack_section(lines, missing):
    p = OUT / "stack_results.json"
    if not p.exists():
        missing.append("python -m scripts.train_stacker   (learned model combination and the full metric suite)")
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    FIG.mkdir(parents=True, exist_ok=True)
    lines += ["## 3. Learned combination (stacker) versus weighted average", "",
              "The weighted average is what the pipeline used before. The stacker learns each model's habits from the validation split. "
              "It is switched on only when cross-validation shows a clear gain. Test-set numbers below were never used for training or for that decision.", ""]
    for g, sets in data.items():
        gate = sets.get("_gate", {})
        lines += [f"### Route group: {g}", "",
                  f"Gate: {'applied' if gate.get('applied') else 'not applied'}. {gate.get('reason', '')}. Validation reviews: {gate.get('n_val')}. "
                  f"Cross-validated macro F1: stacker {f(gate.get('cv_macro_f1_stacker'))}, weighted average {f(gate.get('cv_macro_f1_weighted_average'))}.", ""]
        for sname, d in sets.items():
            if sname == "_gate":
                continue
            b, s = d["weighted_average"], d["stacker"]
            lines += [f"**{sname}, n={d['n']}**", ""]
            keys = [("Accuracy", "accuracy"), ("Balanced accuracy", "balanced_accuracy"), ("Macro precision", "macro_precision"),
                    ("Macro recall", "macro_recall"), ("Macro F1", "macro_f1"), ("Weighted F1", "weighted_f1"), ("MCC", "mcc"),
                    ("Cohen kappa", "kappa"), ("Quadratic kappa", "quadratic_kappa"), ("ROC AUC (one vs rest)", "auc_ovr"),
                    ("Log loss (lower is better)", "log_loss"), ("Brier score (lower is better)", "brier"),
                    ("Opposite-polarity errors (lower is better)", "opposite_error_rate")]
            lines += table(["Metric", "Weighted average", "Stacker"], [[n, f(b.get(k)), f(s.get(k))] for n, k in keys]
                           + [["Expected calibration error (lower is better)", f(b.get("calibration", {}).get("ece"), 4), f(s.get("calibration", {}).get("ece"), 4)],
                              ["Macro F1, 95% range", ci(d["ci_macro_f1"]["weighted_average"]), ci(d["ci_macro_f1"]["stacker"])],
                              ["Accuracy, 95% range", ci(d["ci_accuracy"]["weighted_average"]), ci(d["ci_accuracy"]["stacker"])]])
            mc, pd = d["mcnemar"], d.get("paired") or {}
            lines += [f"Significance: McNemar exact test p = {mc['p_value']:.4f} ({mc['only_a']} reviews only the stacker got right, {mc['only_b']} only the average). "
                      f"Paired bootstrap on macro F1: {pd.get('diff', 0):+.3f} (95% range {pd.get('lo', 0):+.3f} to {pd.get('hi', 0):+.3f}), {pd.get('verdict', '-')}.", ""]
            lines += table(["Class", "Precision", "Recall", "F1", "Support"],
                           [[c, f(s["per_class"][c]["precision"]), f(s["per_class"][c]["recall"]), f(s["per_class"][c]["f1"]), s["per_class"][c]["support"]] for c in M.LABELS])
            use = s if gate.get("applied") else b
            tag = f"{slug(g)}_{slug(sname)}"
            if fig_confusion(use["confusion"], f"{g}, {sname}", FIG / f"confusion_{tag}.png"):
                lines += [f"![Confusion matrix](figures/confusion_{tag}.png)", ""]
            if use.get("calibration") and fig_reliability(use["calibration"], f"{g}", FIG / f"reliability_{tag}.png"):
                lines += [f"![Reliability diagram](figures/reliability_{tag}.png)", ""]


async def db_section(lines, missing):
    from sqlalchemy import text
    from app.db.session import SessionLocal

    try:
        async with SessionLocal() as s:
            gold = (await s.execute(text("""
                SELECT g.review_id, g.label, sc.text_label, sc.confidence FROM gold_label g
                JOIN review_score sc ON sc.review_id = g.review_id WHERE g.source = 'gold'"""))).all()
            stars = (await s.execute(text("""
                SELECT r.rating_norm, sc.pred_stars, sc.fused_stars FROM review r JOIN review_score sc ON sc.review_id = r.review_id
                WHERE r.rating_norm IS NOT NULL"""))).all()
            counts = (await s.execute(text("""
                SELECT (SELECT count(*) FROM review), (SELECT count(DISTINCT product_id) FROM review),
                       (SELECT count(DISTINCT language) FROM review), (SELECT count(*) FROM review_aspect),
                       (SELECT count(*) FROM issue), (SELECT count(*) FROM review WHERE spam_score > 0.69)"""))).one()
    except Exception as e:
        missing.append(f"database not reachable ({type(e).__name__}); start it and run again for the gold-set and star metrics")
        return
    lines += ["## 4. Your own data", "", *table(["Item", "Value"], [["Reviews", f"{counts[0]:,}"], ["Products", counts[1]], ["Languages", counts[2]],
                                                                    ["Aspect mentions", f"{counts[3]:,}"], ["Issues found", counts[4]], ["Flagged as spam", counts[5]]])]
    if len(gold) >= 30:
        g = [r[1] for r in gold]
        p = [r[2] for r in gold]
        rep = M.report(g, p)
        lines += [f"### Final pipeline against your hand labels (n={len(g)})", ""]
        lines += table(["Metric", "Value"], [["Accuracy", f(rep["accuracy"])], ["Accuracy, 95% range", ci(M.bootstrap_ci(M.f_acc, g, p))],
                                            ["Balanced accuracy", f(rep["balanced_accuracy"])], ["Macro F1", f(rep["macro_f1"])],
                                            ["Macro F1, 95% range", ci(M.bootstrap_ci(M.f_macro, g, p))], ["Weighted F1", f(rep["weighted_f1"])],
                                            ["MCC", f(rep["mcc"])], ["Cohen kappa", f(rep["kappa"])], ["Quadratic kappa", f(rep["quadratic_kappa"])],
                                            ["Opposite-polarity errors", f(rep["opposite_error_rate"])]])
        lines += table(["Class", "Precision", "Recall", "F1", "Support"], [[c, f(v["precision"]), f(v["recall"]), f(v["f1"]), v["support"]] for c, v in rep["per_class"].items()])
        FIG.mkdir(parents=True, exist_ok=True)
        if fig_confusion(rep["confusion"], "Gold set", FIG / "confusion_gold.png"):
            lines += ["![Confusion matrix](figures/confusion_gold.png)", ""]
    else:
        missing.append(f"gold labels: {len(gold)} so far, label 200+ on the Model Evaluation page (open /label) for the accuracy section")
    pairs = [(a, p) for a, p, _ in stars if p is not None]
    if len(pairs) >= 30:
        sm = M.star_metrics([a for a, _ in pairs], [p for _, p in pairs])
        lines += ["### Star prediction from the review text", "",
                  "How close the star rating predicted from the words is to the rating the customer gave.", "",
                  *table(["Metric", "Value"], [["Reviews", f"{sm['n']:,}"], ["Mean absolute error (stars)", f(sm["mae"])], ["Root mean squared error", f(sm["rmse"])],
                                               ["Within half a star", f(sm["within_half_star"])], ["Within one star", f(sm["within_one_star"])],
                                               ["Average bias (stars)", f(sm["bias"])], ["Pearson correlation", f(sm["pearson"])], ["Spearman correlation", f(sm["spearman"])]])]


def main() -> None:
    lines = [f"# ReviewIQ final metrics", "", f"Generated {date.today():%d %b %Y}. Every number below comes from a script in backend/scripts, so it can be reproduced.", "",
             "## 1. How to read this", "",
             "- Macro F1 averages the F1 of negative, neutral and positive equally, so the rare neutral class counts as much as positive.",
             "- MCC and Cohen kappa correct for chance agreement. Quadratic kappa also penalises negative-versus-positive mistakes more than negative-versus-neutral ones.",
             "- ROC AUC, log loss and Brier score judge the probabilities, not just the final label. Expected calibration error says whether 90% confidence means right about 90% of the time.",
             "- 95% ranges come from resampling the test reviews. McNemar and paired bootstrap tests say whether a difference between two systems is more than noise.", ""]
    missing: list[str] = []
    heldout_section(lines, missing)
    stack_section(lines, missing)
    asyncio.run(db_section(lines, missing))
    if missing:
        lines += ["## Not yet run", "", *[f"- {m}" for m in missing], ""]
    DOCS.mkdir(exist_ok=True)
    (DOCS / "final_metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", DOCS / "final_metrics.md")
    for m in missing:
        print("TODO:", m)


if __name__ == "__main__":
    main()
