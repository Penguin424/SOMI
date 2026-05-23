"""Tool: guardar_snippet — guarda un comando o configuración técnica en la bóveda."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, asegurar_archivo, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "guardar_snippet",
        "description": (
            "Guarda un comando, configuración o snippet técnico en la bóveda de Obsidian. "
            "Úsala cuando el usuario quiera guardar un comando de terminal, una config, "
            "un script, o cualquier texto técnico para referencia futura."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "enum": ["linux", "proton", "git", "hyprland", "otro"],
                    "description": "Categoría del snippet.",
                },
                "titulo": {
                    "type": "string",
                    "description": "Título descriptivo del snippet.",
                },
                "contenido": {
                    "type": "string",
                    "description": "El comando o código a guardar.",
                },
                "descripcion": {
                    "type": "string",
                    "description": "Descripción breve de para qué sirve el snippet.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquetas opcionales.",
                },
            },
            "required": ["categoria", "titulo", "contenido"],
        },
    },
}

_ARCHIVO_POR_CATEGORIA: dict[str, str] = {
    "linux": "Linux.md",
    "proton": "Proton.md",
    "git": "Git.md",
    "hyprland": "Hyprland.md",
    "otro": "Otros.md",
}


def ejecutar(
    categoria: str,
    titulo: str,
    contenido: str,
    descripcion: str | None = None,
    tags: list[str] | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not titulo or not titulo.strip():
        return {"status": "error", "message": "El título no puede estar vacío."}
    if not contenido or not contenido.strip():
        return {"status": "error", "message": "El contenido no puede estar vacío."}
    if categoria not in _ARCHIVO_POR_CATEGORIA:
        return {"status": "error", "message": f"Categoría '{categoria}' no válida."}

    fecha, hora = ahora()
    nombre_archivo = _ARCHIVO_POR_CATEGORIA[categoria]
    ruta = vault_path / "Snippets" / nombre_archivo

    asegurar_archivo(ruta, {
        "tipo": "snippet",
        "categoria": categoria,
        "fecha": fecha,
        "hora": hora,
        "tags": [],
    })

    seccion = f"\n## {titulo.strip()}\n"
    if descripcion and descripcion.strip():
        seccion += f"{descripcion.strip()}\n"
    seccion += f"```bash\n{contenido.strip()}\n```\n"
    if tags:
        tags_str = " ".join(f"#{t}" for t in tags if t.strip())
        if tags_str:
            seccion += f"Tags: {tags_str}\n"

    try:
        append_seguro(ruta, seccion)
    except Exception as exc:
        log_fn(f"tool=guardar_snippet params={{titulo='{titulo[:50]}'}} status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    log_fn(
        f"tool=guardar_snippet params={{categoria={categoria}, titulo='{titulo[:50]}'}} "
        f"status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"Snippet '{titulo}' guardado en Snippets/{nombre_archivo}.",
        "path": str(ruta),
    }
