"""
Interfaz Tkinter + Netmiko: conexión SSH al switch y captura de datos de VLANs/hostname.
La aplicación de comandos al equipo se ampliará en pasos posteriores.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import paramiko
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException


DEFAULT_DEVICE_TYPE = "cisco_ios"
DEFAULT_HOSTNAME = "SWITCH_AUTOMATIZADO"
VLAN_DEFAULTS: list[tuple[int, str]] = [
    (10, "VLAN_DATOS"),
    (20, "VLAN_VOZ"),
    (50, "VLAN_SEGURIDAD"),
]

SIMULATOR_HOST = "192.168.255.255"
SIMULATOR_USER = "admin"
SIMULATOR_PASS = "admin"


def _normalize_vlan_name(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip())


def _desired_vlan_map_from_rows(rows: list[dict[str, Any]]) -> dict[int, str]:
    out: dict[int, str] = {}
    for row in rows:
        raw_id = str(row["var_id"].get()).strip()
        raw_name = str(row["var_name"].get())
        if not raw_id and not raw_name.strip():
            continue
        try:
            vid = int(raw_id)
        except ValueError:
            raise ValueError(f"VLAN ID inválido: '{raw_id}'")
        if vid < 1 or vid > 4094:
            raise ValueError(f"VLAN ID fuera de rango (1-4094): {vid}")
        name = _normalize_vlan_name(raw_name)
        if not name:
            raise ValueError(f"Nombre vacío para VLAN {vid}")
        out[vid] = name
    return out


class SimulatedCiscoDevice:
    def __init__(self) -> None:
        self.hostname = "SIM_SWITCH"
        self.vlans: dict[int, str] = {1: "default"}
        self.saved = False

    def disconnect(self) -> None:  # netmiko-like
        return None

    def send_command(self, command: str, **_: Any) -> str:  # netmiko-like
        cmd = command.strip().lower()
        if cmd == "show version":
            return "Cisco IOS Software, simulated\nROM: SIM\n"
        if cmd.startswith("show vlan"):
            lines = [
                "VLAN Name                             Status    Ports",
                "---- -------------------------------- --------- -------------------------------",
            ]
            for vid in sorted(self.vlans):
                lines.append(f"{vid:<4} {self.vlans[vid]:<32} active")
            return "\n".join(lines) + "\n"
        if cmd.startswith("show running-config") or cmd.startswith("show run"):
            cfg = [f"hostname {self.hostname}", "!"]
            for vid in sorted(self.vlans):
                if vid == 1:
                    continue
                cfg.extend([f"vlan {vid}", f" name {self.vlans[vid]}", "!"])
            return "\n".join(cfg) + "\n"
        return f"% Unknown command: {command}\n"

    def send_config_set(self, config_commands: list[str], **_: Any) -> str:  # netmiko-like
        current_vlan: int | None = None
        out: list[str] = []
        for raw in config_commands:
            line = raw.strip()
            low = line.lower()
            out.append(line)
            m = re.fullmatch(r"hostname\s+(.+)", line, flags=re.IGNORECASE)
            if m:
                self.hostname = m.group(1).strip()
                current_vlan = None
                self.saved = False
                continue
            m = re.fullmatch(r"vlan\s+(\d+)", line, flags=re.IGNORECASE)
            if m:
                current_vlan = int(m.group(1))
                self.vlans.setdefault(current_vlan, f"VLAN{current_vlan}")
                self.saved = False
                continue
            m = re.fullmatch(r"name\s+(.+)", line, flags=re.IGNORECASE)
            if m and current_vlan is not None:
                self.vlans[current_vlan] = _normalize_vlan_name(m.group(1))
                self.saved = False
                continue
        return "\n".join(out) + "\n"

    def save_config(self, **_: Any) -> str:  # netmiko-like
        self.saved = True
        return "Building configuration...\n[OK]\n"


def _build_vlan_config(desired_vlans: dict[int, str]) -> list[str]:
    cmds: list[str] = []
    for vid in sorted(desired_vlans):
        cmds.append(f"vlan {vid}")
        cmds.append(f" name {desired_vlans[vid]}")
    return cmds


def _parse_hostname_from_running_config(running_config: str) -> str | None:
    m = re.search(r"(?m)^\s*hostname\s+(\S+)\s*$", running_config)
    return m.group(1) if m else None


def _vlan_names_present(show_vlan_brief: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in show_vlan_brief.splitlines():
        line = line.rstrip()
        if not line or line.lower().startswith("vlan ") or line.startswith("----"):
            continue
        m = re.match(r"^\s*(\d+)\s+(\S+)\s+(\S+)", line)
        if not m:
            continue
        vid = int(m.group(1))
        name = m.group(2)
        out[vid] = name
    return out


def _sftp_upload_file(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    local_path: str,
    remote_dir: str,
) -> str:
    remote_dir = remote_dir.strip() or "."
    remote_dir = remote_dir.replace("\\", "/")
    if remote_dir != "." and not remote_dir.startswith("/"):
        remote_dir = "/" + remote_dir
    remote_path = remote_dir.rstrip("/") + "/" + os.path.basename(local_path)

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            # Ensure remote directory exists (best-effort)
            if remote_dir not in (".", "/"):
                parts = [p for p in remote_dir.split("/") if p]
                cur = ""
                for p in parts:
                    cur = cur + "/" + p
                    try:
                        sftp.stat(cur)
                    except IOError:
                        try:
                            sftp.mkdir(cur)
                        except Exception:
                            pass
            sftp.put(local_path, remote_path)
        finally:
            try:
                sftp.close()
            except Exception:
                pass
    finally:
        try:
            transport.close()
        except Exception:
            pass

    return remote_path


def _smb_copy_file(*, local_path: str, unc_dir: str) -> str:
    unc_dir = unc_dir.strip()
    if not unc_dir:
        raise ValueError("Ruta SMB/UNC vacía.")
    dest = os.path.join(unc_dir, os.path.basename(local_path))
    shutil.copy2(local_path, dest)
    return dest


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
        self.btn_connect_sim = ttk.Button(
            btn_row,
            text="Conectar simulación",
            command=self._connect_simulation_clicked,
        )
        self.btn_connect_sim.pack(side=tk.LEFT, padx=(8, 0))

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

        vlan_header = ttk.Frame(cfg)
        vlan_header.pack(fill=tk.X)
        ttk.Label(vlan_header, text="VLANs:", width=10).pack(side=tk.LEFT)
        self.btn_add_base = ttk.Button(
            vlan_header, text="+ Base (10/20/50)", command=self._add_base_vlans
        )
        self.btn_add_base.pack(side=tk.LEFT)
        self.btn_add_vlan = ttk.Button(vlan_header, text="+ VLAN", command=self._add_vlan_row)
        self.btn_add_vlan.pack(side=tk.LEFT, padx=(8, 0))

        table = ttk.Frame(cfg)
        table.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(table, text="VLAN ID", width=10).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(table, text="Nombre", width=30).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(table, text="Acciones", width=10).grid(row=0, column=2, sticky=tk.W)

        self.vlan_table = table
        self.vlan_rows: list[dict[str, Any]] = []

        actions = ttk.Frame(cfg)
        actions.pack(fill=tk.X, pady=(12, 0))
        self.btn_apply = ttk.Button(
            actions, text="Aplicar (hostname + VLANs)", command=self._apply_clicked
        )
        self.btn_apply.pack(side=tk.LEFT)
        self.btn_save = ttk.Button(actions, text="Guardar (NVRAM)", command=self._save_clicked)
        self.btn_save.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_backup = ttk.Button(actions, text="Backup running-config", command=self._backup_clicked)
        self.btn_backup.pack(side=tk.LEFT, padx=(8, 0))
        self.btn_validate = ttk.Button(actions, text="Validar", command=self._validate_clicked)
        self.btn_validate.pack(side=tk.LEFT, padx=(8, 0))

        remote = ttk.LabelFrame(cfg, text="Backup remoto (opcional)", padding=10)
        remote.pack(fill=tk.X, pady=(12, 0))

        self.var_remote_enabled = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(
            remote,
            text="Subir backup también a servidor remoto",
            variable=self.var_remote_enabled,
            command=self._remote_toggle_changed,
        )
        chk.grid(row=0, column=0, columnspan=4, sticky=tk.W)

        self.var_remote_kind = tk.StringVar(value="sftp")
        ttk.Radiobutton(
            remote, text="SFTP", variable=self.var_remote_kind, value="sftp", command=self._remote_kind_changed
        ).grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Radiobutton(
            remote, text="SMB (UNC)", variable=self.var_remote_kind, value="smb", command=self._remote_kind_changed
        ).grid(row=1, column=1, sticky=tk.W, pady=(6, 0))

        # SFTP fields
        self.remote_sftp_frame = ttk.Frame(remote)
        self.remote_sftp_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(self.remote_sftp_frame, text="Host:").grid(row=0, column=0, sticky=tk.W)
        self.var_sftp_host = tk.StringVar()
        ttk.Entry(self.remote_sftp_frame, textvariable=self.var_sftp_host, width=20).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 12)
        )
        ttk.Label(self.remote_sftp_frame, text="Puerto:").grid(row=0, column=2, sticky=tk.W)
        self.var_sftp_port = tk.StringVar(value="22")
        ttk.Entry(self.remote_sftp_frame, textvariable=self.var_sftp_port, width=6).grid(
            row=0, column=3, sticky=tk.W
        )
        ttk.Label(self.remote_sftp_frame, text="Usuario:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        self.var_sftp_user = tk.StringVar()
        ttk.Entry(self.remote_sftp_frame, textvariable=self.var_sftp_user, width=20).grid(
            row=1, column=1, sticky=tk.W, padx=(6, 12), pady=(6, 0)
        )
        ttk.Label(self.remote_sftp_frame, text="Clave:").grid(row=1, column=2, sticky=tk.W, pady=(6, 0))
        self.var_sftp_pass = tk.StringVar()
        ttk.Entry(self.remote_sftp_frame, textvariable=self.var_sftp_pass, width=20, show="*").grid(
            row=1, column=3, sticky=tk.W, pady=(6, 0)
        )
        ttk.Label(self.remote_sftp_frame, text="Dir remoto:").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        self.var_sftp_dir = tk.StringVar(value="/backups")
        ttk.Entry(self.remote_sftp_frame, textvariable=self.var_sftp_dir, width=44).grid(
            row=2, column=1, columnspan=3, sticky=tk.W, padx=(6, 0), pady=(6, 0)
        )

        # SMB fields
        self.remote_smb_frame = ttk.Frame(remote)
        self.remote_smb_frame.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Label(self.remote_smb_frame, text="Ruta UNC:").grid(row=0, column=0, sticky=tk.W)
        self.var_smb_unc = tk.StringVar(value=r"\\SERVIDOR\share\backups")
        ttk.Entry(self.remote_smb_frame, textvariable=self.var_smb_unc, width=44).grid(
            row=0, column=1, sticky=tk.W, padx=(6, 0)
        )
        ttk.Label(
            self.remote_smb_frame,
            text="(Requiere acceso previo a la carpeta compartida en Windows)",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(4, 0))

        self._set_config_widgets_state(tk.DISABLED)
        self._remote_kind_changed()
        self._remote_toggle_changed()

    def _set_config_widgets_state(self, state: str) -> None:
        self.entry_hostname.configure(state=state)
        self.btn_add_base.configure(state=state)
        self.btn_add_vlan.configure(state=state)
        for row in self.vlan_rows:
            row["entry_id"].configure(state=state)
            row["entry_name"].configure(state=state)
            row["btn_delete"].configure(state=state)
        self.btn_apply.configure(state=state)
        self.btn_save.configure(state=state)
        self.btn_backup.configure(state=state)
        self.btn_validate.configure(state=state)
        self.btn_disconnect.configure(state=tk.NORMAL if self.device is not None else tk.DISABLED)
        self._remote_toggle_changed()

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
                if host == SIMULATOR_HOST:
                    if user != SIMULATOR_USER or password != SIMULATOR_PASS:
                        raise NetmikoAuthenticationException("Credenciales inválidas (simulación).")
                    dev = SimulatedCiscoDevice()
                    dev.send_command("show version")
                    self.after(0, lambda: self._on_connect_ok(dev, simulated=True))
                    return

                dev = ConnectHandler(
                    device_type=dtype,
                    host=host,
                    port=port,
                    username=user,
                    password=password,
                    conn_timeout=30,
                )
                dev.send_command("show version", read_timeout=60)
                self.after(0, lambda: self._on_connect_ok(dev, simulated=False))
            except NetmikoTimeoutException as e:
                self.after(0, lambda: self._on_connect_fail(f"Tiempo de espera: {e}"))
            except NetmikoAuthenticationException as e:
                self.after(0, lambda: self._on_connect_fail(f"Autenticación: {e}"))
            except Exception as e:
                self.after(0, lambda: self._on_connect_fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _connect_simulation_clicked(self) -> None:
        if self.device is not None:
            messagebox.showinfo("Conexión", "Ya hay una sesión activa. Desconecta primero.")
            return
        self.var_host.set(SIMULATOR_HOST)
        self.var_port.set("22")
        self.var_username.set(SIMULATOR_USER)
        self.var_password.set(SIMULATOR_PASS)
        self.var_device_type.set(DEFAULT_DEVICE_TYPE)
        self._connect_clicked()

    def _on_connect_ok(self, dev: Any, simulated: bool) -> None:
        self.device = dev
        self.btn_connect.configure(state=tk.NORMAL)
        label = "Estado: conectado (SIMULACIÓN)" if simulated else "Estado: conectado (SSH OK)"
        self.lbl_status.configure(text=label, foreground="green")
        self._set_config_widgets_state(tk.NORMAL)

    def _on_connect_fail(self, msg: str) -> None:
        self.btn_connect.configure(state=tk.NORMAL)
        self.lbl_status.configure(text="Estado: sin conexión", foreground="gray")
        messagebox.showerror("No se pudo conectar", msg)

    def _apply_clicked(self) -> None:
        if self.device is None:
            messagebox.showerror("Sin conexión", "Primero conecta al switch.")
            return

        hostname = self.var_hostname.get().strip()
        if not hostname:
            messagebox.showerror("Hostname", "El hostname no puede estar vacío.")
            return

        try:
            desired_vlans = _desired_vlan_map_from_rows(self.vlan_rows)
        except ValueError as e:
            messagebox.showerror("VLANs", str(e))
            return
        if not desired_vlans:
            messagebox.showerror("VLANs", "Agrega al menos una VLAN (botón +).")
            return

        cmds = [f"hostname {hostname}", *_build_vlan_config(desired_vlans)]
        self._run_device_job(
            title="Aplicar configuración",
            job=lambda: self.device.send_config_set(cmds),
        )

    def _save_clicked(self) -> None:
        if self.device is None:
            messagebox.showerror("Sin conexión", "Primero conecta al switch.")
            return

        def job() -> str:
            if hasattr(self.device, "save_config"):
                return self.device.save_config()
            return self.device.send_command("copy running-config startup-config", read_timeout=120)

        self._run_device_job(title="Guardar configuración", job=job)

    def _backup_clicked(self) -> None:
        if self.device is None:
            messagebox.showerror("Sin conexión", "Primero conecta al switch.")
            return

        def job() -> str:
            running = self.device.send_command("show running-config", read_timeout=120)
            host = _parse_hostname_from_running_config(running) or "SWITCH"
            ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            out_dir = os.path.join(os.getcwd(), "backups")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{host}-{ts}-running-config.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(running)
            msgs = [f"Backup local guardado en:\n{path}"]

            if self.var_remote_enabled.get():
                kind = self.var_remote_kind.get()
                if kind == "sftp":
                    sftp_host = self.var_sftp_host.get().strip()
                    sftp_user = self.var_sftp_user.get().strip()
                    sftp_pass = self.var_sftp_pass.get()
                    sftp_dir = self.var_sftp_dir.get().strip() or "/"
                    if not sftp_host or not sftp_user:
                        raise ValueError("SFTP: completa host y usuario.")
                    try:
                        sftp_port = int(self.var_sftp_port.get().strip() or "22")
                    except ValueError:
                        raise ValueError("SFTP: puerto inválido.")
                    remote_path = _sftp_upload_file(
                        host=sftp_host,
                        port=sftp_port,
                        username=sftp_user,
                        password=sftp_pass,
                        local_path=path,
                        remote_dir=sftp_dir,
                    )
                    msgs.append(f"Subido por SFTP a:\n{remote_path}")
                elif kind == "smb":
                    unc_dir = self.var_smb_unc.get().strip()
                    remote_path = _smb_copy_file(local_path=path, unc_dir=unc_dir)
                    msgs.append(f"Copiado por SMB a:\n{remote_path}")
                else:
                    raise ValueError(f"Tipo remoto no soportado: {kind}")

            return "\n\n".join(msgs)

        self._run_device_job(title="Backup running-config", job=job)

    def _validate_clicked(self) -> None:
        if self.device is None:
            messagebox.showerror("Sin conexión", "Primero conecta al switch.")
            return

        desired_hostname = self.var_hostname.get().strip()
        try:
            desired_vlans = _desired_vlan_map_from_rows(self.vlan_rows)
        except ValueError as e:
            messagebox.showerror("VLANs", str(e))
            return

        def job() -> str:
            running = self.device.send_command("show running-config", read_timeout=120)
            actual_hostname = _parse_hostname_from_running_config(running)
            vlan_brief = self.device.send_command("show vlan brief", read_timeout=120)
            actual_vlans = _vlan_names_present(vlan_brief)

            problems: list[str] = []
            if actual_hostname != desired_hostname:
                problems.append(f"- Hostname esperado: {desired_hostname} | actual: {actual_hostname}")

            for vid, name in desired_vlans.items():
                actual = actual_vlans.get(vid)
                if actual != name:
                    problems.append(f"- VLAN {vid}: esperado '{name}' | actual '{actual}'")

            if problems:
                return "VALIDACIÓN: NO OK\n\n" + "\n".join(problems)
            return "VALIDACIÓN: OK (hostname y VLANs coinciden)"

        self._run_device_job(title="Validación", job=job, show_as_error_on_fail=True)

    def _run_device_job(
        self,
        title: str,
        job: callable,
        show_as_error_on_fail: bool = False,
    ) -> None:
        self.btn_apply.configure(state=tk.DISABLED)
        self.btn_save.configure(state=tk.DISABLED)
        self.btn_backup.configure(state=tk.DISABLED)
        self.btn_validate.configure(state=tk.DISABLED)

        def worker() -> None:
            try:
                result = job()
                self.after(0, lambda: messagebox.showinfo(title, str(result).strip() or "OK"))
            except Exception as e:
                self.after(
                    0,
                    lambda: messagebox.showerror(title, str(e))
                    if show_as_error_on_fail
                    else messagebox.showwarning(title, str(e)),
                )
            finally:
                self.after(0, lambda: self._set_config_widgets_state(tk.NORMAL))

        threading.Thread(target=worker, daemon=True).start()

    def _add_vlan_row(self, vid: int | None = None, name: str = "") -> None:
        var_id = tk.StringVar(value="" if vid is None else str(vid))
        var_name = tk.StringVar(value=name)
        entry_id = ttk.Entry(self.vlan_table, textvariable=var_id, width=10)
        entry_name = ttk.Entry(self.vlan_table, textvariable=var_name, width=32)
        btn_delete = ttk.Button(
            self.vlan_table, text="Eliminar", command=lambda: self._delete_vlan_row(row_ref)
        )
        row_ref: dict[str, Any] = {
            "var_id": var_id,
            "var_name": var_name,
            "entry_id": entry_id,
            "entry_name": entry_name,
            "btn_delete": btn_delete,
        }
        # Now that row_ref exists, we can safely set the command target
        btn_delete.configure(command=lambda r=row_ref: self._delete_vlan_row(r))

        self.vlan_rows.append(
            row_ref
        )
        self._regrid_vlan_rows()
        # Respect current enabled/disabled state
        if self.device is None:
            entry_id.configure(state=tk.DISABLED)
            entry_name.configure(state=tk.DISABLED)
            btn_delete.configure(state=tk.DISABLED)

    def _add_base_vlans(self) -> None:
        existing: set[int] = set()
        for row in self.vlan_rows:
            try:
                existing.add(int(str(row["var_id"].get()).strip()))
            except Exception:
                continue
        for vid, default_name in VLAN_DEFAULTS:
            if vid not in existing:
                self._add_vlan_row(vid=vid, name=default_name)

    def _delete_vlan_row(self, row: dict[str, Any]) -> None:
        try:
            row["entry_id"].destroy()
        except Exception:
            pass
        try:
            row["entry_name"].destroy()
        except Exception:
            pass
        try:
            row["btn_delete"].destroy()
        except Exception:
            pass

        self.vlan_rows = [r for r in self.vlan_rows if r is not row]
        self._regrid_vlan_rows()

    def _regrid_vlan_rows(self) -> None:
        for i, row in enumerate(self.vlan_rows, start=1):  # header is row 0
            row["entry_id"].grid(row=i, column=0, sticky=tk.W, pady=4)
            row["entry_name"].grid(row=i, column=1, sticky=tk.W, pady=4)
            row["btn_delete"].grid(row=i, column=2, sticky=tk.W, pady=4)

    def _remote_toggle_changed(self) -> None:
        enabled = bool(self.var_remote_enabled.get()) and self.device is not None
        for child in self.remote_sftp_frame.winfo_children():
            if hasattr(child, "configure"):
                try:
                    child.configure(state=(tk.NORMAL if enabled and self.var_remote_kind.get() == "sftp" else tk.DISABLED))
                except Exception:
                    pass
        for child in self.remote_smb_frame.winfo_children():
            if hasattr(child, "configure"):
                try:
                    child.configure(state=(tk.NORMAL if enabled and self.var_remote_kind.get() == "smb" else tk.DISABLED))
                except Exception:
                    pass

    def _remote_kind_changed(self) -> None:
        kind = self.var_remote_kind.get()
        self.remote_sftp_frame.grid_remove()
        self.remote_smb_frame.grid_remove()
        if kind == "sftp":
            self.remote_sftp_frame.grid()
        else:
            self.remote_smb_frame.grid()
        self._remote_toggle_changed()

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
