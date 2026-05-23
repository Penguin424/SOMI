"""Tool: consultar_experto — consulta a Claude o Gemini via CLI."""
from __future__ import annotations

import subprocess
from typing import Callable

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "consultar_experto",
        "description": (
            "Consulta a una IA externa (Claude o Gemini) para obtener una segunda opinión "
            "o información especializada. Úsala cuando el usuario pida explícitamente "
            "consultar a Claude, a Gemini, o a 'otra IA'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pregunta": {
                    "type": "string",
                    "description": "La pregunta o consulta a enviar al experto externo.",
                },
                "experto": {
                    "type": "string",
                    "description": (
                        "Qué IA consultar: 'claude', 'gemini', o 'ambos'. "
                        "Por defecto: 'claude'."
                    ),
                },
            },
            "required": ["pregunta"],
        },
    },
}

_TIMEOUT = 120    # Gemini puede tardar >60s con reintentos de quota
_MAX_CHARS = 2000

_CLI: dict[str, list[str]] = {
    "claude": ["claude", "-p"],
    "gemini": ["gemini", "-m", "gemini-2.5-flash", "-p"],
}


def _llamar_cli(nombre: str, pregunta: str) -> dict:
    cmd = _CLI[nombre] + [pregunta]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            stdin=subprocess.DEVNULL,   # evita bloqueo esperando stdin en modo no-interactivo
        )
    except subprocess.TimeoutExpired:
        return {"experto": nombre, "status": "error", "message": f"{nombre} no respondió en {_TIMEOUT}s (puede haber límite de cuota)."}
    except FileNotFoundError:
        return {"experto": nombre, "status": "error", "message": f"CLI '{nombre}' no está instalado."}

    if result.returncode != 0:
        stderr = result.stderr.strip()[:200]
        return {"experto": nombre, "status": "error", "message": stderr or f"{nombre} devolvió código {result.returncode}."}

    respuesta = result.stdout.strip()
    if not respuesta:
        return {"experto": nombre, "status": "error", "message": f"{nombre} no devolvió respuesta."}

    if len(respuesta) > _MAX_CHARS:
        respuesta = respuesta[:_MAX_CHARS] + "..."

    return {"experto": nombre, "status": "ok", "respuesta": respuesta}


def ejecutar(
    pregunta: str,
    experto: str = "claude",
    *,
    log_fn: Callable[[str], None],
    **_kwargs,
) -> dict:
    if not pregunta or not pregunta.strip():
        return {"status": "error", "message": "La pregunta no puede estar vacía."}

    experto = experto.strip().lower()
    if experto not in ("claude", "gemini", "ambos"):
        experto = "claude"

    if experto == "ambos":
        resultados = [_llamar_cli("claude", pregunta), _llamar_cli("gemini", pregunta)]
        ok = [r for r in resultados if r["status"] == "ok"]
        errores = [r for r in resultados if r["status"] == "error"]
        log_fn(
            f"tool=consultar_experto experto=ambos status=ok "
            f"ok={len(ok)} errores={len(errores)}"
        )
        return {"status": "ok", "experto": "ambos", "resultados": resultados}

    resultado = _llamar_cli(experto, pregunta)
    log_fn(
        f"tool=consultar_experto experto={experto} status={resultado['status']}"
    )
    return resultado
