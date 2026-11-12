\echo ===== LIVE join (what the endpoint did before) =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT r.workspace_id, r.product_id, ra.aspect_id, count(*), count(*) FILTER (WHERE r.rating_norm >= 4)
FROM review_aspect ra JOIN review r ON r.review_id = ra.review_id
LEFT JOIN review_score s ON s.review_id = r.review_id
WHERE r.spam_score <= 0.6 AND r.rating_norm IS NOT NULL AND ra.sentiment <= -0.25 AND ra.confidence >= 0.6
  AND ra.evidence_span IS NOT NULL AND ra.evidence_span <> ''
  AND NOT (coalesce(s.mismatch_type, '') = 'overrated'
           AND NOT EXISTS (SELECT 1 FROM review_aspect p WHERE p.review_id = r.review_id AND p.sentiment >= -0.25))
GROUP BY r.workspace_id, r.product_id, ra.aspect_id;

\echo ===== MATERIALIZED VIEW read (what the endpoint does now) =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT a.name, sum(m.negative_n), sum(m.hidden_n)
FROM mv_hidden_dissatisfaction m JOIN aspect a ON a.aspect_id = m.aspect_id
WHERE m.workspace_id = 1 GROUP BY a.name;
