
# ReviewIQ changelog

Dates are 2026. Each line is one step of the build; the git log has the detail.

## 15 Nov
- Final pipeline document applied: cleaning and spam rules (spam line 0.7), route groups, RoBERTa / nlptown / Twitter XLM-R models,
  weighted ensemble from validation macro F1, TF-IDF baseline trained by us, original confidence-based mismatch rule.
- Sentence-level aspects (pysbd, SBERT seed phrases, keyword fallback); per-aspect KMeans issues with silhouette and c-TF-IDF;
  embeddings per language with a model column.
- Upload reviews buttons, Sentiment page, per-upload results and CSV download.
- Ensemble weights recomputed from 200+ gold labels (scripts/recompute_weights).
- Step 17: serious-complaint list (safety, allergy, fraud, legal), reply queue with template drafts, Reports page.
- Docker: tesseract in the image, TF-IDF file mounted, API health check, worker waits for the migrated API.
- Requirements pinned (tools/pin_requirements.ps1); all checks runnable with tools/run_checks.ps1.

## 14 Nov
- One-flow upload page and /uploads/{id}/results; PDF and Excel export; PDF and XML upload; aspect labelling export.
- Docker full stack (api, worker, web) with CPU PyTorch and an nginx proxy.

## 13 Nov
- Completion pass: PDF, OCR and XML readers, tie-breaker, LLM column fallback, fixtures, fuzz tests.
- pgvector review_embedding with HNSW, embed stage, similar-review search, audit_log with triggers.
- Gold labels and evaluation (macro F1, bootstrap range, confusion matrix, calibration).

## 12 Nov
- Worker queue (SKIP LOCKED, SSE progress), pretrained sentiment scoring, fusion, star gap, mismatch flags, True Rating.
- Aspects, Hidden Dissatisfaction, issue discovery, priority, what-if, recommendations, action tracker.
- Materialized views (mv_product_daily, mv_hidden_dissatisfaction), trends and spike alerts.
- React app: Home, Rating vs Text, Problems, Aspects, Explorer, Upload, Trends, Products and Competitors.

## 11 Nov
- Schema and Alembic migrations, file intake and type detection, readers, column detection, value parsing, cleaning and ingest,
  language routing.

## Known limits
- Thresholds are starting values until tuned on the gold set. Aspect tags are not yet hand-checked.
- Hinglish has no labelled data of its own. nlptown does not cover Hindi.
