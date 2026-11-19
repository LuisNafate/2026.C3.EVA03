# Decisiones y criterios EDGE-DB

## Alcance

Caso de estudio de una Raspberry Pi Zero 2 W. El protocolo original propone dos unidades. Se trabajó con una, sin disipador. Queda pendiente la confirmación docente de la desviación. El responsable declaró una microSD ADATA 64 GB UHS-I Class 10 V10 y ausencia de termómetro ambiental y medidor USB. No se estiman ambiente, potencia ni energía a partir de los sensores de la placa. Las series térmicas describen el SoC bajo este único montaje. La fuente y el cable exactos pendientes de confirmar limitan la interpretación eléctrica.

## Factibilidad por motor

| Motor | Método | Interpretación |
| --- | --- | --- |
| PostgreSQL 17.12 ARM64 | Instalación APT, consulta JSONB, cargas aisladas, oráculo independiente y verificación de persistencia | Factibilidad en el equipo observado. Consultar los logs para el alcance verificado |
| MongoDB Community 8.0 ARM64 | Contraste de requisitos oficiales de instrucciones con el Cortex-A53 identificado en el inventario | Incompatible con los binarios oficiales especificados. Sin instalación ni medición en esta placa |

[MongoDB exige ARMv8.2-A o posterior en ARM64](https://www.mongodb.com/docs/v8.0/administration/production-notes/#arm64). [Arm documenta el Cortex-A53 como Armv8-A](https://documentation-service.arm.com/static/6040c321ee937942ba301626). [Raspberry Pi identifica el SoC y la RAM de la Zero 2 W](https://www.raspberrypi.com/documentation/computers/zero.html). La conclusión se limita a la versión y distribución oficiales elegidas. Los pipelines se validaron en una [compilación comunitaria 7.0.40](mongodb-armv8-experimental.md) en una sesión posterior sin medir rendimiento.

## Contrato de medición

- Q1 devuelve país, categoría, suma, promedio y conteo de artículos de precio mayor a 50. Suma y promedio se normalizan a dos decimales. Q2 devuelve hasta 1,000 pares de identificador y total, ordenados por total descendente y, ante empate, identificador ascendente. Las fechas se tratan como días ISO en un intervalo semiabierto. El generador produce campos requeridos completos, cantidades enteras y precios en unidades monetarias con dos decimales de precisión.
- La laptop prepara los datos, agenda toda la carga y guarda resultados. En la Pi, cada cliente usa un proceso persistente `psql` por un canal SSH y PostgreSQL usa su socket local. La latencia incluye ida, consulta y vuelta de todas las filas. La validación de salida en Python ocurre después de detener el reloj de cada operación. Las operaciones que cruzan el cierre de ventana quedan en el CSV con su marca. El throughput cuenta solo operaciones completas, válidas y dentro de la ventana.
- La captura usa un canal adicional, con muestreo cercano a 1 Hz. CPU es global, la RAM disponible es `MemAvailable`, y el RSS es la suma de los procesos llamados `postgres` y puede contar memoria compartida más de una vez. Las diferencias de sectores de 512 bytes se estiman entre primera y última muestra dentro de la ventana. Una muestra de CPU representa el intervalo previo. Memoria y temperatura son extremos observados a la cadencia usada, no picos continuos. El costo del monitor no se cuantificó. El widget gráfico quedó fuera de la instrumentación.
- Un piloto de 1,000 pedidos, Q1/Q2, tres repeticiones y un cliente precede a la matriz. Se registra el plan final antes de ejecutarla. Se escala por volumen con un cliente y se examina la concurrencia en 10,000 pedidos con 1, 2 y 5 clientes. Se intenta completar cinco repeticiones por celda y se cambia el orden Q1/Q2 de forma reproducible dentro de cada repetición. Es un estudio de caché caliente. El orden progresivo, la corta espera entre corridas y la falta de control ambiental pueden influir en los efectos temporales.
- Parada preventiva si el SoC llega a 70 °C, la RAM disponible cae por debajo de 64 MiB, hay flags activos de alimentación/limitación, error de consulta/validación o pérdida de telemetría. Se revisan el ID de arranque y los mensajes del kernel. Energía, registros de OOM y reinicio solo se describen según evidencia disponible.
- P50/P95/P99 por rango más cercano sobre operaciones completas. Con menos de 100 operaciones por corrida, P99 se interpreta con cautela. Las repeticiones de una misma placa no equivalen a réplicas de hardware.

## Enmienda durante la ejecución

El intento inicial `final-50000-q1-c1-r2` devolvió una operación válida de 3,481 ms fuera de la ventana de 5 s, con cinco muestras de telemetría. Se registró como fallido bajo esa definición de completitud. El calentamiento podía cruzar el inicio y consumir parte de la ventana. La continuación empieza a medir tras una barrera común al completar el calentamiento, conserva 5 s en Q2 y eleva a 20 s la ventana de Q1 a 50,000 pedidos. Se rehacen ambas celdas de 50,000 pedidos con cinco repeticiones cada una, se retoman c2/c5 y quedan rastreables todos los intentos. No se mezclan repeticiones del plan inicial y enmendado en la misma celda.

## Alcance eléctrico en la Zero 2 W

La máscara registrada conserva estados del firmware. En la familia Zero no debe interpretarse como prueba de ausencia de caídas en la entrada de 5 V. El [plan de trabajo](plan-de-trabajo.md) describe la comprobación interna posterior y la evidencia aún pendiente.
