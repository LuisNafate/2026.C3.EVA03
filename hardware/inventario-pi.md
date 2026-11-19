# Inventario de la Raspberry Pi

Registro del 18 de noviembre de 2026. Consulta el [inventario con MAC retirada](../results/redacted/inventario-redactado.log). El log original se conserva en la laptop.

| Elemento | Registro | Evidencia |
| --- | --- | --- |
| Unidad evaluada | Una Raspberry Pi Zero 2 W Rev 1.0, anfitrión `edge-db` | Modelo de la placa leído por SSH |
| CPU | ARM Cortex-A53, 4 núcleos, 600–1,000 MHz, gobernador `ondemand` | `lscpu` y sysfs |
| Sistema | Raspberry Pi OS Lite de 64 bits, Debian 13.7 «Trixie», kernel `6.18.50+rpt-rpi-v8`, arquitectura `arm64` | Edición elegida por el usuario. Versión, kernel y arquitectura leídos en la Pi |
| RAM | 512 MB nominales. Linux reporta 425,116 KiB de memoria total utilizable | `free -k` y especificación de la placa |
| Swap | 424,956 KiB de swap total reportado. Se observó un dispositivo `zram0` de 415 MiB | `free -k` y `lsblk` |
| Almacenamiento | Una microSD de 64 GB nominales, `mmcblk0` de 57.8 GiB reportados, raíz ext4 | Capacidad nominal declarada. Capacidad y formato leídos en la Pi |
| Red y control | Interfaz `wlan0` activa. Inventario y recolección por SSH desde la laptop Windows | `ip` y conexión SSH verificada |
| Fuente y cable | Modelo, salida nominal y cable efectivo pendientes de confirmar físicamente | Pendiente. El estado eléctrico de la Pi se registró por separado |
| Montaje térmico | Sin disipador. Temperatura ambiente sin medir. Posición del montaje pendiente | Condición y falta de termómetro declaradas por el usuario |
| microSD física | ADATA 64 GB, UHS-I, Class 10, V10. Modelo comercial exacto pendiente | Características declaradas por el usuario |
| Consumo eléctrico | Sin medición | El usuario no dispone de medidor USB |

El cambio frente al playbook es el uso de una sola unidad física. Los resultados caracterizarán esta placa y esta microSD.

La llamada a `swapon --show` no estuvo disponible en el PATH de la sesión. El log conserva el aviso y los resultados de `free` y `lsblk`. La inspección posterior de `/proc/swaps` confirmó que la swap activa era `/dev/zram0`.
