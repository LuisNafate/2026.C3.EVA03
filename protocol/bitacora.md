# Bitácora EDGE-DB

## 18 de noviembre de 2026 · Preparación

Alcance de la sesión: inventariar el montaje, registrar al menos diez minutos en reposo antes del motor e instalar PostgreSQL. Las cargas, los datasets y las consultas quedan para otra sesión.

- [Inventario del montaje](../hardware/inventario-pi.md)
- [Carpeta de evidencia cruda](../results/raw/sesion-2026-11-18/)
- [Recolector y procedimiento de instalación](../telemetry/preparar_pi.py)

### Método de reposo

La laptop ejecutó la captura con una sesión SSH y un shell de lectura en la Pi. Se tomó una muestra aproximadamente cada cinco segundos, sin ejecutar cargas. Se guarda la hora UTC de recepción de cada muestra y el tiempo transcurrido según el reloj monotónico de la laptop.

El porcentaje de CPU se calcula por diferencia de contadores entre muestras. Se trata la espera de I/O como inactividad y la primera fila carece de porcentaje por ser la referencia inicial. La RAM disponible proviene de `MemAvailable`. La temperatura corresponde al SoC y la frecuencia a `scaling_cur_freq` de CPU 0. Los sectores de microSD son contadores acumulados desde el arranque. La máscara de `vcgencmd get_throttled` conserva indicadores actuales e históricos según el firmware.

Esta es una línea base instrumentada del sistema previo a PostgreSQL. Para la comparación futura conviene conservar el mismo intervalo y documentar si además se usó el widget.

### Línea base observada

[CSV de la línea base](../results/raw/sesion-2026-11-18/linea_base.csv) y [salida original del recolector](../results/raw/sesion-2026-11-18/linea_base_recolector.log). Se obtuvieron **121 muestras en 602.208 segundos**, de 08:07:46 a 08:17:49 UTC. Hay 120 intervalos de CPU calculables.

| Métrica | Resultado del reposo |
| --- | --- |
| CPU global | 0.232 % promedio, 0.100–0.599 % |
| RAM disponible | 267.3 MiB de promedio, 260.1–269.2 MiB |
| Temperatura del SoC | 42.083 °C de promedio, 41.318–43.470 °C |
| Frecuencia reportada de CPU 0 | 600 y 1,000 MHz |
| Swap usado | 0 KiB en todas las muestras |
| Actividad microSD | 16 sectores leídos y 88 escritos durante la captura |
| Máscara de throttling | `0x0` en las 121 muestras |

### Instalación y cierre

La instalación se inició una vez completada la línea base. APT instaló PostgreSQL **17.12** (paquete Debian `17.12-0+deb13u1`, ARM64). La comprobación de paquetes y del clúster mostró `17/main` en línea por el puerto 5432. El registro de arranque muestra los sockets locales predeterminados. Se pospusieron las consultas SQL y las cargas.

La conexión SSH se cortó durante el desempaquetado de `libllvm19`. La salida transmitida conserva el corte. Tras reconectar, la auditoría de paquetes y el historial local de APT confirmaron que la instalación se completó en la Pi. La causa del corte quedó sin determinar.

- [Salida de apt update](../results/raw/sesion-2026-11-18/apt-update.log) y [salida de instalación hasta el corte](../results/raw/sesion-2026-11-18/apt-install.log)
- [Diagnóstico tras reconectar](../results/raw/sesion-2026-11-18/apt-interrupcion-diagnostico.log), [registro de incidencias consultadas](../results/raw/sesion-2026-11-18/kernel-incidencias.log) e [historial final de APT](../results/raw/sesion-2026-11-18/apt-historial-postgresql.log)
- [Estado de PostgreSQL](../results/raw/sesion-2026-11-18/postgresql-estado.log), [arranque de PostgreSQL](../results/raw/sesion-2026-11-18/postgresql-arranque.log) y [registro de systemd](../results/raw/sesion-2026-11-18/postgresql-systemd.log)
- [Eventos y horas de la sesión](../results/raw/sesion-2026-11-18/eventos.log)

