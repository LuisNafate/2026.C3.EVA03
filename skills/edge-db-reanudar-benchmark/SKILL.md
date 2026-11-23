---
name: edge-db-reanudar-benchmark
description: Reanuda una matriz EDGE-DB interrumpida en una Raspberry Pi conservando corridas aceptadas, controles térmicos y estado de los servicios. Úsala para ejecutar o recuperar sesiones, con autorización sobre la placa.
---

# Reanudar una sesión EDGE-DB

1. Identifica si la sesión pertenece a la serie inicial o a la ampliación. Lee [las decisiones](../../protocol/diseno-y-decisiones.md), [el protocolo de ampliación](../../protocol/protocolo-ampliado.md) y los `estado.json` del supervisor y de la sesión. Si un supervisor sigue activo, inspecciona su estado antes de iniciar otro.
2. Verifica por SSH la identidad de la placa, el estado de los motores y el almacenamiento disponible. Ante un corte durante MongoDB, comprueba si queda la unidad experimental antes de iniciar PostgreSQL. Consulta la recuperación documentada en la [bitácora](../../protocol/bitacora.md) y el procedimiento de [aislamiento](../../protocol/mongodb-armv8-experimental.md).
3. Reutiliza [`continuar.py`](../../runner/continuar.py) para la enmienda inicial o [`continuar_extension.py`](../../runner/continuar_extension.py) para la ampliación. Cada reintento escribe en un directorio nuevo. Mantén los identificadores lógicos para que el análisis pueda elegir cada repetición válida una sola vez.
4. Verifica que cada corrida conserve el hash del conjunto, la salida cotejada con el oráculo, el control de telemetría y el estado de enfriamiento al cierre. Si cambian la ventana, el transporte o la configuración, registra la desviación antes de comparar con otra serie.
5. Antes de cerrar, comprueba el estado real del servicio y del supervisor. Registra la última corrida válida, la siguiente celda, los incidentes y sus rutas en la bitácora. Un supervisor cerrado con estado parcial requiere revisar los bloques pendientes individualmente.
