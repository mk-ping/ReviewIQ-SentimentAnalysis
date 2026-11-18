# Final result on public datasets

Genres the models were built for: product reviews, restaurant reviews and movie reviews. These sets were chosen because they match the training genres, so this is the in-domain result; weaker genres (tweets, finance, other languages) are reported separately in benchmark_results.md. No model, weight or threshold was tuned on these test splits.

## Summary (weighted ensemble)

| Dataset | What it is | Reviews | Accuracy | Macro F1 | Best system |
|---|---|---|---|---|---|
| sst2 | Movie sentences, positive or negative | 872 | 0.881 | 0.881 | weighted ensemble |
| amazon_polarity | Product reviews, positive or negative | 1000 | 0.939 | 0.939 | learned stacker |
| imdb | Movie reviews, positive or negative | 1000 | 0.893 | 0.893 | learned stacker |
| amazon_reviews_en | Product reviews, 1 to 5 stars turned into negative, neutral, positive | 1000 | 0.751 | 0.684 | learned stacker |
| **average** | | | **0.866** | **0.849** | |

These datasets carry sentiment labels written by people, so they test the model without relying on star ratings. Binary sets (positive or negative) are scored on those two classes only. Intervals are 95% bootstrap ranges.

### sst2

Movie sentences, positive or negative. 872 reviews (neg 428, pos 444).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.826 | 0.800 to 0.851 | 0.826 | 0.651 | 0.651 | 0.901 | 0.0943 | 0.174 |
| roberta | 0.858 | 0.834 to 0.880 | 0.858 | 0.720 | 0.716 | 0.929 | 0.0743 | 0.142 |
| nlptown | 0.807 | 0.780 to 0.834 | 0.807 | 0.617 | 0.614 | 0.902 | 0.0517 | 0.193 |
| weighted ensemble | 0.881 | 0.860 to 0.901 | 0.881 | 0.761 | 0.761 | 0.948 | 0.0831 | 0.119 |
| learned stacker | 0.878 | 0.856 to 0.900 | 0.878 | 0.757 | 0.757 | 0.949 | 0.0220 | 0.122 |

### amazon_polarity

Product reviews, positive or negative. 1000 reviews (neg 500, pos 500).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.870 | 0.851 to 0.891 | 0.870 | 0.741 | 0.740 | 0.944 | 0.0733 | 0.130 |
| roberta | 0.906 | 0.888 to 0.924 | 0.906 | 0.813 | 0.812 | 0.966 | 0.0398 | 0.094 |
| nlptown | 0.933 | 0.918 to 0.949 | 0.933 | 0.866 | 0.866 | 0.982 | 0.0087 | 0.067 |
| weighted ensemble | 0.939 | 0.925 to 0.954 | 0.939 | 0.878 | 0.878 | 0.983 | 0.0654 | 0.061 |
| learned stacker | 0.942 | 0.927 to 0.957 | 0.942 | 0.884 | 0.884 | 0.984 | 0.0186 | 0.058 |

### imdb

Movie reviews, positive or negative. 1000 reviews (neg 500, pos 500).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.856 | 0.835 to 0.876 | 0.856 | 0.712 | 0.712 | 0.936 | 0.0686 | 0.144 |
| roberta | 0.841 | 0.818 to 0.864 | 0.841 | 0.682 | 0.682 | 0.922 | 0.0778 | 0.159 |
| nlptown | 0.864 | 0.842 to 0.885 | 0.864 | 0.729 | 0.728 | 0.945 | 0.0277 | 0.136 |
| weighted ensemble | 0.893 | 0.875 to 0.911 | 0.893 | 0.786 | 0.786 | 0.963 | 0.0670 | 0.107 |
| learned stacker | 0.898 | 0.881 to 0.915 | 0.898 | 0.797 | 0.796 | 0.962 | 0.0170 | 0.102 |

### amazon_reviews_en

Product reviews, 1 to 5 stars turned into negative, neutral, positive. 1000 reviews (neg 400, neu 200, pos 400).

| System | Accuracy | 95% range | Macro F1 | MCC | Kappa | ROC AUC | ECE | Opposite errors |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.686 | 0.656 to 0.715 | 0.643 | 0.515 | 0.514 | 0.836 | 0.0682 | 0.058 |
| roberta | 0.709 | 0.678 to 0.738 | 0.629 | 0.539 | 0.537 | 0.847 | 0.0840 | 0.053 |
| nlptown | 0.746 | 0.718 to 0.773 | 0.678 | 0.601 | 0.599 | 0.886 | 0.0556 | 0.026 |
| weighted ensemble | 0.751 | 0.724 to 0.777 | 0.684 | 0.608 | 0.606 | 0.885 | 0.0606 | 0.028 |
| learned stacker | 0.736 | 0.705 to 0.762 | 0.708 | 0.604 | 0.599 | 0.883 | 0.0264 | 0.020 |
