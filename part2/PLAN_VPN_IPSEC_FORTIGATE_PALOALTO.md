#  (Parte 2)

# Plan de Automatización

# VPN IPSec Fortigate ↔ Palo Alto

ste documento describe un plan para automatizar la configuración de una VPN IPSec site-to-site entre un firewall Fortigate (FortiOS) y un firewall Palo Alto (PAN-OS) en un entorno multi-vendor.

El objetivo es definir un enfoque estructurado, reutilizable e idempotente que permita implementar, validar y mantener la configuración de forma automatizada mediante el uso de APIs y scripts en Python.

**Alcance:** planificación + ejemplos conceptuales (no requiere acceso a equipos reales).

Topología Lógica

Fortigate (LAN 10.10.10.0/24)

        |

   [IPSec Tunnel]

        |

Palo Alto (LAN 10.20.20.0/24)



*La automatización debería partir de un archivo de parámetros (por ejemplo YAML/JSON) con, como mínimo, lo siguiente.*



### 1.1 Identidad y gestión (para automatización)

- **Fortigate**
  - **mgmt_host**: IP/FQDN de administración
  - **mgmt_port**: (HTTPS API) 443 por defecto
  - **api_token** o usuario/clave (ideal: token)
  - **vdom** (si aplica)
- **Palo Alto**
  - **mgmt_host**: IP/FQDN de administración
  - **mgmt_port**: 443 por defecto
  - **api_key** o usuario/clave (ideal: api key)
  - **vsys** (si aplica)

### 1.2 Parámetros de la VPN (site-to-site)

#### Direcciones WAN (peer / gateway)

- **fgt_wan_ip**: IP pública/externa del Fortigate
- **pa_wan_ip**: IP pública/externa del Palo Alto

#### Redes locales (ejemplo)

- **fgt_local_subnets**: por ejemplo `10.10.10.0/24`
- **pa_local_subnets**: por ejemplo `10.20.20.0/24`

#### Red de túnel (route-based)

Se pide: **`169.254.1.0/30`** con IP por extremo (prefijo **`169.254.0.0/16`**, convención habitual para direccionamiento interno de enlace / túnel punto a punto).

- **tunnel_network**: `169.254.1.0/30`
- **fgt_tunnel_ip**: `169.254.1.1/30`
- **pa_tunnel_ip**: `169.254.1.2/30`

#### Autenticación

- **psk** (pre-shared key) — debe ser igual en ambos extremos.
- **ike_version**: recomendado `ikev2` (si ambos lo soportan en el baseline).

#### Propuestas compatibles (Phase 1 / IKE)

Recomendación “baseline” compatible (ajustable):

- **encryption**: AES-256
- **integrity**: SHA-256
- **dh_group**: grupo 14 (modp2048) o grupo 19 (ecp256) si ambos lo soportan
- **lifetime**: 28800s (8h) típico
- **nat_traversal**: habilitado (si hay NAT)
- **dpd**: habilitado (keepalive / dead peer detection)

#### Propuestas compatibles (Phase 2 / IPsec)

Recomendación “baseline” compatible (ajustable):

- **protocol**: ESP
- **encryption**: AES-256
- **integrity**: SHA-256
- **pfs**: grupo 14 (o deshabilitado si el entorno lo exige, pero preferible habilitar)
- **lifetime**: 3600s (1h) típico
- **selectors / proxy-ids**
  - Route-based: selectores 0.0.0.0/0 ↔ 0.0.0.0/0 (según modelo) y control por rutas/políticas
  - Policy-based: selectores por subred (10.10.10.0/24 ↔ 10.20.20.0/24)

> Nota: Fortigate y Palo Alto suelen implementarse mejor como **route-based** (tunnel interface) y control de tráfico mediante rutas y políticas.

## 2) Identificación de herramientas / APIs para automatización

### 2.1 Fortigate (FortiOS)

- **FortiOS REST API** (recomendado)
  - Ventajas: idempotencia más sencilla, lectura/validación directa, menos “screen scraping”.
- **SSH** (alternativa)
  - Usable con Netmiko/Paramiko si no se puede usar API.
- **FortiManager** (si existiera en el entorno)
  - Centraliza y simplifica despliegues masivos.

### 2.2 Palo Alto (PAN-OS)

- **PAN-OS XML API / REST API** (según versión; recomendado usar API oficial disponible en tu PAN-OS)
  - Permite crear objetos, IKE/IPsec, interfaces túnel, rutas, políticas, commit.
- **SSH** (alternativa)
  - Automatable, pero menos robusto que API para validación y consistencia.
- **Panorama** (si existiera en el entorno)
  - Gestión centralizada con plantillas/Device Groups.

## 3) Pasos lógicos de automatización (flujo del script)

Un script “bien hecho” debería ser **determinista** (misma entrada → misma config) e **idempotente** (si ya existe, no rompe; actualiza solo si difiere).

### Idempotencia

El proceso de automatización debe ser **idempotente**, es decir:

- Si la configuración ya existe y **coincide** con lo deseado, **no debe modificarse**.
- Si **existe pero difiere**, debe **actualizarse** hasta alinearla con el estado objetivo.
- Si **no existe**, debe **crearse**.

Esto evita configuraciones duplicadas, reduce el riesgo en **ejecuciones repetidas** (re-runs del pipeline o del script) y facilita auditorías (“solo cambió lo que debía cambiar”).

### 3.1 Pre-checks y validación de inputs

- Validar formato de IPs, subredes y que `169.254.1.0/30` tenga 2 hosts.
- Validar que `fgt_tunnel_ip` y `pa_tunnel_ip` estén dentro del /30 y sean diferentes.
- Validar que Phase1/Phase2 propuestas tengan intersección (al menos 1 combinación compatible).
- Validar conectividad a management (HTTPs a APIs, DNS si aplica).

### 3.2 Configurar Fortigate (alto nivel)

1. Crear/validar **address objects** para `pa_local_subnets`.
2. Crear/validar **IPsec Phase1 interface**:
  - peer: `pa_wan_ip`
  - psk, ike version, proposals, DPD, NAT-T
3. Crear/validar **IPsec Phase2**:
  - selectors (o 0/0 en route-based según diseño)
  - proposals, PFS, lifetime
4. Crear/validar **interfaz túnel** (si aplica) y asignar `fgt_tunnel_ip`.
5. Crear/validar **rutas estáticas** hacia `pa_local_subnets` vía el túnel (o usar routing dinámico si se define).
6. Crear/validar **políticas de firewall**:
  - permit `fgt_local_subnets` → `pa_local_subnets` (y retorno)
  - definir servicios permitidos (ICMP, TCP/UDP según necesidad)
7. Guardar/commit según corresponda (en Fortigate típicamente los cambios se aplican al guardar la config; vía API se reflejan directamente).

### 3.3 Configurar Palo Alto (alto nivel)

1. Crear/validar **Address Objects** para `fgt_local_subnets`.
2. Crear/validar **IKE Crypto Profile** (Phase 1).
3. Crear/validar **IPsec Crypto Profile** (Phase 2).
4. Crear/validar **IKE Gateway** apuntando a `fgt_wan_ip` con PSK.
5. Crear/validar **Tunnel Interface** (ej. `tunnel.1`) y asignar `pa_tunnel_ip`.
6. Crear/validar **IPsec Tunnel** ligando Gateway + Crypto Profiles + Tunnel Interface.
7. Crear/validar **Virtual Router**:
  - Rutas a `fgt_local_subnets` vía `tunnel.1`
8. Crear/validar **Security Policies** (permitir tráfico entre zonas/subredes).
9. **Commit** (PAN-OS requiere commit para aplicar cambios).

### 3.4 Túnel IPSec y tráfico útil: Fortigate y Palo Alto (ambos lados)

Levantar el **túnel IPSec** (IKE + IPsec SA) **no basta** para que las redes locales se hablen: hace falta **enrutamiento** y **políticas de seguridad** en **los dos firewalls**.

- **Fortigate**
  - **Rutas**: hacia las subredes remotas apuntando al túnel/interfaz correcta (o **BGP** si el diseño anuncia prefijos por el túnel).
  - **Políticas de firewall**: reglas que **permitan** explícitamente el tráfico (origen/destino, servicios, NAT si aplica). Sin política que permita el flujo, el túnel puede estar “UP” y el tráfico igual cae en **deny implicit**.

- **Palo Alto**
  - **Mismo concepto**: en **Virtual Router** necesitas **ruta estática** (o BGP/OSPF según diseño) hacia `fgt_local_subnets` vía `tunnel.x`; y **Security Policies** entre zonas que **permitan** el tráfico hacia/desde esas redes. PAN-OS también tiene **deny implícito** al final.

En resumen: **sí** — en Palo Alto hay que hacer el equivalente (rutas + políticas), aunque la sintaxis y el modelo (zonas, VR, commit) son distintos a Fortigate. El plan de automatización debería tratar **routing + políticas** como parte del mismo entregable, no solo Phase1/Phase2.

## 4) Consideraciones específicas y desafíos (multi-vendor)

- **Route-based vs policy-based**: ambos vendors soportan ambos modelos, pero route-based suele ser más claro para automatización.
- **Nombres y referencias cruzadas**: perfiles, gateways y tunnels dependen de nombres exactos; definir convención (`VPN-FGT-PA-S2S`, `IKE-PROFILE-...`).
- **Compatibilidad de propuestas**: mismatches de IKE/ESP (AES/SHA/DH/PFS/lifetimes) son causa #1 de fallas.
- **NAT-T / ID**: si hay NAT, NAT-T debe estar habilitado; los “ID” (local/peer ID) pueden requerirse en ciertos escenarios.
- **MTU/MSS**: el túnel puede requerir ajuste de MSS clamping para evitar fragmentación.
- **Commit/apply**: PAN-OS requiere commit; Fortigate aplica diferente según método.
- **Zonas/Interfaces**: Palo Alto opera fuerte con zones; Fortigate con interfaces/policies; el mapping debe estar claro.
- **Ambientes con VDOM/VSYS**: hay que parametrizarlo.

