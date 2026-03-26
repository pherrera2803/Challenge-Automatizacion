# Automatización de switch Cisco (Parte 1)

Proyecto de entrevista: interfaz en **Tkinter** y automatización con **Netmiko** para configurar VLANs y hostname en un switch Cisco real.

## Requisitos

- Python 3.10 o superior
- Acceso por SSH al switch (usuario con permisos de configuración)

## Instalación

```powershell -- correr cada comando desde la raiz del proyecto para arrancar la aplicacion
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt


## Ejecución

```powershell
# Si usas entorno virtual:
.\.venv\Scripts\python.exe main.py

# Alternativa (si tu PATH apunta al Python correcto):
python main.py
```


1. **Paso 1 — Conexión:** introduce IP o FQDN, puerto SSH (22 por defecto), usuario y contraseña. Opcionalmente ajusta el tipo de dispositivo Netmiko (`cisco_ios` por defecto). Pulsa *Conectar (validar SSH)* para abrir la sesión y comprobar acceso con un `show version`.
2. **Paso 2 — Configuración:** tras conectar, edita el hostname y los nombres de las VLANs 10, 20 y 50. La aplicación de comandos al switch, guardado en NVRAM, backup y validación se irán añadiendo por fases.

## Notas

- El tipo de dispositivo por defecto es `cisco_ios` (IOS/IOS-XE vía SSH).
- Los backups y la aplicación completa de la configuración se documentarán conforme se añadan al repositorio.


## Caso que no levante la aplicacion -- puuedes aplicar los siguientes comandos para recrear el venv
rmdir /s /q .venv
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py