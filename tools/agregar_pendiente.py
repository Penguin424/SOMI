"""Tool: agregar_pendiente — añade una tarea a Pendientes.md."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, asegurar_archivo, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "agregar_pendiente",
        "description": (
            "Añade una tarea pendiente al archivo de pendientes del usuario. "
            "Úsala cuando el usuario mencione algo que tiene que hacer, "
            "quiera que le recuerdes algo o tenga una tarea nueva."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tarea": {
                    "type": "string",
                    "description": "Descripción de la tarea a agregar.",
                },
                "prioridad": {
                    "type": "string",
                    "enum": ["alta", "media", "baja"],
                    "description": "Prioridad de la tarea. Por defecto: media.",
                },
                "fecha_limite": {
                    "type": "string",
                    "description": "Fecha límite en formato YYYY-MM-DD.",
                },
                "contexto": {
                    "type": "string",
                    "description": "Contexto de la tarea, por ejemplo: trabajo, casa, compras.",
                },
            },
            "required": ["tarea"],
        },
    },
}

_EMOJI_PRIORIDAD = {
    "alta": "🔴",
    "media": "🟡",
    "baja": "🟢",
}


def ejecutar(
    tarea: str,
    prioridad: str | None = None,
    fecha_limite: str | None = None,
    contexto: str | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not tarea or not tarea.strip():
        return {"status": "error", "message": "La tarea no puede estar vacía."}

    fecha, hora = ahora()
    ruta = vault_path / "Pendientes.md"

    asegurar_archivo(ruta, {
        "tipo": "pendiente",
        "fecha": fecha,
        "hora": hora,
        "tags": [],
    })

    linea = f"- [ ] {tarea.strip()}"
    if prioridad and prioridad in _EMOJI_PRIORIDAD:
        linea += f" {_EMOJI_PRIORIDAD[prioridad]} #{prioridad}"
    if fecha_limite:
        linea += f" 📅 {fecha_limite}"
    if contexto:
        linea += f" #{contexto}"
    linea += "\n"

    try:
        append_seguro(ruta, linea)
    except Exception as exc:
        log_fn(f"tool=agregar_pendiente params={{tarea='{tarea[:50]}'}} status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    log_fn(
        f"tool=agregar_pendiente params={{tarea='{tarea[:50]}', prioridad={prioridad}, "
        f"fecha_limite={fecha_limite}, contexto={contexto}}} status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"Tarea '{tarea}' agregada a pendientes.",
        "path": str(ruta),
    }