Los archivos quedaron guardados en la laptop. Al retomar, encender la Pi y conectarse por SSH para iniciar la validación funcional.

### Registro de IA

Codex (GPT-6.2) preparó el recolector, ejecutó el inventario y organizó la evidencia. Las mediciones y los mensajes de instalación provienen directamente de la Raspberry y se guardan con sus salidas crudas. La verificación física de los componentes queda pendiente.

## 18 de noviembre de 2026 · Reanudación y verificación inicial

- Codex (GPT-6.2) redactó el [prompt maestro](prompts/maestro-edge-db.md) a partir del playbook, la rúbrica, el inventario y los resultados de preparación. Usó las habilidades PDF y token-efficient-doc-creator para contrastar requisitos y estructurar el documento. Quedan pendientes la revisión humana y la confirmación docente de la desviación a una placa, si todavía no existe.
- Ejecutó el [SQL de verificación](../workloads/postgresql/verificar_jsonb.sql) en la Pi por SSH con Paramiko y `psql`. PostgreSQL 17.12 leyó la muestra JSONB en una transacción de solo lectura. El resultado coincide con el esperado: dos artículos, uno con precio mayor a 50 y un subtotal filtrado de 130. Se conserva el [log crudo](../results/raw/validacion-inicial-2026-11-18/postgresql-jsonb.log) y la [marca de ejecución](../results/raw/validacion-inicial-2026-11-18/eventos.log).
- La comprobación acredita la lectura de un arreglo JSONB y una agregación simple. Quedan pendientes la inserción y persistencia, la validación completa de Q1 y Q2, la línea base con el motor y las corridas de rendimiento.

## 18 de noviembre de 2026 · Ensayo y artículo

- El usuario declaró ADATA 64 GB UHS-I Class 10 V10, sin disipador, sin termómetro ambiental ni medidor de energía. La sesión nocturna del 18 cae el 19 en las marcas UTC de los logs.
- Se generaron y comprobaron por SHA-256 cinco prefijos. Las salidas de Q1 y Q2 para las cinco tablas coincidieron con el oráculo Python. Se verificó la persistencia después del reinicio del clúster.
- El [ensayo inicial](../results/raw/benchmark-v1/) guarda 62 muestras de reposo con el motor, seis corridas piloto y el plan de ventanas. Se interrumpió al quedar fuera de ventana una consulta válida de Q1 a 50,000 pedidos. La [continuación](../results/raw/benchmark-v2/) documentó el cambio de protocolo e incluyó las celdas de concurrencia pendientes.
- Se conservaron 80 intentos en total. El análisis seleccionó 70 resultados finales, 6 de piloto y conservó 4 intentos de la variante supersedida, incluido el fallido. Las 2,750 operaciones finales válidas se verificaron nuevamente desde sus CSV individuales. La [selección](../results/processed/benchmark/seleccion_corridas.csv) y el [resumen de celdas](../results/processed/benchmark/resumen_celdas.csv) permiten rastrear el resultado.
- El [diagnóstico](../results/processed/benchmark/planes_normalizados.json) observó en Q1 a 50,000 pedidos ordenamiento externo y 3,532 bloques temporales escritos. Q2 usó top-N heapsort y escribió cero bloques temporales en su plan. El ID de arranque coincidió y durante la captura se registró máscara `0x0`.
- El [artículo](../report/articulo.tex) utiliza datos derivados generados por `results/analizar.py`. Las referencias primarias y los límites del estudio se consignan en el artículo. Se prepararon versiones redactadas de los dos logs de red para GitHub y se preservaron los originales localmente.

## 18 de noviembre de 2026 · Comprobación de alimentación

