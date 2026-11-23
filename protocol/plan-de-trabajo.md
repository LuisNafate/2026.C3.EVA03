# Plan de trabajo · EDGE-DB

## Qué está cubierto

| Área | Estado | Evidencia |
| --- | --- | --- |
| Montaje | Verificado por SSH. Una Zero 2 W, microSD ADATA 64 GB UHS-I V10, sin disipador | [Inventario](../hardware/inventario-pi.md) |
| Factibilidad | PostgreSQL 17.12 y MongoDB comunitario 7.0.40 pasaron la prueba de inserción, consultas y persistencia. MongoDB oficial se evaluó documentalmente | [Decisiones](diseno-y-decisiones.md), [evidencia de MongoDB](mongodb-armv8-experimental.md) |
| Datos y consultas | Cinco prefijos reproducibles con SHA-256. Q1 y Q2 cotejadas contra un oráculo independiente | [Manifiesto](../dataset/generado-v1/manifiesto.json), [consultas](../workloads/) |
| Rendimiento | 6 corridas piloto, 70 finales utilizables, 4 intentos conservados del plan inicial de 50k | [Selección de corridas](../results/processed/benchmark/seleccion_corridas.csv) |
| Análisis y entrega | Exploratorio, descriptivo y diagnóstico. Artículo, evidencia y auditoría de IA en el repositorio privado | [Artículo](../reporte/articulo.pdf), [auditoría](auditoria-ia.md) |
| Comprobación eléctrica por software | Consulta de capacidades, voltaje interno del VC4 y señales de operación. Sesión separada de la matriz final | [Carpeta de evidencia](../results/raw/alimentacion-software/) |
| Voltaje de entrada, corriente y energía | Sin medición directa. El firmware no expone el canal de entrada de 5 V en esta placa | [Respuesta del firmware](../results/raw/alimentacion-software/capacidades.log) |

## Cómo se cubre la parte de software

Por SSH se registró la lista de comandos del firmware. La consulta `vcgencmd pmic_read_adc EXT5V_V` devolvió `Command not registered`. Se instrumentó el voltaje del VC4 con `vcgencmd measure_volts core`, junto con frecuencia del ARM, temperatura del SoC y máscara del firmware a aproximadamente 1 Hz.

El ensayo separa 25 s en reposo, 25 s de solicitudes Q1 a 10,000 pedidos con un cliente y 15 s de recuperación. La columna `input_5v_v` queda vacía. El voltaje del VC4 corresponde al riel interno que reporta el firmware. La familia Zero carece del circuito de aviso de bajo voltaje descrito para otros modelos, por lo que una máscara `0x0` no acredita que la entrada se mantuviera en 5 V. [Comandos del firmware](https://www.raspberrypi.com/documentation/computers/os.html#measure_volts-block) · [Advertencias de alimentación](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#power-supply-warnings)

El ensayo produjo 64 muestras y 49 operaciones Q1 válidas. Las medianas de VC4 fueron 1.2500 V en reposo, 1.2625 V en carga y 1.2500 V en recuperación. La máscara permaneció en `0x0`. [Resumen](../results/raw/alimentacion-software/resumen.json) · [Datos por muestra](../results/raw/alimentacion-software/telemetria.csv)

## Qué falta y en qué orden

| Siguiente paso | Tiempo activo | Criterio de cierre |
| --- | ---: | --- |
| Fotografiar o copiar la línea `Output` del cargador y describir el cable | 5 min | Fuente, voltaje nominal y cable contrastados con la etiqueta |
| Confirmar con el docente la única placa y el alcance de la parte eléctrica | 5–10 min, aparte de la espera | Aclarar si acepta el diagnóstico interno o requiere una lectura física de la entrada |
| Confirmar la admisibilidad de MongoDB comunitario | En la misma consulta | Decidir si la prueba funcional es suficiente o si hace falta una matriz cronometrada separada. El primer piloto debe verificar el recorte de Q2 con más de 1,000 pedidos elegibles |
| Revisar el artículo, autoría, referencias y auditoría de IA | 20–30 min | Lectura humana y cifras contrastadas con CSV y logs |
| Si exigen voltaje de entrada, conseguir prestado un medidor y anexar una sesión | 15–25 min con el instrumento disponible | Voltaje observado en reposo y carga, punto de medición, modelo del instrumento y CSV propio |

La revisión y el registro de la fuente pueden avanzar en paralelo a la respuesta del docente. El ensayo eléctrico complementario conserva la matriz ya medida. Con solo software, el valor real de los 5 V sigue sin determinarse.
