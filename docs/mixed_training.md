# Mixed-genre training results (cross-validated, rows the models never trained on)

Result: **applied** - beats the weighted average across genres without hurting reviews.

Overall macro F1: weighted average 0.729, stacker 0.743. Accuracy 0.751 to 0.755.

| Source | Rows | Weighted avg acc | Stacker acc | Weighted avg F1 | Stacker F1 | Stacker without text clues F1 |
|---|---|---|---|---|---|---|
| amazon_polarity | 700 | 0.924 | 0.924 | 0.942 | 0.943 | 0.932 |
| financial_news | 700 | 0.657 | 0.707 | 0.574 | 0.573 | 0.548 |
| reviews | 1400 | 0.748 | 0.742 | 0.671 | 0.683 | 0.667 |
| sst2 | 700 | 0.770 | 0.774 | 0.833 | 0.837 | 0.818 |
| sst5 | 700 | 0.727 | 0.716 | 0.663 | 0.642 | 0.649 |
| tweet_eval | 700 | 0.737 | 0.711 | 0.730 | 0.687 | 0.727 |
| tweet_sentiment | 700 | 0.693 | 0.721 | 0.681 | 0.722 | 0.722 |
