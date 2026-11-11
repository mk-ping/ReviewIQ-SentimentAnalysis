INSERT INTO product (workspace_id, name)
SELECT 1, 'synthetic product ' || g FROM generate_series(1, 20) g
ON CONFLICT DO NOTHING;

INSERT INTO review (workspace_id, product_id, batch_id, text_clean, rating_norm, review_date, source, content_hash, language)
SELECT 1,
       (SELECT product_id FROM product WHERE workspace_id = 1 AND name = 'synthetic product ' || (1 + g % 20)),
       (SELECT min(batch_id) FROM upload_batch),
       'synthetic review ' || g,
       1 + floor(random() * 5),
       date '2025-01-01' + (random() * 600)::int,
       'synthetic',
       md5(g::text || random()::text),
       'en'
FROM generate_series(1, 50000) g;

ANALYZE review;

\echo ===== WITH index ix_review_ws_product_date =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*), avg(rating_norm) FROM review
WHERE workspace_id = 1
  AND product_id = (SELECT product_id FROM product WHERE workspace_id = 1 AND name = 'synthetic product 3')
  AND review_date BETWEEN '2025-06-01' AND '2025-08-31';

BEGIN;
DROP INDEX ix_review_ws_product_date;
\echo ===== WITHOUT the index =====
EXPLAIN (ANALYZE, BUFFERS)
SELECT count(*), avg(rating_norm) FROM review
WHERE workspace_id = 1
  AND product_id = (SELECT product_id FROM product WHERE workspace_id = 1 AND name = 'synthetic product 3')
  AND review_date BETWEEN '2025-06-01' AND '2025-08-31';
ROLLBACK;

DELETE FROM product WHERE workspace_id = 1 AND name LIKE 'synthetic product %';
