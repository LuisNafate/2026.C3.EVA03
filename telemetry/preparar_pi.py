"""Captura el montaje y la línea base, e instala PostgreSQL después."""

import argparse
import csv
from datetime import datetime, timezone
from getpass import GetPassWarning, getpass
from pathlib import Path
from time import monotonic
import warnings

import paramiko


INVENTORY = r"""
export LC_ALL=C
echo '== Identidad y plataforma =='
date -u '+%Y-%m-%dT%H:%M:%SZ'
hostname
tr -d '\000' < /proc/device-tree/model
echo
uname -srmo
cat /etc/os-release
dpkg --print-architecture
lscpu
echo '== Memoria y swap =='
free -k
swapon --show
echo '== Almacenamiento =='
lsblk -o NAME,TYPE,SIZE,MODEL,FSTYPE,MOUNTPOINTS
df -h /
for field in manfid oemid name date; do
    path=/sys/block/mmcblk0/device/$field
    if [ -r "$path" ]; then printf '%s=' "$field"; cat "$path"; fi
done
echo '== Interfaz de red y tiempo encendido =='
ip -brief link show wlan0
uptime
echo '== Frecuencia, temperatura y alimentación =='
for field in scaling_governor scaling_min_freq scaling_max_freq; do
    path=/sys/devices/system/cpu/cpu0/cpufreq/$field
    if [ -r "$path" ]; then printf '%s=' "$field"; cat "$path"; fi
done
vcgencmd measure_temp
vcgencmd get_throttled
echo '== Bases de datos al inicio =='
dpkg-query -W -f='${binary:Package} ${Version} ${db:Status-Status}\n' 'postgresql*' 'mongodb*' 2>/dev/null || :
if pgrep -x postgres >/dev/null || pgrep -x mongod >/dev/null; then
    echo 'Hay un motor activo antes de la línea base.'
    exit 2
fi
echo 'Sin procesos postgres ni mongod.'
"""

SAMPLER = r"""
export LC_ALL=C
while :; do
    read -r label user nice system idle iowait irq softirq steal rest < /proc/stat || exit 1
    cpu_total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    cpu_idle=$((idle + iowait))
    mem_total=na
    mem_available=na
    swap_total=na
    swap_free=na
    while read -r key value unit; do
        case "$key" in
            MemTotal:) mem_total=$value ;;
            MemAvailable:) mem_available=$value ;;
            SwapTotal:) swap_total=$value ;;
            SwapFree:) swap_free=$value; break ;;
        esac
    done < /proc/meminfo
    temp=na
    freq=na
    read_sectors=na
    write_sectors=na
    if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        read -r temp < /sys/class/thermal/thermal_zone0/temp || temp=na
    fi
    if [ -r /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq ]; then
        read -r freq < /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq || freq=na
    fi
    if [ -r /sys/block/mmcblk0/stat ]; then
        read -r reads merges read_sectors read_ms writes wmerges write_sectors rest < /sys/block/mmcblk0/stat
    fi
    flags=$(vcgencmd get_throttled 2>/dev/null) || flags=na
    printf 'EDGE %s %s %s %s %s %s %s %s %s %s %s\n' \
        "$cpu_total" "$cpu_idle" "$mem_total" "$mem_available" "$swap_total" "$swap_free" \
        "$temp" "$freq" "$read_sectors" "$write_sectors" "${flags#throttled=}" || exit 0
    sleep 5
done
"""

FIELDS = (
    "timestamp_utc", "elapsed_s", "cpu_pct", "cpu_total_ticks", "cpu_idle_ticks",
    "ram_total_kib", "ram_available_kib", "swap_total_kib", "swap_free_kib",
    "soc_temp_c", "cpu0_scaling_khz", "mmc_read_sectors", "mmc_write_sectors",
    "throttled_mask",
)

