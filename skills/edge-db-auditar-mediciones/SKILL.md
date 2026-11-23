---
name: edge-db-auditar-mediciones
description: Reconcilia el manifiesto, los intentos y las operaciones válidas de EDGE-DB con sus CSV derivados. Úsala antes de publicar cifras o para rastrear discrepancias entre el reporte y los datos.
---

# Auditar las mediciones de EDGE-DB

1. Localiza la serie, el motor, el volumen, la consulta y la concurrencia que respaldan la cifra. Para la ampliación, el archivo de entrada es `corridas.csv` dentro de cada sesión y cada fila apunta a un CSV por operación con el mismo `run_id`. Usa la carpeta de sesión para distinguir un intento de su reintento.
2. Comprueba el manifiesto de los cinco prefijos de [`dataset/generado-v1/`](../../dataset/generado-v1/manifiesto.json). Contrasta las salidas con [`expected()`](../../runner/experimento.py) para revisar la suma, el promedio y el conteo de Q1 o el orden y desempate de Q2.
3. Reconstruye con [`reconstruir.ps1`](../../reporte/reconstruir.ps1), que invoca los analizadores de ambas series. En la ampliación, verifica cinco corridas válidas por celda, la deduplicación del `run_id` por motor y el cotejo de latencias, operaciones y QPS desde los CSV por operación. Conserva los intentos fuera de la selección.
4. Si comparas medianas por motor, mantén fija una condición completa. Los cuartiles de P95 resumen dispersión entre corridas. Para P99, revisa la columna de repeticiones con menos de 100 operaciones. En escritura por consulta, divide dentro de cada ventana antes de resumir los cocientes. El numerador es actividad de toda la microSD.
5. Entrega un registro con la afirmación, la celda, el valor recalculado y la ruta de evidencia. Si un dato falta o discrepa, conserva la diferencia y localiza el origen antes de cambiar el artículo.
