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
