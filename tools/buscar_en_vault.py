"""Tool: buscar_en_vault — busca texto en la bóveda usando ripgrep."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "buscar_en_vault",
        "description": (
            "Busca información en la bóveda de Obsidian. "
            "Úsala cuando el usuario haga preguntas sobre contenido que ya guardó: "
            "'¿qué tengo pendiente?', '¿cuánto levanté la semana pasada?', "
            "'¿qué películas he calificado?', '¿anotaste algo sobre X?'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Texto a buscar. "
                        "Para pendientes sin completar usa '- [ ]'. "
                        "Para buscar por nombre de ejercicio, película, etc., usa ese nombre."
                    ),
                },
                "tipo": {
                    "type": "string",
                    "description": (
                        "Filtra la búsqueda por tipo de nota: "
                        "diario, entrenamiento, pendiente, snippet, media, vocabulario, gramatica, nota."
                    ),
                },
                "max_resultados": {
                    "type": "integer",
                    "description": "Número máximo de archivos a devolver. Por defecto: 5.",
                },
            },
            "required": ["query"],
        },
    },
}

_TIMEOUT = 10
_MAX_CHARS_POR_RESULTADO = 800


def _archivos_por_tipo(vault_path: Path, tipo: str) -> list[Path]:
    """Devuelve los .md cuyo frontmatter contiene 'tipo: X'."""
    cmd = ["rg", "--type", "md", "-l", f"^tipo: {tipo}", str(vault_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
    if result.returncode != 0:
        return []
    return [Path(p) for p in result.stdout.strip().splitlines() if p]


def _parsear_json_rg(salida: str, vault_path: Path, max_resultados: int) -> list[dict]:
    """Convierte la salida JSON de rg en lista de resultados por archivo."""
    grupos: dict[str, list[str]] = {}

    for linea in salida.splitlines():
        if not linea.strip():
            continue
        try:
            obj = json.loads(linea)
        except json.JSONDecodeError:
            continue

        if obj.get("type") not in ("match", "context"):
            continue

        data = obj["data"]
        archivo = data["path"]["text"]
        texto = data["lines"]["text"].rstrip("\n")

        if archivo not in grupos:
            grupos[archivo] = []
        grupos[archivo].append(texto)

    resultados = []
    for archivo, lineas in list(grupos.items())[:max_resultados]:
        try:
            ruta_rel = str(Path(archivo).relative_to(vault_path))
        except ValueError:
            ruta_rel = archivo

        contenido = "\n".join(lineas)
        if len(contenido) > _MAX_CHARS_POR_RESULTADO:
            contenido = contenido[:_MAX_CHARS_POR_RESULTADO] + "..."

        resultados.append({"archivo": ruta_rel, "contenido": contenido})

    return resultados


def ejecutar(
    query: str,
    tipo: str | None = None,
    max_resultados: int = 5,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not query or not query.strip():
        return {"status": "error", "message": "La búsqueda no puede estar vacía."}

    max_resultados = max(1, min(max_resultados, 20))

    try:
        if tipo:
            archivos = _archivos_por_tipo(vault_path, tipo)
            if not archivos:
                log_fn(f"tool=buscar_en_vault params={{query='{query[:40]}', tipo={tipo}}} status=ok resultados=0")
                return {
                    "status": "ok",
                    "resultados": [],
                    "mensaje": f"No hay archivos de tipo '{tipo}' en la bóveda.",
                }
            cmd = [
                "rg", "--json", "--fixed-strings", "--ignore-case",
                "--context", "2", "--max-count", "5",
                "--", query.strip(),
            ] + [str(f) for f in archivos]
        else:
            cmd = [
                "rg", "--json", "--fixed-strings", "--type", "md", "--ignore-case",
                "--context", "2", "--max-count", "5",
                "--", query.strip(), str(vault_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)

    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "La búsqueda tardó demasiado (más de 10s)."}
    except FileNotFoundError:
        return {"status": "error", "message": "ripgrep (rg) no está instalado."}

    if result.returncode == 2:
        return {"status": "error", "message": result.stderr[:200]}

    if result.returncode == 1 or not result.stdout.strip():
        log_fn(f"tool=buscar_en_vault params={{query='{query[:40]}', tipo={tipo}}} status=ok resultados=0")
        return {
            "status": "ok",
            "resultados": [],
            "mensaje": f"No se encontró '{query}' en la bóveda.",
        }

    resultados = _parsear_json_rg(result.stdout, vault_path, max_resultados)

    log_fn(
        f"tool=buscar_en_vault params={{query='{query[:40]}', tipo={tipo}}} "
        f"status=ok resultados={len(resultados)}"
    )
    return {
        "status": "ok",
        "query": query,
        "resultados": resultados,
        "total_archivos": len(resultados),
    }
