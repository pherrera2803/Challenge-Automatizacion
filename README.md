# Automatización de switch Cisco (Parte 1)

Proyecto de entrevista: interfaz en **Tkinter** y automatización con **Netmiko** para configurar VLANs y hostname en un switch Cisco real (o en **modo simulación** para pruebas sin equipo).

## Descripción general

La aplicación permite:
- Conectarse por SSH a un switch Cisco (Netmiko) o conectarse a una **simulación**.
- Configurar **hostname** y **VLANs** (IDs y nombres definidos por el usuario).
- Guardar configuración en NVRAM.
- Generar un **backup** local del `running-config` (con hostname y fecha/hora).
- (Opcional) Subir el backup a un servidor remoto por **SFTP** o copiarlo a una carpeta compartida **SMB/UNC**.
- Validar que el estado actual (hostname/VLANs) coincida con lo deseado.

## Requisitos

- Python 3.10 o superior
- Acceso por SSH al switch (usuario con permisos de configuración)

## Instalación

```powershell
cd C:\CodigosPedro\Automatizacion-Switches
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
## Ejecución

```powershell
.\.venv\Scripts\python.exe main.py
```

## Uso del frontend (paso a paso)

### 1) Conexión

- **Conexión real (SSH)**:
  - Completa **IP/FQDN**, **Puerto** (22 por defecto), **Usuario**, **Contraseña**.
  - Tipo Netmiko por defecto: `cisco_ios`.
  - Pulsa **Conectar (validar SSH)**. La app valida la sesión con `show version`.

- **Conexión simulada**:
  - Pulsa **Conectar simulación** (precarga IP `192.168.255.255` y credenciales `admin/admin`).
  - Útil para probar el flujo completo sin un switch real.

### 2) VLANs y hostname

- Agrega VLANs con:
  - **+ Base (10/20/50)** para cargar VLAN 10/20/50 con nombres por defecto.
  - **+ VLAN** para crear una fila nueva y definir **VLAN ID** y **Nombre**.
  - **Eliminar** borra una fila agregada.

- Define el **Hostname** (por defecto `SWITCH_AUTOMATIZADO`).

### 3) Acciones

- **Aplicar (hostname + VLANs)**: envía la configuración (Netmiko usa modo config automáticamente al aplicar).
- **Guardar (NVRAM)**: ejecuta el guardado para persistir cambios.
- **Backup running-config**: guarda un archivo en `backups/` con `hostname + fecha/hora` en el nombre.
- **Validar**: compara hostname/VLANs deseadas contra la configuración actual del switch.

### 4) Backup remoto (opcional)

En **Backup remoto (opcional)** puedes activar:
- **SFTP**: sube el archivo de backup a un servidor SFTP (host/puerto/usuario/clave/dir remoto).
- **SMB (UNC)**: copia el archivo a una ruta UNC, por ejemplo `\\SERVIDOR\share\backups`.


1. **Paso 1 — Conexión:** introduce IP o FQDN, puerto SSH (22 por defecto), usuario y contraseña. Opcionalmente ajusta el tipo de dispositivo Netmiko (`cisco_ios` por defecto). Pulsa *Conectar (validar SSH)* para abrir la sesión y comprobar acceso con un `show version`.
2. **Paso 2 — Configuración:** tras conectar, edita el hostname y los nombres de las VLANs 10, 20 y 50. La aplicación de comandos al switch, guardado en NVRAM, backup y validación se irán añadiendo por fases.

## Notas

- El tipo de dispositivo por defecto es `cisco_ios` (IOS/IOS-XE vía SSH).
- Los backups se almacenan en la ruta `backups/`, con el nombre del switch y fecha/hora.
- Backup remoto (opcional): la app soporta **SFTP** y **SMB/UNC** desde el frontend.
- Modo simulación: usa el botón **Conectar simulación** (IP `192.168.255.255`, usuario `admin`, clave `admin`) para probar sin un switch real.
- La opción **Validar** compara la configuración deseada con la configuración actual del switch; primero ejecuta **Aplicar** (y opcionalmente **Guardar**) para que la validación sea OK.

## Si no levanta la aplicación (recrear venv)

```powershell
rmdir /s /q .venv
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```