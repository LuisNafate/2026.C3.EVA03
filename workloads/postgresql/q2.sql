SELECT order_id, round((payload #>> '{payment,final_total}')::numeric, 2) AS final_total
FROM __TABLE__
WHERE payload->>'status' = 'completed'
  AND (payload->>'timestamp')::date >= DATE '2025-03-01'
  AND (payload->>'timestamp')::date < DATE '2025-12-01'
ORDER BY final_total DESC, order_id ASC
LIMIT 1000;
