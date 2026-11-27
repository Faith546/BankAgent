"""Chequeo de conectividad hacia Ollama (local o servidor remoto con GPU).

Uso:
    uv run python -m tests.check_ollama_connection
    OLLAMA_BASE_URL=http://<ip-servidor>:11434 uv run python -m tests.check_ollama_connection

Verifica: URL válida (http://), alcance y latencia de `/api/tags`, que el modelo del agente y el
de embeddings estén instalados, y los modelos cargados en VRAM (`/api/ps`). Si Ollama corre en
esta misma máquina y existe `nvidia-smi`, muestra también el uso de la GPU.
Código de salida: 0 = todo en orden, 1 = falla de conectividad o modelo faltante, 2 = URL inválida.
Solo usa la librería estándar y no modifica nada (solo lectura).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

TIMEOUT_S = 10.0
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def model_installed(configured: str, installed_names: list[str]) -> bool:
    """Indica si `configured` está instalado (Ollama añade `:latest` cuando no hay etiqueta)."""
    candidates = {configured, f"{configured}:latest"} if ":" not in configured else {configured}
    return any(name in candidates for name in installed_names)


def fetch_json(
    base_url: str, path: str, timeout: float = TIMEOUT_S
) -> tuple[dict[str, Any], float]:
    """GET a `base_url + path`; devuelve (json, latencia en segundos). Lanza OSError/ValueError."""
    t0 = time.perf_counter()
    with urllib.request.urlopen(f"{base_url}{path}", timeout=timeout) as resp:  # noqa: S310
        body = resp.read().decode("utf-8")
    return json.loads(body), time.perf_counter() - t0


def _gb(num_bytes: int | float) -> str:
    return f"{num_bytes / 1e9:.1f} GB"


def _print_local_gpu() -> None:
    if shutil.which("nvidia-smi") is None:
        print("      (nvidia-smi no disponible en esta máquina)")
        return
    try:
        out = subprocess.run(  # noqa: S603  (lista de argumentos fija, sin shell)
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
        print(f"      GPU (nvidia-smi): {out.stdout.strip() or out.stderr.strip()}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"      nvidia-smi falló: {exc}")


def run_checks() -> int:
    """Ejecuta los chequeos y devuelve el código de salida."""
    try:
        from src.config import (
            OLLAMA_BASE_URL,
            OLLAMA_EMBED_MODEL,
            OLLAMA_MODEL,
            OLLAMA_NUM_CTX,
        )
    except ValueError as exc:
        print(f"[FALLA] Configuración inválida: {exc}")
        return 2

    print(f"Ollama      : {OLLAMA_BASE_URL}")
    print(f"Modelo      : {OLLAMA_MODEL} (num_ctx={OLLAMA_NUM_CTX})")
    print(f"Embeddings  : {OLLAMA_EMBED_MODEL}")
    print("-" * 72)

    # [1/3] Conectividad y latencia
    print("[1/3] ¿Responde Ollama en /api/tags? (firewall/VPN/puerto)")
    try:
        tags, latency = fetch_json(OLLAMA_BASE_URL, "/api/tags")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"      FALLA: {exc}")
        print("      Revisa: ¿Ollama está corriendo? ¿VPN activa? ¿firewall del puerto 11434?")
        print("      Si Ollama solo escucha en localhost, usa un túnel SSH:")
        print("        ssh -L 11434:localhost:11434 usuario@servidor")
        return 1
    models = tags.get("models", [])
    names = [m.get("name", "") for m in models]
    print(f"      OK — latencia {latency * 1000:.0f} ms, {len(names)} modelos instalados")
    for m in models:
        print(f"        - {m.get('name')}  ({_gb(m.get('size', 0))})")

    # [2/3] Modelos requeridos
    print("[2/3] ¿Están instalados los modelos que usa el proyecto?")
    faltan: list[str] = []
    for label, name in (("agente", OLLAMA_MODEL), ("embeddings", OLLAMA_EMBED_MODEL)):
        ok = model_installed(name, names)
        print(f"      {'OK   ' if ok else 'FALTA'} {label}: {name}")
        if not ok:
            faltan.append(name)

    # [3/3] VRAM
    print("[3/3] Modelos cargados en memoria (VRAM) según /api/ps")
    try:
        ps, _ = fetch_json(OLLAMA_BASE_URL, "/api/ps")
        loaded = ps.get("models", [])
        if not loaded:
            print("      Ningún modelo cargado ahora (se cargan en la primera consulta).")
        for m in loaded:
            total, vram = m.get("size", 0), m.get("size_vram", 0)
            pct = (vram / total * 100) if total else 0.0
            print(
                f"      {m.get('name')}: {_gb(vram)} de {_gb(total)} en GPU ({pct:.0f}%)"
                + ("  <-- parte en RAM, irá más lento" if total and vram < total else "")
            )
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"      No se pudo leer /api/ps: {exc}")
    host = urlparse(OLLAMA_BASE_URL).hostname or ""
    if host in LOCAL_HOSTS:
        _print_local_gpu()
    else:
        print("      (servidor remoto: corre `nvidia-smi` por SSH para ver la VRAM total)")

    print("=" * 72)
    if faltan:
        print(f"RESULTADO: conexión OK, pero faltan modelos: {', '.join(faltan)}")
        print("           Instala con: ollama pull <modelo> (en el servidor)")
        return 1
    print("RESULTADO: conexión y modelos OK. Listo para correr el smoke test / benchmark.")
    return 0


def main() -> None:
    sys.exit(run_checks())


if __name__ == "__main__":
    main()
