from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import datetime


def tcp_probe(host: str, port: int, timeout_s: float) -> tuple[bool, str]:
    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            latency = round((time.time() - start) * 1000, 2)
            return True, f"OK ({latency} ms)"
    except Exception as e:
        return False, str(e)


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Prueba simple de conectividad 'a través del túnel' usando TCP connect. "
            "Útil en entornos donde ICMP está bloqueado o requiere privilegios."
        )
    )
    p.add_argument("--host", required=True, help="IP/host del destino en la red remota")
    p.add_argument("--port", type=int, default=443, help="Puerto TCP a probar (default 443)")
    p.add_argument("--retries", type=int, default=5, help="Reintentos (default 5)")
    p.add_argument("--timeout", type=float, default=3.0, help="Timeout por intento en segundos (default 3)")
    p.add_argument("--sleep", type=float, default=1.0, help="Espera entre intentos (default 1)")
    p.add_argument("--json", action="store_true", help="Salida en formato JSON (una línea en stdout)")
    args = p.parse_args()

    def log(msg):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dest = sys.stderr if args.json else sys.stdout
        print(f"[{now}] {msg}", file=dest)

    log(f"Inicio prueba TCP → {args.host}:{args.port} (reintentos={args.retries}, timeout={args.timeout}s)")

    ok = False
    msg = ""
    for i in range(1, args.retries + 1):
        ok, msg = tcp_probe(args.host, args.port, args.timeout)
        status = "PASS" if ok else "FAIL"
        log(f"[{i}/{args.retries}] {status} {args.host}:{args.port} - {msg}")
        if ok:
            log("Conectividad OK.")
            break
        if i < args.retries:
            time.sleep(args.sleep)

    if not ok:
        log("Sin conectividad tras todos los reintentos.")

    if args.json:
        result = {
            "host": args.host,
            "port": args.port,
            "success": ok,
            "message": msg,
            "test": "tcp_connectivity_end_to_end",
            "ipsec_state_from_device": False,
            "note": (
                "success=true significa que el TCP al host:puerto respondió. "
                "No consulta CLI/API ni estado IKE/IPsec en Fortigate/Palo Alto; "
                "para eso ver el plan (validación en §5) o comandos tipo vpn ipsec / ipsec tunnel."
            ),
        }
        print(json.dumps(result, ensure_ascii=True))

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
