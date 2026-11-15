# ReviewIQ decisions

These follow the final pipeline document (Nov 14). The older model-swap notes are replaced.

## Models (CPU only, nothing needs an API key)
- We train one model: TF-IDF + Logistic Regression (single words and word pairs, min_df 3, 50,000 features, balanced classes),
  trained on public sources and saved as ml/out/tfidf_lr.joblib. Every other model is pretrained and downloaded once.
- English: TF-IDF, cardiffnlp/twitter-roberta-base-sentiment-latest, nlptown/bert-base-multilingual-uncased-sentiment.
- Spanish, French, German, Italian, Dutch: TF-IDF, nlptown, cardiffnlp/twitter-xlm-roberta-base-sentiment.
- Hindi, Hinglish, undetermined: TF-IDF, Twitter XLM-RoBERTa, multilingual DistilBERT.
  nlptown does not cover Hindi, so Hindi reviews never get a vote from it and the star gap shows as not available.
- Dropped: tabularisai as a core model, the fine-tuned GPU star model, and the rule that every model must agree before a
  mismatch is flagged.
- Route groups and per-group weights are designs validated by ablation on the gold set, not results.

## Ensemble and fusion
- Ensemble weight = validation macro F1 of each model in the route group. Groups with fewer than 100 validation reviews use equal weights.
  Uploads with fewer than 300 rated reviews use the stored default weights. With 200 or more gold labels, weights are recomputed against them.
- Text score = P(pos) - P(neg). Star score = (stars - 3) / 2. Confidence = highest ensemble probability; w = clip(confidence, 0.4, 0.9).
- Fused = w x text + (1 - w) x star; fused stars = 3 + 2 x fused.
- Mismatch: confidence >= 0.7 and abs(text - star) >= 0.7 (tuned on gold labels, see tune_thresholds). Star gap: nlptown expected stars minus actual; flag at abs >= 1.5.

## Aspects
- pysbd sentences (fragments under 2 words dropped); seven aspects with 6 seed phrases each (config/aspect_config.py).
- SBERT: all-MiniLM-L6-v2 for English, paraphrase-multilingual-MiniLM-L12-v2 for the rest. A sentence gets every aspect at cosine 0.35 or more;
  otherwise a keyword check on word starts; otherwise general. The LLM never replaces the SBERT tags.
- Sentence sentiment: RoBERTa for English, Twitter XLM-RoBERTa for other route groups.
- The aspect view smooths each cell with (n x cell mean + 10 x overall mean) / (n + 10).
- review_aspect is derived from sentence_aspect so Hidden Dissatisfaction and the issues keep one reading path.

## Issues
- Problem sentences: sentiment -0.25 or lower. An aspect needs 30 of them for per-aspect KMeans (k 2 to 4, silhouette picks k, clusters named by c-TF-IDF,
  rare complaints beyond mean + 2 std). Fewer than 30 gives one issue marked few sentences.
- English and non-English sentences are clustered separately because their vectors come from different models.

## Embeddings
- One vector per review with a model column; search compares only vectors from the same model. HNSW index on 384-number vectors.

## Reports
- reportlab for the PDF and openpyxl for Excel, so nothing needs a system library.
- Alerts: SPIKE_Z 2.5, SPIKE_MIN_WEEKS 4, SPIKE_MIN_COUNT 5 (core/thresholds.py): chosen defaults, tune on real data.

## Retired
- The GPU fine-tuning path. ml/reviewiq_train.py is kept only for its build and baseline commands (public-source data build for TF-IDF training and the held-out evaluation).

## Deviations from the final pipeline document
- Issue growth compares the later half of dated reviews with the earlier half (median split, smoothed), not the last 12 months, so small uploads still get a value. Revisit when a workspace spans more than a year.
- Issue discovery needs 2 reviews per issue (ISSUE_MIN_REVIEWS) at demo scale; raise to 5 on real data.
- The local LLM is qwen2.5:3b and is used only for issue claims in Listing vs Reality and the column-detection fallback, never for aspect tags.
- The aspect list is fixed (7 aspects, 6 seeds each); the per-business editable list is not built.
- Baseline retraining on a workspace's own data (2,000 rated reviews) is not built; the public-source baseline is used.
