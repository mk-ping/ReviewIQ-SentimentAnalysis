# Benchmark on human-labelled sentiment datasets

These datasets carry sentiment labels written by people, so they test the model without relying on star ratings. Binary sets (positive or negative) are scored on those two classes only. Intervals are 95% bootstrap ranges.

## Summary (weighted ensemble)

| Dataset | What it is | Reviews | Accuracy | Macro F1 | Best system |
|---|---|---|---|---|---|
| tweet_eval | Tweets, 3 classes, people-labelled (SemEval) | 500 | 0.620 | 0.623 | roberta |
| tweet_sentiment | Tweets, 3 classes, people-labelled | 499 | 0.673 | 0.672 | roberta |
| sst5 | Movie sentences, 5 levels collapsed to 3 | 500 | 0.752 | 0.679 | learned stacker |
| sst2 | Movie sentences, positive or negative | 500 | 0.876 | 0.876 | weighted ensemble |
| amazon_polarity | Product reviews, positive or negative | 500 | 0.944 | 0.944 | learned stacker |
| financial_news | Finance tweets, 3 classes | 500 | 0.288 | 0.302 | learned stacker |
| **average** | | | **0.692** | **0.683** | |

### tweet_eval

Tweets, 3 classes, people-labelled (SemEval). 500 reviews (neg 162, neu 242, pos 96).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.498 | 0.454 to 0.540 | 0.498 | 0.254 | 0.246 | 0.703 | 0.0350 | 0.096 |
| roberta | 0.726 | 0.690 to 0.768 | 0.734 | 0.571 | 0.568 | 0.883 | 0.0685 | 0.008 |
| nlptown | 0.438 | 0.392 to 0.486 | 0.387 | 0.294 | 0.225 | 0.751 | 0.2558 | 0.080 |
| weighted ensemble | 0.620 | 0.576 to 0.666 | 0.623 | 0.481 | 0.441 | 0.865 | 0.0928 | 0.034 |
| learned stacker | 0.608 | 0.566 to 0.652 | 0.607 | 0.421 | 0.405 | 0.818 | 0.0568 | 0.030 |

### tweet_sentiment

Tweets, 3 classes, people-labelled. 499 reviews (neg 143, neu 200, pos 156).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.625 | 0.581 to 0.665 | 0.626 | 0.430 | 0.423 | 0.807 | 0.0566 | 0.030 |
| roberta | 0.689 | 0.647 to 0.727 | 0.690 | 0.546 | 0.538 | 0.878 | 0.0873 | 0.034 |
| nlptown | 0.501 | 0.457 to 0.545 | 0.445 | 0.331 | 0.284 | 0.766 | 0.1920 | 0.092 |
| weighted ensemble | 0.673 | 0.633 to 0.711 | 0.672 | 0.532 | 0.517 | 0.880 | 0.0961 | 0.034 |
| learned stacker | 0.677 | 0.635 to 0.719 | 0.683 | 0.510 | 0.504 | 0.843 | 0.0567 | 0.010 |

### sst5

Movie sentences, 5 levels collapsed to 3. 500 reviews (neg 206, neu 88, pos 206).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.690 | 0.644 to 0.728 | 0.599 | 0.499 | 0.495 | 0.809 | 0.1236 | 0.102 |
| roberta | 0.656 | 0.614 to 0.698 | 0.615 | 0.485 | 0.476 | 0.830 | 0.0933 | 0.036 |
| nlptown | 0.652 | 0.606 to 0.690 | 0.559 | 0.443 | 0.442 | 0.785 | 0.0635 | 0.086 |
| weighted ensemble | 0.752 | 0.712 to 0.786 | 0.679 | 0.602 | 0.602 | 0.855 | 0.1445 | 0.054 |
| learned stacker | 0.748 | 0.706 to 0.784 | 0.685 | 0.597 | 0.597 | 0.861 | 0.0636 | 0.060 |

### sst2

Movie sentences, positive or negative. 500 reviews (neg 245, pos 255).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.822 | 0.794 to 0.856 | 0.822 | 0.644 | 0.644 | 0.896 | 0.0882 | 0.178 |
| roberta | 0.844 | 0.812 to 0.876 | 0.844 | 0.694 | 0.689 | 0.920 | 0.0835 | 0.156 |
| nlptown | 0.814 | 0.776 to 0.846 | 0.813 | 0.629 | 0.627 | 0.899 | 0.0483 | 0.186 |
| weighted ensemble | 0.876 | 0.844 to 0.906 | 0.876 | 0.752 | 0.752 | 0.945 | 0.0786 | 0.124 |
| learned stacker | 0.870 | 0.840 to 0.896 | 0.870 | 0.740 | 0.740 | 0.942 | 0.0297 | 0.130 |

### amazon_polarity

Product reviews, positive or negative. 500 reviews (neg 250, pos 250).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.878 | 0.846 to 0.908 | 0.878 | 0.757 | 0.756 | 0.948 | 0.0821 | 0.122 |
| roberta | 0.912 | 0.886 to 0.936 | 0.912 | 0.824 | 0.824 | 0.970 | 0.0313 | 0.088 |
| nlptown | 0.934 | 0.910 to 0.954 | 0.934 | 0.868 | 0.868 | 0.982 | 0.0182 | 0.066 |
| weighted ensemble | 0.944 | 0.920 to 0.964 | 0.944 | 0.888 | 0.888 | 0.984 | 0.0711 | 0.056 |
| learned stacker | 0.954 | 0.934 to 0.972 | 0.954 | 0.908 | 0.908 | 0.986 | 0.0206 | 0.046 |

### financial_news

Finance tweets, 3 classes. 500 reviews (neg 73, neu 99, pos 328).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.250 | 0.216 to 0.290 | 0.251 | 0.032 | 0.023 | 0.554 | 0.2254 | 0.288 |
| roberta | 0.238 | 0.202 to 0.274 | 0.291 | -0.051 | -0.033 | 0.550 | 0.5203 | 0.068 |
| nlptown | 0.458 | 0.412 to 0.502 | 0.326 | 0.210 | 0.162 | 0.657 | 0.2014 | 0.340 |
| weighted ensemble | 0.288 | 0.248 to 0.330 | 0.302 | 0.027 | 0.021 | 0.594 | 0.2069 | 0.200 |
| learned stacker | 0.352 | 0.314 to 0.394 | 0.365 | 0.192 | 0.142 | 0.664 | 0.2190 | 0.232 |

### multilingual_hi

Skipped: DatasetNotFoundError.

### multilingual_es

Skipped: DatasetNotFoundError.

### multilingual_de

Skipped: DatasetNotFoundError.
