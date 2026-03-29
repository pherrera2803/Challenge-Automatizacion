# Parte 2 — VPN IPSec Fortigate ↔ Palo Alto (planificación)

Esta carpeta contiene el **entregable de planificación** para automatizar una VPN IPSec **site-to-site** entre **Fortigate (FortiOS)** y **Palo Alto (PAN-OS)**, documentado en el mismo repositorio que la Parte 1.

## Documento principal

| Archivo | Contenido |
|--------|-----------|
| [`PLAN_VPN_IPSEC_FORTIGATE_PALOALTO.md`](PLAN_VPN_IPSEC_FORTIGATE_PALOALTO.md) | Plan completo: parámetros, herramientas/APIs, pasos de automatización, consideraciones multi-vendor, validación, alertas, seguridad de credenciales, logging, rollback e idempotencia. |

Empieza por ese Markdown: es el núcleo del criterio de evaluación de la Parte 2.

## Artefactos opcionales

### Ejemplos de configuración (conceptuales)

| Archivo | Uso |
|--------|-----|
| [`examples/fortigate_example.txt`](examples/fortigate_example.txt) | Fragmentos de referencia FortiOS (Phase1/Phase2, túnel, rutas). Ajustar a tu versión/VDOM/interfaces. |
| [`examples/paloalto_example_setcli.txt`](examples/paloalto_example_setcli.txt) | Comandos `set` de referencia PAN-OS (crypto, IKE gateway, túnel, ruta). Requiere commit; validar sintaxis según tu versión. |

No son configuraciones listas para copiar/pegar en producción: sirven como **base** para la entrevista y para alinear nombres con el plan.

### Script de prueba de conectividad

[`scripts/connectivity_test.py`](scripts/connectivity_test.py) prueba **TCP** hacia un host/puerto en la red remota (útil si ICMP no está permitido).

Desde la raíz del repositorio:

```powershell
python part2\scripts\connectivity_test.py --host 10.20.20.10 --port 443
```

Salida **JSON** (una línea en stdout; los logs con timestamp van a stderr):

```powershell
python part2\scripts\connectivity_test.py --host 10.20.20.10 --port 443 --json
```

**Qué indica el resultado:** `success` en el JSON es **conectividad TCP** hacia un host/puerto en la red remota (prueba de extremo a extremo si enrutas por el túnel). **No** equivale a leer en Fortigate/Palo Alto si el túnel IPSec está “UP” o si IKE negoció bien; eso se valida con **CLI/API** en los firewalls (como en `PLAN_VPN_IPSEC_FORTIGATE_PALOALTO.md`, validación §5). El campo `ipsec_state_from_device` en el JSON queda en `false` para dejar explícito que este script **no** consulta el estado IPSec en el equipo.

Además, aunque el túnel IPSec esté bien, hace falta **rutas** (estáticas o BGP, según diseño) y **políticas de firewall** en **Fortigate y en Palo Alto** para que el tráfico entre redes esté permitido y enrutado; está detallado en el plan **`§3.4`**.

Solo depende de la biblioteca estándar de Python (sin paquetes extra).

## Estructura de esta carpeta

```
part2/
├── README.md                          ← este archivo
├── PLAN_VPN_IPSEC_FORTIGATE_PALOALTO.md
├── examples/
│   ├── fortigate_example.txt
│   └── paloalto_example_setcli.txt
└── scripts/
    └── connectivity_test.py
```

## Relación con la Parte 1

La Parte 1 (Tkinter + Netmiko + switch Cisco) vive en la raíz del repo (`main.py`, `requirements.txt`, README principal). 
La Parte 2 es **independiente** y solo comparte el mismo repositorio Git para el entregable único.
