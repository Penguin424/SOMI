"""Tool: entrada_diario — anexa una entrada al diario del día."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, asegurar_archivo, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "entrada_diario",
        "description": (
            "Anexa una entrada al diario personal del día de hoy. "
            "Úsala cuando el usuario quiera anotar algo en su diario, "
            "registrar un evento, una reflexión, una idea o su estado de ánimo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "contenido": {
                    "type": "string",
                    "description": "Texto de la entrada a guardar en el diario.",
                },
                "tag": {
                    "type": "string",
                    "enum": ["reflexion", "evento", "idea", "animo"],
                    "description": "Categoría opcional de la entrada.",
                },
            },
            "required": ["contenido"],
        },
    },
}


def ejecutar(
    contenido: str,
    tag: str | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not contenido or not contenido.strip():
        return {"status": "error", "message": "El contenido no puede estar vacío."}

    fecha, hora = ahora()
    ruta = vault_path / "Diario" / f"{fecha}.md"

    asegurar_archivo(ruta, {
        "tipo": "diario",
        "fecha": fecha,
        "hora": hora,
        "tags": [],
    })

    entrada = f"\n## {hora}\n{contenido.strip()}"
    if tag:
        entrada += f"\n#{tag}"
    entrada += "\n"

    try:
        append_seguro(ruta, entrada)
    except Exception as exc:
        log_fn(f"tool=entrada_diario params={{tag={tag}}} status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    log_fn(
        f"tool=entrada_diario params={{contenido='{contenido[:50]}', tag={tag}}} "
        f"status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"Entrada agregada al diario del {fecha}.",
        "path": str(ruta),
    }
