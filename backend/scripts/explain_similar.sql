-- Evidence for the report: nearest-neighbour search with and without the HNSW index.
-- Run:  Get-Content backend\scripts\explain_similar.sql | docker exec -i reviewiq_db psql -U reviewiq -d reviewiq
-- On a few hundred rows the planner prefers a sequential scan, so force the index for the "after" plan.

\echo === WITH HNSW INDEX ===
SET enable_seqscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT review_id FROM review_embedding
ORDER BY embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;

\echo === WITHOUT INDEX (sequential scan) ===
RESET enable_seqscan;
SET enable_indexscan = off;
EXPLAIN (ANALYZE, BUFFERS)
SELECT review_id FROM review_embedding
ORDER BY embedding <=> (SELECT embedding FROM review_embedding ORDER BY review_id LIMIT 1) LIMIT 5;
RESET enable_indexscan;
