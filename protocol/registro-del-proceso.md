# Registro del proceso de EDGE-DB

## Agente y modelos de IA

La [auditoría por sesión](auditoria-ia.md) documenta un agente principal de Codex y registra GPT-6.2 en las fases de desarrollo y experimentación en las que se anotó ese identificador. En las intervenciones posteriores donde solo consta Codex se conserva ese nivel de detalle. El registro indica la tarea, el artefacto y la comprobación realizada.

## Reglas, habilidades y prompts

| Elemento | Evidencia |
| --- | --- |
| Reglas del proyecto | [AGENTS.md](../AGENTS.md) y [decisiones del benchmark](diseno-y-decisiones.md) |
| Habilidades utilizadas | La [auditoría](auditoria-ia.md) registra cuándo se usaron las habilidades de reporte científico, PDF, documentación técnica y commits convencionales |
| Habilidades específicas de EDGE-DB | [Reanudar sesiones](../skills/edge-db-reanudar-benchmark/SKILL.md), [auditar mediciones](../skills/edge-db-auditar-mediciones/SKILL.md) y [revisar el artículo](../skills/edge-db-revisar-articulo/SKILL.md). Formalizadas después del experimento a partir de los procedimientos documentados |
| Prompts versionados | [Maestro](prompts/maestro-edge-db.md), [auditoría de una afirmación](prompts/auditoria-resultados.md) y [revisión de entrega](prompts/revision-publicacion.md). La versión inicial del maestro está en el commit `fa28bed` |

## Herramientas y salidas

| Operación | Herramientas | Evidencia |
| --- | --- | --- |
| Inventario y captura | PowerShell, OpenSSH, Paramiko y telemetría del proyecto | [Inventario redactado](../results/redacted/inventario-redactado.log) y [recolector](../telemetry/preparar_pi.py) |
| Ejecución y validación | PostgreSQL 17.12 mediante `psql`, MongoDB comunitario 7.0.40 mediante PyMongo, Python para el oráculo | [Consultas](../workloads/) y [runners](../runner/) |
| Análisis | Python, resumen por celda y verificación desde CSV por operación | [Crudos de la ampliación](../results/raw/) y [matriz consolidada](../results/processed/benchmark-extendido/matriz_consolidada.csv) |
| Edición y comprobación | LaTeX, Tectonic, Poppler y pypdf | [Fuente](../reporte/articulo.tex), [PDF](../reporte/articulo.pdf) y [reconstrucción](../reporte/reconstruir.ps1) |

## Procedencia y trazabilidad

- Un ensayo previo del mismo autor en Docker Desktop orientó el método. El [protocolo ampliado](protocolo-ampliado.md) documenta la adaptación a la Pi.
- Los pedidos se regeneran a partir del [generador y su semilla](../dataset/generar.py). El [manifiesto](../dataset/generado-v1/manifiesto.json) registra los hashes de cada prefijo. Los tiempos proceden de los registros de la placa y del cliente. Las sesiones preservan los intentos excluidos y sus reintentos.
- La [prueba comunitaria](mongodb-armv8-experimental.md) acredita la procedencia del binario externo y de su biblioteca de compatibilidad. El repo conserva el código del experimento, los controles y los resultados de esa integración.
- El historial de Git documenta la evolución del proyecto.
