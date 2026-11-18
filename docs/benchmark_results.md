# Benchmark on human-labelled sentiment datasets

These datasets carry sentiment labels written by people, so they test the model without relying on star ratings. Binary sets (positive or negative) are scored on those two classes only. Intervals are 95% bootstrap ranges.

## Summary (weighted ensemble)

| Dataset | What it is | Reviews | Accuracy | Macro F1 | Best system |
|---|---|---|---|---|---|
| tweet_eval | Tweets, 3 classes, people-labelled (SemEval) | 500 | 0.628 | 0.634 | roberta |
| tweet_sentiment | Tweets, 3 classes, people-labelled | 499 | 0.683 | 0.679 | learned stacker |
| sst5 | Movie sentences, 5 levels collapsed to 3 | 500 | 0.742 | 0.661 | weighted ensemble |
| sst2 | Movie sentences, positive or negative | 500 | 0.870 | 0.870 | learned stacker |
| amazon_polarity | Product reviews, positive or negative | 500 | 0.936 | 0.936 | learned stacker |
| financial_news | Finance tweets, 3 classes | 500 | 0.648 | 0.580 | roberta |
| **average** | | | **0.751** | **0.727** | |

### tweet_eval

Tweets, 3 classes, people-labelled (SemEval). 500 reviews (neg 162, neu 242, pos 96).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.494 | 0.452 to 0.538 | 0.456 | 0.173 | 0.168 | 0.651 | 0.0320 | 0.052 |
| roberta | 0.726 | 0.690 to 0.768 | 0.734 | 0.571 | 0.568 | 0.883 | 0.0685 | 0.008 |
| nlptown | 0.438 | 0.392 to 0.486 | 0.387 | 0.294 | 0.225 | 0.751 | 0.2558 | 0.080 |
| weighted ensemble | 0.628 | 0.592 to 0.670 | 0.634 | 0.465 | 0.443 | 0.857 | 0.0779 | 0.024 |
| learned stacker | 0.678 | 0.642 to 0.718 | 0.680 | 0.480 | 0.478 | 0.851 | 0.0283 | 0.008 |

### tweet_sentiment

Tweets, 3 classes, people-labelled. 499 reviews (neg 143, neu 200, pos 156).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.573 | 0.533 to 0.615 | 0.576 | 0.349 | 0.347 | 0.776 | 0.0397 | 0.044 |
| roberta | 0.689 | 0.647 to 0.727 | 0.690 | 0.546 | 0.538 | 0.878 | 0.0873 | 0.034 |
| nlptown | 0.501 | 0.457 to 0.545 | 0.445 | 0.331 | 0.284 | 0.766 | 0.1920 | 0.092 |
| weighted ensemble | 0.683 | 0.643 to 0.723 | 0.679 | 0.554 | 0.533 | 0.872 | 0.0961 | 0.038 |
| learned stacker | 0.721 | 0.681 to 0.760 | 0.725 | 0.587 | 0.583 | 0.881 | 0.0299 | 0.022 |

### sst5

Movie sentences, 5 levels collapsed to 3. 500 reviews (neg 206, neu 88, pos 206).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.626 | 0.576 to 0.664 | 0.532 | 0.391 | 0.387 | 0.740 | 0.1027 | 0.164 |
| roberta | 0.656 | 0.614 to 0.698 | 0.615 | 0.485 | 0.476 | 0.830 | 0.0933 | 0.036 |
| nlptown | 0.652 | 0.606 to 0.690 | 0.559 | 0.443 | 0.442 | 0.785 | 0.0635 | 0.086 |
| weighted ensemble | 0.742 | 0.704 to 0.778 | 0.661 | 0.587 | 0.586 | 0.841 | 0.1478 | 0.044 |
| learned stacker | 0.732 | 0.690 to 0.768 | 0.635 | 0.568 | 0.565 | 0.847 | 0.0440 | 0.054 |

### sst2

Movie sentences, positive or negative. 500 reviews (neg 245, pos 255).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.798 | 0.764 to 0.832 | 0.798 | 0.596 | 0.596 | 0.852 | 0.1134 | 0.202 |
| roberta | 0.844 | 0.812 to 0.876 | 0.844 | 0.694 | 0.689 | 0.920 | 0.0835 | 0.156 |
| nlptown | 0.814 | 0.776 to 0.846 | 0.813 | 0.629 | 0.627 | 0.899 | 0.0483 | 0.186 |
| weighted ensemble | 0.870 | 0.840 to 0.898 | 0.870 | 0.740 | 0.740 | 0.934 | 0.0873 | 0.130 |
| learned stacker | 0.870 | 0.842 to 0.900 | 0.870 | 0.741 | 0.740 | 0.941 | 0.0282 | 0.130 |

### amazon_polarity

Product reviews, positive or negative. 500 reviews (neg 250, pos 250).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.838 | 0.802 to 0.872 | 0.838 | 0.676 | 0.676 | 0.927 | 0.0986 | 0.162 |
| roberta | 0.912 | 0.886 to 0.936 | 0.912 | 0.824 | 0.824 | 0.970 | 0.0313 | 0.088 |
| nlptown | 0.934 | 0.910 to 0.954 | 0.934 | 0.868 | 0.868 | 0.982 | 0.0182 | 0.066 |
| weighted ensemble | 0.936 | 0.910 to 0.956 | 0.936 | 0.872 | 0.872 | 0.985 | 0.0917 | 0.064 |
| learned stacker | 0.946 | 0.922 to 0.964 | 0.946 | 0.893 | 0.892 | 0.985 | 0.0137 | 0.054 |

### financial_news

Finance tweets, 3 classes. 500 reviews (neg 73, neu 328, pos 99).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.654 | 0.610 to 0.696 | 0.473 | 0.234 | 0.223 | 0.661 | 0.0619 | 0.030 |
| roberta | 0.684 | 0.642 to 0.724 | 0.587 | 0.350 | 0.348 | 0.806 | 0.0743 | 0.004 |
| nlptown | 0.220 | 0.186 to 0.260 | 0.215 | 0.102 | 0.061 | 0.604 | 0.4297 | 0.124 |
| weighted ensemble | 0.648 | 0.608 to 0.688 | 0.580 | 0.346 | 0.344 | 0.777 | 0.1350 | 0.018 |
| learned stacker | 0.702 | 0.662 to 0.744 | 0.571 | 0.348 | 0.332 | 0.811 | 0.0722 | 0.002 |

### multilingual_hi

Skipped: RuntimeError.

### multilingual_es

Skipped: RuntimeError.

### multilingual_de

Skipped: RuntimeError.

### multilingual_fr

Skipped: RuntimeError.
