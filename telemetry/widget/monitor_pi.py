"""Monitor de escritorio para una Raspberry Pi accesible por SSH."""

from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread
import tkinter as tk
from tkinter import simpledialog, ttk

import paramiko


KNOWN_HOSTS = Path.home() / ".ssh" / "known_hosts"

# Un shell remoto, una sesión SSH y una muestra cada tres segundos.
# Los porcentajes se calculan en la laptop a partir de los contadores.
COLLECTOR = r"""
while :; do
    read -r label user nice system idle iowait irq softirq steal rest < /proc/stat || exit 1
    total=$((user + nice + system + idle + iowait + irq + softirq + steal))
    idle_total=$((idle + iowait))
    mem_total=0
    mem_available=-1
    while read -r key value unit; do
        case "$key" in
            MemTotal:) mem_total=$value ;;
            MemAvailable:) mem_available=$value; break ;;
        esac
    done < /proc/meminfo
    temp=na
    if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
        read -r temp < /sys/class/thermal/thermal_zone0/temp || temp=na
    fi
    printf 'PI %s %s %s %s %s\n' "$total" "$idle_total" "$mem_total" "$mem_available" "$temp" || exit 0
    sleep 3
done
"""


def monitor(host, username, password, updates, stopped):
    try:
        with paramiko.SSHClient() as client:
            if KNOWN_HOSTS.is_file():
                client.load_host_keys(str(KNOWN_HOSTS))
            if not client.get_host_keys().lookup(host):
                updates.put(("error", "Confirma primero la identidad de esta Pi en PowerShell por SSH."))
                return
            client.connect(
                host, username=username, password=password, look_for_keys=False,
                allow_agent=False, timeout=6, banner_timeout=6, auth_timeout=8,
            )
            password = None
            _, output, _ = client.exec_command(COLLECTOR, timeout=12)
            for line in output:
                if stopped.is_set():
                    return
                values = line.split()
                if len(values) == 6 and values[0] == "PI":
                    total, idle, ram, available = map(int, values[1:5])
                    temp = None if values[5] == "na" else int(values[5]) / 1000
                    updates.put(("sample", (total, idle, ram, available, temp)))
            updates.put(("error", "La sesión de medición se cerró."))
    except paramiko.BadHostKeyException:
        updates.put(("error", "La identidad SSH cambió. Verifica la IP y la huella de la Pi."))
    except paramiko.AuthenticationException:
        updates.put(("error", "SSH rechazó el usuario o la contraseña."))
    except (OSError, paramiko.SSHException, ValueError):
        updates.put(("error", "Sin lecturas. Revisa la red, la IP y que SSH esté activo."))


class Widget:
    def __init__(self, root):
        self.root = root
        self.updates = SimpleQueue()
        self.stopped = Event()
        self.previous_cpu = None
        self.host = tk.StringVar(value="192.168.1.80")
        self.username = tk.StringVar(value="rasp")
        self.status = tk.StringVar(value="Listo para conectar")
        self.values = [tk.StringVar(value="—") for _ in range(3)]
        self.bars = [tk.DoubleVar() for _ in range(2)]

        root.title("Monitor Raspberry Pi")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=14)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Raspberry Pi Zero 2 W", font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, text="IP").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.host_input = ttk.Entry(frame, textvariable=self.host, width=17)
        self.host_input.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        self.user_input = ttk.Entry(frame, textvariable=self.username, width=9)
        self.user_input.grid(row=1, column=2, sticky="ew")

        for index, label in enumerate(("CPU", "RAM", "Temperatura")):
            row = 2 + index
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=5)
            if index < 2:
                ttk.Progressbar(frame, variable=self.bars[index], maximum=100, length=85).grid(
                    row=row, column=1, sticky="ew", padx=(0, 6)
                )
            ttk.Label(frame, textvariable=self.values[index], width=21, anchor="e").grid(
                row=row, column=2, sticky="e"
            )

        ttk.Label(frame, textvariable=self.status, wraplength=290).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(5, 7)
        )
        self.connect_button = ttk.Button(frame, text="Conectar", command=self.connect)
        self.connect_button.grid(row=6, column=0, columnspan=3, sticky="ew")
        root.after(400, self.refresh)

    def connect(self):
        host, username = self.host.get().strip(), self.username.get().strip()
        if not host or not username:
            self.status.set("Escribe la IP y el usuario.")
            return
        password = simpledialog.askstring("Monitor Raspberry Pi", f"Contraseña SSH de {username}", show="*", parent=self.root)
        if password is None:
            return
        self.previous_cpu = None
        self.status.set("Conectando por SSH…")
        for control in (self.connect_button, self.host_input, self.user_input):
            control.configure(state="disabled")
        Thread(target=monitor, args=(host, username, password, self.updates, self.stopped), daemon=True).start()

    def refresh(self):
        while True:
            try:
                kind, value = self.updates.get_nowait()
            except Empty:
                break
            if kind == "sample":
                self.display(value)
            else:
                self.status.set(value)
                for reading in self.values:
                    reading.set("—")
                for bar in self.bars:
                    bar.set(0)
                for control in (self.connect_button, self.host_input, self.user_input):
                    control.configure(state="normal")
        self.root.after(400, self.refresh)

    def display(self, sample):
        total, idle, ram, available, temp = sample
        if self.previous_cpu:
            previous_total, previous_idle = self.previous_cpu
            elapsed = total - previous_total
            idle_ticks = idle - previous_idle
            if elapsed > 0 and 0 <= idle_ticks <= elapsed:
                cpu = 100 * (elapsed - idle_ticks) / elapsed
                self.bars[0].set(cpu)
                self.values[0].set(f"{cpu:.0f} %")
        self.previous_cpu = (total, idle)
        if ram > 0 and 0 <= available <= ram:
            used = ram - available
            percent = 100 * used / ram
            self.bars[1].set(percent)
            self.values[1].set(f"{percent:.0f} %  ·  {used / 1024:.0f}/{ram / 1024:.0f} MiB")
        self.values[2].set("—" if temp is None else f"{temp:.1f} °C")
        self.status.set("En vivo · actualización cada 3 s")

    def close(self):
        self.stopped.set()
        self.root.destroy()


if __name__ == "__main__":
    app = tk.Tk()
    Widget(app)
    app.mainloop()
