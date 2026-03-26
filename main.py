"""
Interfaz Tkinter + Netmiko: conexión SSH al switch y captura de datos de VLANs/hostname.
La aplicación de comandos al equipo se ampliará en pasos posteriores.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException


DEFAULT_DEVICE_TYPE = "cisco_ios"
DEFAULT_HOSTNAME = "SWITCH_AUTOMATIZADO"
VLAN_DEFAULTS: list[tuple[int, str]] = [
    (10, "VLAN_DATOS"),
    (20, "VLAN_VOZ"),
    (50, "VLAN_SEGURIDAD"),
]


class CiscoAutomationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Automatización Cisco — VLANs y hostname")
        self.minsize(520, 420)
        self.device: Any = None

        self._build_connection_frame()
        self._build_config_frame()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_connection_frame(self) -> None:
        conn = ttk.LabelFrame(self, text="1. Conexión al switch", padding=10)
        conn.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(conn, text="IP o FQDN:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.var_host = tk.StringVar()
        ttk.Entry(conn, textvariable=self.var_host, width=32).grid(
            row=0, column=1, sticky=tk.W, pady=2
        )

        ttk.Label(conn, text="Puerto SSH:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.var_port = tk.StringVar(value="22")
        ttk.Entry(conn, textvariable=self.var_port, width=8).grid(
            row=1, column=1, sticky=tk.W, pady=2
        )

        ttk.Label(conn, text="Usuario:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.var_username = tk.StringVar()
        ttk.Entry(conn, textvariable=self.var_username, width=32).grid(
            row=2, column=1, sticky=tk.W, pady=2
        )

        ttk.Label(conn, text="Contraseña:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.var_password = tk.StringVar()
        ttk.Entry(
            conn, textvariable=self.var_password, width=32, show="*"
        ).grid(row=3, column=1, sticky=tk.W, pady=2)

        ttk.Label(conn, text="Tipo Netmiko:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.var_device_type = tk.StringVar(value=DEFAULT_DEVICE_TYPE)
        ttk.Entry(conn, textvariable=self.var_device_type, width=20).grid(
            row=4, column=1, sticky=tk.W, pady=2
        )

        btn_row = ttk.Frame(conn)
        btn_row.grid(row=5, column=0, columnspan=2, pady=(8, 0), sticky=tk.W)
        self.btn_connect = ttk.Button(
            btn_row, text="Conectar (validar SSH)", command=self._connect_clicked
        )
        self.btn_connect.pack(side=tk.LEFT)
        self.btn_disconnect = ttk.Button(
            btn_row, text="Desconectar", command=self._disconnect, state=tk.DISABLED
        )
        self.btn_disconnect.pack(side=tk.LEFT, padx=(8, 0))

        self.lbl_status = ttk.Label(conn, text="Estado: sin conexión", foreground="gray")
        self.lbl_status.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))

    def _build_config_frame(self) -> None:
        cfg = ttk.LabelFrame(self, text="2. VLANs y hostname", padding=10)
        cfg.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.var_hostname = tk.StringVar(value=DEFAULT_HOSTNAME)
        hf = ttk.Frame(cfg)
        hf.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(hf, text="Hostname del switch:").pack(side=tk.LEFT)
        self.entry_hostname = ttk.Entry(hf, textvariable=self.var_hostname, width=28)
        self.entry_hostname.pack(side=tk.LEFT, padx=(8, 0))

        table = ttk.Frame(cfg)
        table.pack(fill=tk.X)
        ttk.Label(table, text="VLAN ID", width=10).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(table, text="Nombre", width=30).grid(row=0, column=1, sticky=tk.W)

        self.vlan_name_vars: dict[int, tk.StringVar] = {}
        self.vlan_entries: list[ttk.Entry] = []
        for i, (vid, default_name) in enumerate(VLAN_DEFAULTS, start=1):
            ttk.Label(table, text=str(vid)).grid(row=i, column=0, sticky=tk.W, pady=4)
            var = tk.StringVar(value=default_name)
            self.vlan_name_vars[vid] = var
            ent = ttk.Entry(table, textvariable=var, width=32)
            ent.grid(row=i, column=1, sticky=tk.W, pady=4)
            self.vlan_entries.append(ent)

        self._set_config_widgets_state(tk.DISABLED)

        hint = ttk.Label(
            cfg,
            text=(
                "Esta sección se habilita tras una conexión SSH correcta. "
                "La aplicación de la configuración al switch se añadirá en el siguiente paso."
            ),
            foreground="gray",
            wraplength=480,
        )
        hint.pack(anchor=tk.W, pady=(12, 0))

    def _set_config_widgets_state(self, state: str) -> None:
        self.entry_hostname.configure(state=state)
        for ent in self.vlan_entries:
            ent.configure(state=state)

    def _connect_clicked(self) -> None:
        if self.device is not None:
            messagebox.showinfo("Conexión", "Ya hay una sesión activa. Desconecta primero.")
            return

        host = self.var_host.get().strip()
        user = self.var_username.get().strip()
        password = self.var_password.get()
        dtype = self.var_device_type.get().strip() or DEFAULT_DEVICE_TYPE

        if not host or not user:
            messagebox.showerror("Datos incompletos", "Indica IP/FQDN y usuario.")
            return

        try:
            port = int(self.var_port.get().strip() or "22")
        except ValueError:
            messagebox.showerror("Puerto inválido", "El puerto debe ser un número.")
            return

        self.btn_connect.configure(state=tk.DISABLED)
        self.lbl_status.configure(text="Estado: conectando…", foreground="blue")

        def worker() -> None:
            try:
                dev = ConnectHandler(
                    device_type=dtype,
                    host=host,
                    port=port,
                    username=user,
                    password=password,
                    conn_timeout=30,
                )
                dev.send_command("show version", read_timeout=60)
                self.after(0, lambda: self._on_connect_ok(dev))
            except NetmikoTimeoutException as e:
                self.after(0, lambda: self._on_connect_fail(f"Tiempo de espera: {e}"))
            except NetmikoAuthenticationException as e:
                self.after(0, lambda: self._on_connect_fail(f"Autenticación: {e}"))
            except Exception as e:
                self.after(0, lambda: self._on_connect_fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_ok(self, dev: Any) -> None:
        self.device = dev
        self.btn_connect.configure(state=tk.NORMAL)
        self.btn_disconnect.configure(state=tk.NORMAL)
        self.lbl_status.configure(text="Estado: conectado (SSH OK)", foreground="green")
        self._set_config_widgets_state(tk.NORMAL)

    def _on_connect_fail(self, msg: str) -> None:
        self.btn_connect.configure(state=tk.NORMAL)
        self.lbl_status.configure(text="Estado: sin conexión", foreground="gray")
        messagebox.showerror("No se pudo conectar", msg)

    def _disconnect(self) -> None:
        if self.device is not None:
            try:
                self.device.disconnect()
            except Exception:
                pass
            self.device = None
        self.btn_disconnect.configure(state=tk.DISABLED)
        self.lbl_status.configure(text="Estado: sin conexión", foreground="gray")
        self._set_config_widgets_state(tk.DISABLED)

    def _on_close(self) -> None:
        if self.device is not None:
            try:
                self.device.disconnect()
            except Exception:
                pass
        self.destroy()


def main() -> None:
    app = CiscoAutomationApp()
    app.mainloop()


if __name__ == "__main__":
    main()
