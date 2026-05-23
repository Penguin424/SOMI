"""Tool: crear_nota — crea una nota libre en la bóveda."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from tools.obsidian_utils import crear_con_frontmatter, slugify, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "crear_nota",
        "description": (
            "Crea una nota nueva en la bóveda de Obsidian para contenido que no encaja "
            "en el diario, pendientes u otras categorías. Útil para guardar resúmenes, "
            "respuestas largas, ideas sueltas o cualquier texto libre."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titulo": {
                    "type": "string",
                    "description": "Título de la nota. Se usa también como nombre de archivo.",
                },
                "contenido": {
                    "type": "string",
                    "description": "Cuerpo de la nota.",
                },
                "carpeta": {
                    "type": "string",
                    "description": "Carpeta donde crear la nota. Por defecto: Inbox.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Etiquetas opcionales.",
                },
            },
            "required": ["titulo", "contenido"],
        },
    },
}


def ejecutar(
    titulo: str,
    contenido: str,
    carpeta: str | None = None,
    tags: list[str] | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not titulo or not titulo.strip():
        return {"status": "error", "message": "El título no puede estar vacío."}
    if not contenido or not contenido.strip():
        return {"status": "error", "message": "El contenido no puede estar vacío."}

    fecha, hora = ahora()
    carpeta_final = (carpeta or "Inbox").strip().rstrip("/")
    slug = slugify(titulo.strip())
    ruta = vault_path / carpeta_final / f"{slug}.md"

    # Evita sobreescribir: añade timestamp al nombre si ya existe
    if ruta.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        ruta = vault_path / carpeta_final / f"{slug}_{ts}.md"

    frontmatter = {
        "tipo": "nota",
        "titulo": titulo.strip(),
        "fecha": fecha,
        "hora": hora,
        "tags": tags or [],
    }
    cuerpo = f"# {titulo.strip()}\n\n{contenido.strip()}\n"

    try:
        crear_con_frontmatter(ruta, frontmatter, cuerpo)
    except Exception as exc:
        log_fn(f"tool=crear_nota params={{titulo='{titulo[:50]}'}} status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    log_fn(
        f"tool=crear_nota params={{titulo='{titulo[:50]}', carpeta={carpeta_final}}} "
        f"status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"Nota '{titulo}' creada en {carpeta_final}.",
        "path": str(ruta),
    }
