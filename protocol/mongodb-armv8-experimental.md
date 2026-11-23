# MongoDB comunitario para la Zero 2 W

## Pregunta y alcance

¿Puede un binario comunitario de MongoDB arrancar en nuestra Zero 2 W, conservar 1,000 pedidos tras reiniciar y producir las mismas salidas de Q1 y Q2 que el oráculo de EDGE-DB?

Se evalúa la [compilación de themattman r7.0.40](https://github.com/themattman/mongodb-raspberrypi-binaries/releases/tag/r7.0.40-rpi-unofficial), construida para Cortex-A72. Nuestra aportación es el entorno de ejecución de recursos limitados, el aislamiento y el protocolo de verificación con datos reproducibles. La compilación y el motor tienen procedencia externa. Los binarios oficiales [requieren ARMv8.2-A](https://www.mongodb.com/docs/v7.0/administration/production-notes/#arm64). Arm documenta el Cortex-A53 como [Armv8-A](https://documentation-service.arm.com/static/6040c321ee937942ba301626). WiredTiger ha documentado [riesgos de corrección en CPU ARM sin atómicas LSE](https://jira.mongodb.org/browse/WT-9256). Una prueba breve de reinicio y consultas no cubre concurrencia sostenida, integridad frente a fallas ni uso en producción.

## Qué verifica el runner

1. Confirma el SHA-256 del archivo en ambas computadoras y registra los hashes de los ejecutables extraídos.
2. Intenta `mongod --version` dentro de una unidad temporal, con usuario dinámico, red privada y directorios personales y de PostgreSQL aislados.
3. Si se pudo ejecutar la versión, verifica que no haya clientes de PostgreSQL. Pone el clúster en pausa durante la prueba y lo devuelve a su estado anterior al salir.
4. Usa una base desechable en el directorio de la unidad, loopback privado, límite de 320 MiB de RAM y 128 MiB de swap y caché WiredTiger de 0.25 GB.
5. Inserta el prefijo original de 1,000 pedidos verificado por hash, normaliza importes a Decimal128 y ejecuta Q1/Q2 antes y después de un reinicio limpio de MongoDB. Coteja ambas salidas en la laptop con el oráculo Python.

## Reproducción

Descarga `mongodb.ce.pi4.r7.0.40.tar.gz` del enlace de origen y [libssl1.1 ARM64 1.1.1w-0+deb11u8 del archivo de Debian](https://archive.debian.org/debian-security/pool/updates/main/o/openssl/libssl1.1_1.1.1w-0+deb11u8_arm64.deb). El runner verifica el SHA-256 de ambos. El paquete Debian solo se extrae dentro del directorio temporal. El cargador del servicio aislado busca ahí las bibliotecas. Los binarios permanecen fuera de Git. Usa una ventana en la que PostgreSQL no tenga clientes.

```powershell
python runner/probar_mongo_arm.py --host IP_DE_LA_PI --user USUARIO --archive RUTA_AL_ARCHIVO --compat RUTA_A_LIBSSL_DEB --dataset dataset/generado-v1/orders-1000.jsonl --raw results/raw/nuevo-ensayo-mongo
```

En cada intento se conservan información de la plataforma, transferencia, prueba de versión, salida del servidor/cliente cuando se genera, comparación con el oráculo y estado posterior. Esta página documenta la factibilidad. La [matriz cronometrada de ambos motores](../results/processed/benchmark-extendido/matriz_consolidada.csv) corresponde a la ampliación posterior.

## Resultados comprobados

| Intento | Observación |
| --- | --- |
| [v1](../results/raw/mongo-arm-v1/) | El lanzador no encontró la ruta de ejecución antes del montaje de la unidad. El binario no llegó a ejecutarse. |
| [v2](../results/raw/mongo-arm-v2/) | El binario llegó al cargador dinámico. Faltaba libcrypto.so.1.1 y salió con código 127. |
| [v3](../results/raw/mongo-arm-v3/) | Con libssl1.1 extraída en la unidad, mongod 7.0.40 arrancó en la Pi. Q1 devolvió 16 grupos y Q2 598 pedidos. Las salidas coincidieron con el oráculo antes y después del reinicio. PostgreSQL se verificó activo al terminar. |

La muestra inicial valida el filtro y la ordenación de Q2. El [piloto posterior a 5,000 pedidos](../results/raw/benchmark-extendido-mongodb-v1/validacion.json) verificó el recorte a 1,000 de 3,004 pedidos elegibles.