Codex (GPT-6.2) usó documentación oficial de Raspberry Pi y creó un [runner de diagnóstico](../runner/diagnostico_alimentacion.py) para verificar qué ofrece el firmware de esta Zero 2 W. El canal `EXT5V_V` devolvió `Command not registered`. El ensayo de reposo, carga Q1 y recuperación produjo 64 muestras y 49 consultas válidas. El [resumen](../results/raw/alimentacion-software/resumen.json) conserva los voltajes internos reportados por fase. Se corrigió la interpretación de la máscara `0x0` en el artículo y se registró el [plan de trabajo](plan-de-trabajo.md). La verificación humana del requisito eléctrico queda pendiente.

## 19 de noviembre de 2026 · MongoDB comunitario en ARMv8-A

Codex (GPT-6.2) verificó la fuente y los hashes, implementó la ejecución aislada por SSH y comparó las salidas con el oráculo del benchmark. Los [tres intentos](mongodb-armv8-experimental.md) conservan fallos del lanzador, ausencia de libcrypto.so.1.1 y la prueba exitosa. En la prueba funcional se insertaron 1,000 pedidos. El motor devolvió los 16 grupos de Q1 y los 598 pedidos de Q2 esperados antes y después del reinicio. Al terminar, se verificó el clúster PostgreSQL activo. Quedan pendientes la revisión humana, la aceptación de la variante por el docente y, si procede, un piloto de rendimiento separado.

## 19 de noviembre de 2026 · Ampliación a partir de EVA02

Se cotejaron aviso, playbook, EVA02 y evidencia de EVA03 en la [auditoría](extension-eva02.md). La conexión por llave del alias no autenticó. Se verificó la placa por contraseña y se instaló Paramiko en un entorno virtual local después de que el Python de la laptop no encontró la dependencia. A las 18:57 (Ciudad de México) se inició [A1](../results/raw/extension-eva02-postgresql-v1/) por SSH con verificación de versión, tamaños y reposo de 600 s. El [supervisor](../runner/continuar_extension.py) encadena el diagnóstico y MongoDB a su cierre. Los resultados cerrados se recomputan desde cada CSV de operaciones.

A las 19:12, A1 terminó con seis pilotos válidos y una corrida larga interrumpida por telemetría. El supervisor avanzó a MongoDB a las 19:14. La sesión MongoDB confirmó el montaje del directorio de datos sobre la microSD. Se programó reanudar A1 después del cierre de MongoDB, conservando los pilotos y verificando la cobertura de telemetría en las ventanas nuevas.

A las 23:36 (Ciudad de México) se pausó la cola por solicitud del usuario. La última corrida PostgreSQL válida fue Q1 a 10 000 pedidos, cinco clientes, repetición 5, con 472 operaciones validadas. El usuario podrá retomar a 25 000 pedidos con un cliente. Se conservaron 50 corridas finales válidas de PostgreSQL, 6 de MongoDB y los pilotos de ambos motores. El enfriamiento de la última corrida no completó el protocolo. [Registro de pausa](../results/raw/extension-eva02-supervision-v5/pausa.log) · [Matriz consolidada](../results/processed/extension-eva02/matriz_consolidada.csv).

A las 23:38 se solicitó el apagado ordenado de `edge-db` por SSH. Antes del apagado se comprobó que PostgreSQL estaba en línea, que las cinco tablas de prueba conservaban sus recuentos esperados y que MongoDB no estaba activo. Se guardaron el identificador de arranque, temperatura de 47.8 °C, máscara `0x0`, memoria y almacenamiento. Después de aceptar la orden, SSH quedó inaccesible en tres comprobaciones consecutivas. [Evidencia de cierre](../results/raw/extension-eva02-cierre-v1/).

## 21 de noviembre de 2026 · Reanudación

Se retomó PostgreSQL a 25 000 pedidos con un cliente. La sesión V04 conservó nueve corridas válidas y se detuvo por pérdida de telemetría durante el enfriamiento. El supervisor recuperó las once corridas pendientes en V05 y cerró la matriz de PostgreSQL con 70 repeticiones válidas. A continuación inició MongoDB, conservando sus seis corridas válidas previas. [V04](../results/raw/extension-eva02-postgresql-v04/) · [V05](../results/raw/extension-eva02-postgresql-v05/).
