# Prompt maestro · EDGE-DB

Trabaja sobre EDGE-DB, un estudio de agregaciones documentales en una Raspberry Pi Zero 2 W. La pregunta es cómo cambian latencia de cola, rendimiento y recursos al escalar Q1 y Q2 en las configuraciones documentadas de PostgreSQL JSONB y MongoDB comunitario. La audiencia son desarrolladores interesados en bases de datos y computación de borde. Presenta resultados en español con unidades, condiciones y evidencia de respaldo.

## Entrada y alcance

- Lee el [inventario](../../hardware/inventario-pi.md), el [diseño](../diseno-y-decisiones.md) y la [bitácora](../bitacora.md). Usa la bitácora y los estados de sesión para determinar qué fase está cerrada.
- Mantén trazables las desviaciones entre lo propuesto y lo ejecutado. El montaje documentado usa una placa sin disipador. La temperatura ambiente y la energía carecen de medición directa.
- Reutiliza los scripts del repositorio. Conserva el código original del proyecto, acredita las dependencias y registra las decisiones que afecten la comparabilidad.

## Selección del trabajo

| Si el encargo pide | Procedimiento | Evidencia de cierre |
| --- | --- | --- |
| Ejecutar o reanudar una sesión autorizada | [Reanudar el benchmark](../../skills/edge-db-reanudar-benchmark/SKILL.md) | Estado de la Pi y servicios, sesión, corridas incorporadas, exclusiones y siguiente celda |
| Verificar una cifra o reconstruir el análisis | [Auditar las mediciones](../../skills/edge-db-auditar-mediciones/SKILL.md) | Valores calculados, celdas comparables y rutas a los CSV |
| Editar o evaluar el informe técnico | [Revisar el artículo](../../skills/edge-db-revisar-articulo/SKILL.md) | LaTeX y PDF en [reporte](../../reporte/), figuras cotejadas y alcance de las conclusiones |

## Criterios de revisión

- Para una afirmación cuantitativa indica motor, tamaño, consulta, concurrencia, estadístico y denominador. Usa el CSV por operación cuando se necesite verificar el valor.
- En el análisis **exploratorio**, reconstruye cobertura, intentos y exclusiones. En el **descriptivo**, explica el patrón con unidades y dispersión. En el **diagnóstico**, vincula una explicación a una medición o plan de la sesión correspondiente y delimita qué queda como hipótesis.
- Registra en la [auditoría de IA](../auditoria-ia.md) el agente o herramienta, el identificador de modelo confirmado, la intervención, el artefacto y la verificación. Indica cuando el identificador exacto no conste.

## Respuesta de cierre

Resume el resultado, la ruta de su evidencia y cualquier limitación que afecte su interpretación. Entrega solo los artefactos correspondientes al encargo. Si la matriz está cerrada, comienza por los datos guardados y los scripts de reconstrucción.

El prompt de la fase inicial se conserva en el historial de Git, en el commit `fa28bed`. Esta revisión organiza el trabajo posterior y la publicación del estudio.
