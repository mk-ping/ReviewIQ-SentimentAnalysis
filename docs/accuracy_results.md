# Accuracy results

Each section is one measurement. Newest at the bottom.


## Baseline measurement, 17 Nov 2026 (docs/run_report.txt)

- Labels: derived from stars (public held-out sets), so these are agreement with stars, not accuracy against hand labels.
- Setup: English route group, 300 reviews per set, ensemble weights = validation macro F1, 95% ranges by bootstrap.

| System | Seen categories | Unseen categories | Polarity (tweets, Hindi) |
| --- | --- | --- | --- |
| TF-IDF + LR | 0.681 | 0.699 | 0.672 |
| RoBERTa | 0.594 | 0.597 | 0.680 |
| nlptown | 0.687 | 0.699 | 0.494 |
| Ensemble, all three | 0.700 | 0.697 | 0.703 |
| Ensemble without RoBERTa | 0.718 | 0.695 | 0.612 |
| Ensemble without nlptown | 0.668 | 0.669 | 0.736 |
| Ensemble without TF-IDF | 0.684 | 0.676 | 0.663 |
| Ensemble minus best single | +0.012, no clear difference | -0.002, no clear difference | +0.023, no clear difference |

- Multilingual group (polarity rows): TF-IDF 0.550, XLM-R 0.149 (accuracy 0.150, below chance), ensemble 0.493, ensemble minus best single -0.057 (worse). Suspected cause: label order of the public polarity data.
- European group: only 16 validation reviews, so equal weights apply and no held-out result exists.
- Aspect sentiment against an independent ABSA model: agreement 89.1%, kappa 0.766 (366 sentences). Weakest aspect: ease of use, 71.7%.
- Reference from the original run: ensemble 0.689 against TF-IDF 0.684, a gain within noise.
- Conclusion: the ensemble is not clearly better than its best member, and no accuracy claim can be made until the gold set exists.

## Accuracy experiment, 2026-11-18

- Labels: hand labels from the Label page (source gold), never derived from stars
- Reviews: 31 (neg 12, neu 5, pos 14)
- Method: 5-fold cross-validation. Weights and model choices are fitted on the training folds and scored only on the held-out fold. A route group with fewer than 100 fit reviews keeps equal weights.
- Before = ensemble, stored weights (current pipeline). Verdicts are a paired bootstrap of the macro-F1 difference (500 resamples) on the reviews both systems cover.

| System | Reviews | Macro F1 (95% range) | Accuracy | Change vs before | Verdict |
| --- | --- | --- | --- | --- | --- |
| stars alone | 31 | 0.692 (0.47 to 0.83) | 0.645 | -0.030 | no clear difference |
| nlptown alone | 18 | 0.663 (0.35 to 0.89) | 0.722 | +0.008 | no clear difference |
| roberta alone | 17 | 0.667 (0.45 to 0.91) | 0.765 | +0.019 | no clear difference |
| tfidf alone | 30 | 0.398 (0.25 to 0.54) | 0.533 | -0.366 | worse |
| xlmr alone | 14 | 0.811 (0.44 to 1.00) | 0.857 | +0.000 | no clear difference |
| ensemble, stored weights (current pipeline) | 31 | 0.723 (0.49 to 0.90) | 0.774 | (before) |  |
| ensemble, equal weights | 31 | 0.723 (0.49 to 0.90) | 0.774 | +0.000 | no clear difference |
| ensemble, gold-fitted weights | 31 | 0.723 (0.49 to 0.90) | 0.774 | +0.000 | no clear difference |
| gold weights + model selection | 31 | 0.723 (0.49 to 0.90) | 0.774 | +0.000 | no clear difference |

### Conclusion

No method beat the current setup (ensemble, stored weights (current pipeline), macro F1 0.723). Keep it as it is.

### Limits

- Only the TF-IDF baseline is trained by us. The other models are pretrained and used as downloaded; this experiment changes how their outputs are combined, not the models.
- Small label sets give wide ranges. Quote the range, not just the point value.
- Labels come from the people who labelled them; no second labeller was checked.
