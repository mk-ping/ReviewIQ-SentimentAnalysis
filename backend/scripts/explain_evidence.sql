-- EXPLAIN ANALYZE evidence for the queries added in Steps 20-22. Run it with tools\make_evidence.ps1.
-- On small data the planner prefers sequential scans, so each "with index" plan forces the index.

ANALYZE sentence_aspect;
ANALYZE review_embedding;

\echo ===== SIMILAR REVIEWS, same model only, WITH HNSW INDEX =====
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.review_id FROM review_embedding e
WHERE e.model = (SELECT model FROM review_embedding ORDER BY review_id LIMIT 1)
ORDER BY e.embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;
RESET enable_seqscan;

\echo ===== SIMILAR REVIEWS, same model only, WITHOUT INDEX =====
SET enable_indexscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT e.review_id FROM review_embedding e
WHERE e.model = (SELECT model FROM review_embedding ORDER BY review_id LIMIT 1)
ORDER BY e.embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;
RESET enable_indexscan;

\echo ===== SENTENCES FOR ONE ASPECT, WITH ix_sentence_aspect_aspect =====
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT sentence, sent_score FROM sentence_aspect WHERE aspect = 'delivery' AND sent_score <= -0.25 LIMIT 20;
RESET enable_seqscan;

\echo ===== SENTENCES FOR ONE ASPECT, WITHOUT INDEX =====
SET enable_indexscan = off; SET enable_bitmapscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT sentence, sent_score FROM sentence_aspect WHERE aspect = 'delivery' AND sent_score <= -0.25 LIMIT 20;
RESET enable_indexscan; RESET enable_bitmapscan;

\echo ===== ASPECT COVERAGE (tagged vs general sentences) =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*) FILTER (WHERE aspect <> 'general') AS tagged, count(*) AS total FROM sentence_aspect;
