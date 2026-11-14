
# ReviewIQ decisions

## Models (CPU only, all pretrained)
- Core 1: tabularisai/multilingual-sentiment-analysis (5-class, every language, cc-by-nc-4.0, fine for coursework).
- Core 2: nlptown/bert-base-multilingual-uncased-sentiment (1-5 stars, MIT). Routed by detected language to en, es, fr, de, it, nl only.
  Hindi, Hinglish and undetermined text get no vote from it, because it was not trained on them.
- Optional: cardiffnlp/twitter-xlm-roberta-base-sentiment, enabled by setting cardiff_model.
- We train nothing. The GPU fine-tune (ml/reviewiq_train.py) is retired: it needed a GPU and was not reproducible on a laptop.
- Each model is measured on the hand-labelled gold set and kept only if it beats stars alone and the TF-IDF baseline.

## Fusion
Text score = P(pos) - P(neg). Star score = (stars - 3) / 2. Weight = clip(confidence, 0.4, 0.9).
Fused stars = 3 + 2 * (w * text + (1 - w) * star). Probabilities are averaged over the models that ran for that review.
A mismatch is flagged only when every model that ran agrees on the label.

## Alerts
SPIKE_Z 2.5, SPIKE_MIN_WEEKS 4, SPIKE_MIN_COUNT 5 (core/thresholds.py): chosen defaults, tune on real data.
