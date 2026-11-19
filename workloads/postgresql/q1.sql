SELECT payload #>> '{customer,country}' AS country,
       item->>'category' AS category,
       round(sum((item->>'qty')::integer * (item->>'price')::numeric), 2) AS sum_subtotal,
       round(avg((item->>'qty')::integer * (item->>'price')::numeric), 2) AS avg_subtotal,
       count(*) AS items
FROM __TABLE__
CROSS JOIN LATERAL jsonb_array_elements(payload->'items') AS item
WHERE (item->>'price')::numeric > 50
GROUP BY country, category
ORDER BY 1, 2;