VERIFY_INSTALL = r"""
set -e
dpkg-query -W -f='${binary:Package} ${Version} ${db:Status-Status}\n' postgresql 'postgresql-[0-9]*'
psql --version
pg_lsclusters
systemctl is-active postgresql
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(directory, message):
    print(message, flush=True)
    with (directory / "eventos.log").open("a", encoding="utf-8") as event_log:
        print(utc_now(), message, file=event_log)


def channel(client, command, timeout):
    stream = client.get_transport().open_session(timeout=10)
    stream.settimeout(timeout)
    stream.set_combine_stderr(True)
    stream.exec_command(command)
    return stream


def log_command(client, path, command, secret=None, timeout=120):
    with path.open("x", encoding="utf-8") as out, channel(client, command, timeout) as stream:
        if secret is not None:
            stream.sendall((secret + "\n").encode("utf-8"))
        stream.shutdown_write()
        for line in stream.makefile("r"):
            out.write(line)
            out.flush()
        code = stream.recv_exit_status()
        print(f"\nexit_status={code}", file=out)
        return code


def capture(client, directory, duration):
    start, previous = None, None
    samples, last_minute = 0, 0
    with (
        (directory / "linea_base.csv").open("x", encoding="utf-8", newline="") as csv_file,
        (directory / "linea_base_recolector.log").open("x", encoding="utf-8") as raw,
        channel(client, SAMPLER, 20) as stream,
    ):
        stream.shutdown_write()
        writer = csv.writer(csv_file)
        writer.writerow(FIELDS)
        for line in stream.makefile("r"):
            timestamp = utc_now()
            print(timestamp, line.rstrip(), file=raw, flush=True)
            values = line.split()
            if len(values) != 12 or values[0] != "EDGE":
                continue
            now = monotonic()
            if start is None:
                start = now
            elapsed = now - start
            total, idle = map(int, values[1:3])
            cpu_pct = None
            if previous is not None:
                delta, idle_delta = total - previous[0], idle - previous[1]
                if delta > 0 and 0 <= idle_delta <= delta:
                    cpu_pct = round(100 * (delta - idle_delta) / delta, 3)
            previous = total, idle
            temp = None if values[7] == "na" else int(values[7]) / 1000
            writer.writerow([
                timestamp, round(elapsed, 3), cpu_pct, total, idle, *values[3:7],
                temp, *values[8:12],
            ])
            csv_file.flush()
            samples += 1
            if int(elapsed // 60) > last_minute:
                last_minute = int(elapsed // 60)
                emit(directory, f"Línea base: {elapsed:.0f} s, {samples} muestras.")
            if elapsed >= duration:
                return samples, elapsed
    raise RuntimeError("La conexión terminó antes de completar la línea base.")


def prepare(args, password):
    directory = args.output
    directory.mkdir(parents=True, exist_ok=False)
    emit(directory, "Inicio de preparación. No se ejecutarán cargas ni consultas SQL.")
    try:
        with paramiko.SSHClient() as client:
            client.load_system_host_keys(str(Path.home() / ".ssh" / "known_hosts"))
            client.connect(
                args.host, username=args.user, password=password, look_for_keys=False,
                allow_agent=False, timeout=8, banner_timeout=8, auth_timeout=8,
            )
            if log_command(client, directory / "inventario.log", INVENTORY) != 0:
                raise RuntimeError("Inventario fallido o motor activo al inicio.")
            nopasswd = log_command(client, directory / "sudo_preflight.log", "sudo -n true") == 0
            emit(directory, "Inventario guardado. Inicia línea base previa a PostgreSQL.")
            samples, elapsed = capture(client, directory, 600)
            emit(directory, f"Línea base completa: {samples} muestras en {elapsed:.3f} s.")

            sudo = "sudo -n" if nopasswd else "sudo -S -p ''"
            secret = None if nopasswd else password
            for phase, apt_args in (("apt-update", "update"), ("apt-install", "install -y postgresql")):
                emit(directory, f"Inicia {phase}.")
                command = f"{sudo} env LC_ALL=C DEBIAN_FRONTEND=noninteractive apt-get {apt_args}"
                if log_command(client, directory / f"{phase}.log", command, secret, timeout=300) != 0:
                    raise RuntimeError(f"Falló {phase}. Consulta su log.")
                emit(directory, f"{phase} completado.")
            if log_command(client, directory / "postgresql-estado.log", VERIFY_INSTALL) != 0:
                raise RuntimeError("La comprobación de instalación devolvió un error.")
            emit(directory, "PostgreSQL instalado. Se registró el estado del servicio sin ejecutar SQL.")
    except Exception as error:
        emit(directory, f"Sesión detenida: {type(error).__name__}: {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--host", required=True)
    cli.add_argument("--user", required=True)
    cli.add_argument("--output", required=True, type=Path)
    args = cli.parse_args()
    warnings.filterwarnings("error", category=GetPassWarning)
    prepare(args, getpass("Contraseña SSH (entrada oculta): "))
