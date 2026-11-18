# ReviewIQ final metrics

Generated 18 Nov 2026. Every number below comes from a script in backend/scripts, so it can be reproduced.

## 1. How to read this

- Macro F1 averages the F1 of negative, neutral and positive equally, so the rare neutral class counts as much as positive.
- MCC and Cohen kappa correct for chance agreement. Quadratic kappa also penalises negative-versus-positive mistakes more than negative-versus-neutral ones.
- ROC AUC, log loss and Brier score judge the probabilities, not just the final label. Expected calibration error says whether 90% confidence means right about 90% of the time.
- 95% ranges come from resampling the test reviews. McNemar and paired bootstrap tests say whether a difference between two systems is more than noise.

## 2. Model comparison on held-out data

Each model alone, the ensemble, and the ensemble with one model removed. Intervals are 95% bootstrap ranges.

**Route group english, seen categories (stars)**

| System | Macro F1 | 95% range | Accuracy |
|---|---|---|---|
| tfidf | 0.681 | 0.626 to 0.733 | 0.713 |
| roberta | 0.594 | 0.540 to 0.643 | 0.703 |
| nlptown | 0.687 | 0.624 to 0.744 | 0.747 |
| ensemble (all) | 0.700 | 0.641 to 0.753 | 0.770 |
| ensemble without tfidf | 0.684 | 0.624 to 0.743 | 0.760 |
| ensemble without roberta | 0.718 | 0.652 to 0.768 | 0.767 |
| ensemble without nlptown | 0.668 | 0.614 to 0.719 | 0.750 |

Ensemble minus best single model (nlptown): +0.012, no clear difference.

**Route group english, unseen categories (stars)**

| System | Macro F1 | 95% range | Accuracy |
|---|---|---|---|
| tfidf | 0.699 | 0.645 to 0.747 | 0.717 |
| roberta | 0.597 | 0.542 to 0.648 | 0.657 |
| nlptown | 0.699 | 0.642 to 0.747 | 0.750 |
| ensemble (all) | 0.697 | 0.646 to 0.748 | 0.743 |
| ensemble without tfidf | 0.676 | 0.623 to 0.728 | 0.730 |
| ensemble without roberta | 0.695 | 0.634 to 0.740 | 0.740 |
| ensemble without nlptown | 0.669 | 0.616 to 0.714 | 0.713 |

Ensemble minus best single model (nlptown): -0.002, no clear difference.

**Route group english, polarity (tweets, Hindi)**

| System | Macro F1 | 95% range | Accuracy |
|---|---|---|---|
| tfidf | 0.672 | 0.616 to 0.719 | 0.683 |
| roberta | 0.680 | 0.634 to 0.737 | 0.703 |
| nlptown | 0.494 | 0.454 to 0.541 | 0.587 |
| ensemble (all) | 0.703 | 0.651 to 0.765 | 0.740 |
| ensemble without tfidf | 0.663 | 0.611 to 0.722 | 0.707 |
| ensemble without roberta | 0.612 | 0.551 to 0.665 | 0.677 |
| ensemble without nlptown | 0.736 | 0.680 to 0.788 | 0.757 |

Ensemble minus best single model (roberta): +0.023, no clear difference.

**Route group multi, polarity (tweets, Hindi)**

| System | Macro F1 | 95% range | Accuracy |
|---|---|---|---|
| tfidf | 0.550 | 0.495 to 0.604 | 0.560 |
| xlmr | 0.149 | 0.107 to 0.187 | 0.150 |
| ensemble (all) | 0.486 | 0.432 to 0.537 | 0.500 |

Ensemble minus best single model (tfidf): -0.064, worse.

## 3. Learned combination (stacker) versus weighted average

The weighted average is what the pipeline used before. The stacker learns each model's habits from the validation split. It is switched on only when cross-validation shows a clear gain. Test-set numbers below were never used for training or for that decision.

### Route group: english

Gate: applied. beats the weighted average in cross-validation. Validation reviews: 800. Cross-validated macro F1: stacker 0.728, weighted average 0.690.

**seen categories (stars), n=300**

| Metric | Weighted average | Stacker |
|---|---|---|
| Accuracy | 0.770 | 0.727 |
| Balanced accuracy | 0.700 | 0.707 |
| Macro precision | 0.708 | 0.710 |
| Macro recall | 0.700 | 0.707 |
| Macro F1 | 0.700 | 0.697 |
| Weighted F1 | 0.759 | 0.743 |
| MCC | 0.636 | 0.595 |
| Cohen kappa | 0.633 | 0.586 |
| Quadratic kappa | 0.802 | 0.792 |
| ROC AUC (one vs rest) | 0.890 | 0.896 |
| Log loss (lower is better) | 0.584 | 0.573 |
| Brier score (lower is better) | 0.330 | 0.342 |
| Opposite-polarity errors (lower is better) | 0.033 | 0.013 |
| Expected calibration error (lower is better) | 0.0885 | 0.0569 |
| Macro F1, 95% range | 0.645 to 0.754 | 0.638 to 0.749 |
| Accuracy, 95% range | 0.723 to 0.817 | 0.670 to 0.783 |

