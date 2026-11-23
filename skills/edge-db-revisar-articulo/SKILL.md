---
name: edge-db-revisar-articulo
description: Revisa el artículo de EDGE-DB con la rúbrica EVA03 y criterios de bases de datos, confrontando conclusiones sobre latencia, planes y recursos con su evidencia.
---

# Revisar el artículo de EDGE-DB

1. Lee [`reporte/articulo.tex`](../../reporte/articulo.tex), la [matriz consolidada](../../results/processed/extension-eva02/matriz_consolidada.csv) y los [incidentes](../../protocol/bitacora.md). Identifica la sección exploratoria, las tablas descriptivas y el diagnóstico. Cada nivel debe responder una pregunta distinta sobre los mismos datos.
2. En resultados, comprueba que la comparación incluya volumen, clientes, unidad, número de repeticiones y estadístico. Para un umbral de P95 informa la mediana y cuántas corridas cumplieron. Revisa también las celdas que contradicen la tendencia general.
3. En diagnóstico, relaciona cada operador con el plan, motor y sesión que lo registraron. Distingue tiempo de servidor de respuesta observada en la laptop. La observación de un ordenamiento externo en una sesión aporta contexto para el I/O observado en otra. Para atribuir escrituras a un motor se requieren contadores y eventos del mismo intervalo.
4. Evalúa las amenazas a la validez: una sola placa, recorridos de cliente diferentes, memoria de servicio distinta, corridas excluidas y mediciones ambientales ausentes. El resultado de un diagnóstico interrumpido se reporta con su límite y el registro que lo respalda.
5. Reconstruye el PDF y comprueba portada, índice, tablas, ejes, pies y anexos. Al cerrar, enlaza la fuente y el PDF y registra la intervención real en la [auditoría de IA](../../protocol/auditoria-ia.md).