### Seguridad de credenciales

En entornos corporativos, la automatización no debe persistir secretos en el código ni en el repositorio:

- **Variables de entorno o vaults** (por ejemplo **HashiCorp Vault**, Azure Key Vault, AWS Secrets Manager o el gestor equivalente del entorno) para inyectar API keys, tokens y PSK en tiempo de ejecución.
- **Evitar almacenar credenciales en texto plano** en archivos de configuración versionados, logs o capturas de pantalla; usar `.env` solo local (y nunca commiteado) o secretos del pipeline CI/CD.
- **API tokens con permisos mínimos** necesarios (principio de menor privilegio): cuentas de servicio dedicadas, scopes limitados a objetos IKE/IPsec/rutas/políticas requeridos, y rotación periódica según política de seguridad.

### Logging

El script debería generar **logs estructurados** que incluyan, como mínimo:

- **Timestamp** (hora en zona acordada, preferible UTC en entornos distribuidos).
- **Dispositivo afectado** (por ejemplo `fortigate` / `palo_alto`, hostname o `mgmt_host`).
- **Acción ejecutada** (crear/actualizar Phase1, commit, validación, etc.).
- **Resultado** (`OK` / `ERROR`), y en error un mensaje o código sin exponer secretos.

Esto facilita **troubleshooting** (reproducir la secuencia de pasos) y **auditoría** (quién/qué cambió y cuándo, al integrarse con SIEM o repositorio de logs centralizado).

### Rollback

En caso de **fallo durante la automatización**:

- Se debería poder **revertir la configuración aplicada parcialmente** (por ejemplo eliminando solo los objetos creados en ese run, restaurando valores previos capturados antes del cambio, o aplicando un “snapshot”/backup de config previo si el entorno lo permite).
- **Alternativamente**, trabajar sobre configuraciones **candidate** antes de aplicar (especialmente en **Palo Alto**: cargar cambios en candidata, validar diff, **commit** solo si todo el flujo previo fue OK; en caso de error, **descartar** la candidata sin impactar el running).

Combinar **transacciones lógicas** (orden de creación reversible) con **checkpoints** por dispositivo reduce el riesgo de dejar el firewall en un estado inconsistente a mitad de script.

## 5) Validación de configuración y alertas (estrategia)

La validación debería cubrir **dos niveles**:

### 5.1 Validación de “config aplicada”

- **Fortigate** (vía API o comandos):
  - Verificar existencia y parámetros de Phase1/Phase2.
  - Verificar rutas y políticas relacionadas.
  - Verificar que la interfaz túnel tenga IP `169.254.1.1/30`.
- **Palo Alto** (vía API o comandos):
  - Verificar IKE Gateway, Crypto Profiles, Tunnel Interface `tunnel.1` con `169.254.1.2/30`.
  - Verificar rutas y policies.
  - Verificar que el commit se completó correctamente.

### 5.2 Validación de “túnel operativo”

- **Estado IKE/IPsec**:
  - SA establecidas (IKE SA e IPsec SA) en ambos extremos.
  - **Contadores de tráfico IPsec**: tomar una muestra **T0** de contadores (encaps/decaps u octets según el vendor), generar tráfico de prueba acotado hacia la red remota, y verificar que en **T1** los contadores **incrementan** de forma coherente (si no suben, el túnel puede estar “UP” en UI pero sin tráfico real o con política bloqueando).
- **Negociación sin errores típicos**:
  - Revisar logs/diagnósticos de IKE/IPsec y **fallar la validación** si aparecen errores recurrentes de negociación, por ejemplo **`NO_PROPOSAL_CHOSEN`** (desajuste Phase 1/2: algoritmos, DH/PFS, lifetimes) o **`AUTH_FAILED`** (PSK incorrecto, ID/local/peer ID, o política de autenticación).
  - Opcional: correlacionar con “último error” / reason del gateway en Palo Alto y mensajes equivalentes en Fortigate.
- **Prueba de conectividad**:
  - Ping desde una red a la otra (si ICMP permitido).
  - Alternativa: prueba TCP (ej. conectar a un puerto permitido) o traceroute.

### 5.3 Alertas

- Si falla cualquier paso:
  - Registrar error por dispositivo, con detalle (API/HTTP code, mensaje).
  - Generar “alerta” en salida (log) o UI (si se integra con el frontend de Parte 1 en el futuro).
- Si hay desviaciones:
  - Reportar “diff” (esperado vs actual) para propuestas, peer IP, subredes, rutas y policies.

## 6) Artefactos opcionales (para el repo)

- **Ejemplos de configuración** (conceptuales) para Fortigate y Palo Alto.
- **Script de prueba de conectividad** (conceptual) para validar que “algo” cruza el túnel en un entorno de prueba.

## 7) Estructura recomendada dentro del repositorio

- `part2/PLAN_VPN_IPSEC_FORTIGATE_PALOALTO.md` (este documento)
- `part2/examples/` (config de ejemplo)
- `part2/scripts/` (scripts opcionales: test de conectividad)

