# Auditoría de IA

| Sesión | Agente/modelo | Intervención | Evidencia o verificación | Revisión humana |
| --- | --- | --- | --- | --- |
| Preparación, 18 nov 2026 | Codex (GPT-6.2) | Ayuda con acceso, monitor gráfico, inventario, línea base y preparación de PostgreSQL | Logs en `results/raw/sesion-2026-11-18/` y bitácora | Pendiente de revisión formal |
| Diseño, 18 nov 2026 | Codex (GPT-6.2) | Contrastó rúbrica y playbook y propuso el prompt maestro | Prompt conservado, resultado de JSONB comprobado en la Pi | El usuario reutilizó el prompt y solicitó ejecutar el proyecto |
| Ejecución y artículo, 18 nov 2026 | Codex (GPT-6.2) | Escribió código, diseñó controles, ejecutó, analizó y redactó | Hashes, oráculo Python, logs de la Pi, CSV, script de análisis y fuente LaTeX. Registra el resultado del cierre en la bitácora | El usuario declaró el montaje. Pendiente revisión del artículo y de la desviación ante el docente |
| MongoDB comunitario, 19 nov 2026 | Codex (GPT-6.2) | Preparó y ejecutó una prueba aislada con binarios de terceros y biblioteca de Debian verificada | Hashes, logs de tres intentos y oráculo Python. Se verificó que PostgreSQL volviera a estar activo | Pendiente aceptación docente de la variante y revisión del anexo |

Se utilizó un agente principal. Herramientas efectivas: PowerShell y OpenSSH para diagnóstico, Python y Paramiko para datos y SSH, PostgreSQL/`psql` para consultas, búsqueda de documentación primaria, Tectonic y Poppler para edición y comprobación visual. Habilidades del flujo editorial: PDF y token-efficient-doc-creator. El directorio de prompts conserva el prompt de investigación.

Reglas de auditoría: localizar cada número en evidencia primaria o en el script que lo calcula, conservar intentos y límites, comprobar las fuentes y verificar el montaje físico antes de la entrega. La IA generó el código y asistió en la interpretación. Los datos sintéticos de entrada están identificados. Las mediciones y logs del motor proceden del ensayo real. No guardar contraseñas, tokens ni claves privadas. Antes de compartir, preparar una copia pública de los logs que reduzca identificadores de la red doméstica y conservar los originales como respaldo privado.
