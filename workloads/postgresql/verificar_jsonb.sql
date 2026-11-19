BEGIN READ ONLY;

SELECT 'motor=' || current_setting('server_version');

WITH muestra(payload) AS (
    VALUES ('{"items":[{"qty":1,"price":20},{"qty":2,"price":65}]}'::jsonb)
), articulos AS (
    SELECT (item->>'qty')::integer AS qty, (item->>'price')::numeric AS price
    FROM muestra
    CROSS JOIN LATERAL jsonb_array_elements(payload->'items') AS item
)
SELECT concat('jsonb=', count(*), '|', count(*) FILTER (WHERE price > 50),
              '|', sum(qty * price) FILTER (WHERE price > 50))
FROM articulos;

COMMIT;