Significance: McNemar exact test p = 0.0660 (15 reviews only the stacker got right, 28 only the average). Paired bootstrap on macro F1: -0.003 (95% range -0.053 to +0.050), no clear difference.

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| neg | 0.857 | 0.672 | 0.753 | 125 |
| neu | 0.389 | 0.603 | 0.473 | 58 |
| pos | 0.884 | 0.846 | 0.865 | 117 |

**unseen categories (stars), n=300**

| Metric | Weighted average | Stacker |
|---|---|---|
| Accuracy | 0.743 | 0.757 |
| Balanced accuracy | 0.699 | 0.740 |
| Macro precision | 0.710 | 0.746 |
| Macro recall | 0.699 | 0.740 |
| Macro F1 | 0.697 | 0.740 |
| Weighted F1 | 0.730 | 0.764 |
| MCC | 0.605 | 0.633 |
| Cohen kappa | 0.600 | 0.631 |
| Quadratic kappa | 0.769 | 0.807 |
| ROC AUC (one vs rest) | 0.900 | 0.899 |
| Log loss (lower is better) | 0.592 | 0.622 |
| Brier score (lower is better) | 0.334 | 0.338 |
| Opposite-polarity errors (lower is better) | 0.037 | 0.013 |
| Expected calibration error (lower is better) | 0.0797 | 0.0319 |
| Macro F1, 95% range | 0.646 to 0.746 | 0.691 to 0.783 |
| Accuracy, 95% range | 0.693 to 0.793 | 0.713 to 0.797 |

Significance: McNemar exact test p = 0.5966 (18 reviews only the stacker got right, 14 only the average). Paired bootstrap on macro F1: +0.043 (95% range -0.002 to +0.089), no clear difference.

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| neg | 0.805 | 0.798 | 0.802 | 119 |
| neu | 0.517 | 0.625 | 0.566 | 72 |
| pos | 0.916 | 0.798 | 0.853 | 109 |

**polarity (tweets, Hindi), n=300**

| Metric | Weighted average | Stacker |
|---|---|---|
| Accuracy | 0.737 | 0.740 |
| Balanced accuracy | 0.696 | 0.741 |
| Macro precision | 0.709 | 0.733 |
| Macro recall | 0.696 | 0.741 |
| Macro F1 | 0.698 | 0.730 |
| Weighted F1 | 0.728 | 0.746 |
| MCC | 0.591 | 0.611 |
| Cohen kappa | 0.588 | 0.607 |
| Quadratic kappa | 0.705 | 0.686 |
| ROC AUC (one vs rest) | 0.887 | 0.894 |
| Log loss (lower is better) | 0.661 | 0.639 |
| Brier score (lower is better) | 0.375 | 0.362 |
| Opposite-polarity errors (lower is better) | 0.070 | 0.067 |
| Expected calibration error (lower is better) | 0.1164 | 0.0544 |
| Macro F1, 95% range | 0.646 to 0.756 | 0.681 to 0.783 |
| Accuracy, 95% range | 0.693 to 0.787 | 0.690 to 0.793 |

Significance: McNemar exact test p = 1.0000 (27 reviews only the stacker got right, 26 only the average). Paired bootstrap on macro F1: +0.033 (95% range -0.023 to +0.082), no clear difference.

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| neg | 0.814 | 0.718 | 0.763 | 110 |
| neu | 0.554 | 0.750 | 0.638 | 68 |
| pos | 0.829 | 0.754 | 0.790 | 122 |

## 4. Your own data

| Item | Value |
|---|---|
| Reviews | 6,067 |
| Products | 3548 |
| Languages | 10 |
| Aspect mentions | 2,967 |
| Issues found | 34 |
| Flagged as spam | 1 |

### Final pipeline against your hand labels (n=31)

| Metric | Value |
|---|---|
| Accuracy | 0.774 |
| Accuracy, 95% range | 0.645 to 0.903 |
| Balanced accuracy | 0.697 |
| Macro F1 | 0.723 |
| Macro F1, 95% range | 0.487 to 0.904 |
| Weighted F1 | 0.764 |
| MCC | 0.630 |
| Cohen kappa | 0.621 |
| Quadratic kappa | 0.654 |
| Opposite-polarity errors | 0.129 |

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| neg | 0.714 | 0.833 | 0.769 | 12 |
| neu | 1.000 | 0.400 | 0.571 | 5 |
| pos | 0.800 | 0.857 | 0.828 | 14 |

### Star prediction from the review text

How close the star rating predicted from the words is to the rating the customer gave.

| Metric | Value |
|---|---|
| Reviews | 1,608 |
| Mean absolute error (stars) | 1.019 |
| Root mean squared error | 1.519 |
| Within half a star | 0.481 |
| Within one star | 0.704 |
| Average bias (stars) | -0.075 |
| Pearson correlation | 0.492 |
| Spearman correlation | 0.470 |
