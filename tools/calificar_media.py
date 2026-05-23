"""Tool: calificar_media — añade una calificación a la tabla de series o películas."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, asegurar_archivo, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "calificar_media",
        "description": (
            "Registra una calificación de una serie o película en la bóveda. "
            "Úsala cuando el usuario califique algo que vio, mencione una puntuación "
            "o quiera anotar su opinión sobre una serie o película."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["serie", "pelicula"],
                    "description": "Si es una serie o una película.",
                },
                "titulo": {
                    "type": "string",
                    "description": "Título de la serie o película.",
                },
                "calificacion": {
                    "type": "number",
                    "description": "Puntuación del 0 al 10.",
                },
                "temporada": {
                    "type": "integer",
                    "description": "Número de temporada. Solo para series.",
                },
                "episodio": {
                    "type": "integer",
                    "description": "Número de episodio. Solo para series.",
                },
                "comentario": {
                    "type": "string",
                    "description": "Comentario breve opcional.",
                },
                "fecha_visto": {
                    "type": "string",
                    "description": "Fecha en formato YYYY-MM-DD. Por defecto: hoy.",
                },
            },
            "required": ["tipo", "titulo", "calificacion"],
        },
    },
}

_CABECERA_SERIES = (
    "| Título | Temporada | Episodio | Calificación | Fecha | Comentario |\n"
    "|--------|-----------|----------|--------------|-------|------------|\n"
)
_CABECERA_PELICULAS = (
    "| Título | Calificación | Fecha | Comentario |\n"
    "|--------|--------------|-------|------------|\n"
)


def ejecutar(
    tipo: str,
    titulo: str,
    calificacion: float,
    temporada: int | None = None,
    episodio: int | None = None,
    comentario: str | None = None,
    fecha_visto: str | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not titulo or not titulo.strip():
        return {"status": "error", "message": "El título no puede estar vacío."}
    if tipo not in ("serie", "pelicula"):
        return {"status": "error", "message": f"Tipo '{tipo}' no válido. Usa 'serie' o 'pelicula'."}
    if not (0 <= calificacion <= 10):
        return {"status": "error", "message": "La calificación debe estar entre 0 y 10."}

    fecha, hora = ahora()
    fecha_registro = fecha_visto or fecha
    comentario_str = (comentario or "").strip()
    cal_str = f"{calificacion:.1f}"

    if tipo == "serie":
        ruta = vault_path / "Media" / "Series.md"
        fila = (
            f"| {titulo.strip()} | {temporada or '-'} | {episodio or '-'} "
            f"| {cal_str} | {fecha_registro} | {comentario_str} |\n"
        )
        cabecera = _CABECERA_SERIES
        frontmatter = {"tipo": "media", "subtipo": "series", "fecha": fecha, "hora": hora, "tags": []}
    else:
        ruta = vault_path / "Media" / "Peliculas.md"
        fila = f"| {titulo.strip()} | {cal_str} | {fecha_registro} | {comentario_str} |\n"
        cabecera = _CABECERA_PELICULAS
        frontmatter = {"tipo": "media", "subtipo": "peliculas", "fecha": fecha, "hora": hora, "tags": []}

    archivo_nuevo = not ruta.exists()
    asegurar_archivo(ruta, frontmatter)

    # La cabecera solo se escribe la primera vez que se crea el archivo
    contenido = (cabecera + fila) if archivo_nuevo else fila

    try:
        append_seguro(ruta, contenido)
    except Exception as exc:
        log_fn(f"tool=calificar_media params={{titulo='{titulo[:50]}'}} status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    log_fn(
        f"tool=calificar_media params={{tipo={tipo}, titulo='{titulo[:50]}', "
        f"calificacion={calificacion}}} status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"{titulo} ({tipo}) calificada con {cal_str}/10.",
        "path": str(ruta),
    }
