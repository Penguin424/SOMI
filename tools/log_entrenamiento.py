"""Tool: log_entrenamiento — registra una sesión de entrenamiento de fuerza."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, crear_con_frontmatter, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "log_entrenamiento",
        "description": (
            "Registra una sesión de entrenamiento de fuerza en la bóveda. "
            "Úsala cuando el usuario describa ejercicios que hizo: series, repeticiones y peso. "
            "Cada ejercicio va como un objeto con series (número entero) y reps por serie."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ejercicios": {
                    "type": "array",
                    "description": "Lista de ejercicios realizados en la sesión.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {
                                "type": "string",
                                "description": "Nombre del ejercicio, ej: press banca, sentadilla.",
                            },
                            "series": {
                                "type": "integer",
                                "description": "Número de series realizadas, ej: 4.",
                            },
                            "reps": {
                                "description": (
                                    "Repeticiones por serie. "
                                    "Número entero o la cadena 'fallo' para fallo muscular."
                                ),
                            },
                            "peso": {
                                "type": "number",
                                "description": (
                                    "Peso usado. "
                                    "Omitir o pasar null para ejercicios de peso corporal."
                                ),
                            },
                            "unidad": {
                                "type": "string",
                                "description": "Unidad del peso. Por defecto: kg.",
                            },
                        },
                        "required": ["nombre", "series", "reps"],
                    },
                },
                "notas": {
                    "type": "string",
                    "description": "Observaciones generales de la sesión.",
                },
                "duracion_min": {
                    "type": "integer",
                    "description": "Duración total de la sesión en minutos.",
                },
            },
            "required": ["ejercicios"],
        },
    },
}


def _tabla_ejercicio(nombre: str, series: int, reps, peso=None, unidad: str = "kg") -> str:
    """Genera sección Markdown expandiendo el número de series en filas individuales."""
    lineas = [f"\n## {nombre.title()}\n"]

    if peso is not None:
        lineas.append("| Set | Peso | Reps |")
        lineas.append("|-----|------|------|")
        for i in range(1, series + 1):
            lineas.append(f"| {i} | {peso} {unidad} | {reps} |")
    else:
        lineas.append("| Set | Reps |")
        lineas.append("|-----|------|")
        for i in range(1, series + 1):
            lineas.append(f"| {i} | {reps} |")

    return "\n".join(lineas) + "\n"


def _descripcion_ejercicio(e: dict) -> str:
    """Genera descripción corta para el frontmatter, ej: 'press banca (4x8 @ 80 kg)'."""
    nombre = e.get("nombre", "sin nombre")
    series = e.get("series", "?")
    reps = e.get("reps", "?")
    peso = e.get("peso")
    unidad = e.get("unidad", "kg")
    if peso is not None:
        return f"{nombre} ({series}x{reps} @ {peso} {unidad})"
    return f"{nombre} ({series}x{reps})"


def ejecutar(
    ejercicios: list[dict],
    notas: str | None = None,
    duracion_min: int | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not ejercicios:
        return {"status": "error", "message": "Se requiere al menos un ejercicio."}

    fecha, hora = ahora()
    ruta = vault_path / "Fitness" / "Entrenamientos" / f"{fecha}.md"
    ya_existia = ruta.exists()

    if not ya_existia:
        descripciones = [_descripcion_ejercicio(e) for e in ejercicios]
        frontmatter: dict = {
            "tipo": "entrenamiento",
            "fecha": fecha,
            "hora": hora,
            "ejercicios": descripciones,
            "tags": [],
        }
        if duracion_min is not None:
            frontmatter["duracion_min"] = duracion_min
        try:
            crear_con_frontmatter(ruta, frontmatter)
        except Exception as exc:
            log_fn(f"tool=log_entrenamiento status=error message={exc}")
            return {"status": "error", "message": str(exc)}

    cuerpo = f"\n---\n\n## Sesión {hora}\n" if ya_existia else ""
    for ejercicio in ejercicios:
        nombre = ejercicio.get("nombre", "Sin nombre").strip()
        series = int(ejercicio.get("series", 1))
        reps = ejercicio.get("reps", "?")
        peso = ejercicio.get("peso")
        unidad = ejercicio.get("unidad", "kg")
        cuerpo += _tabla_ejercicio(nombre, series, reps, peso, unidad)

    if notas and notas.strip():
        cuerpo += f"\nNotas: {notas.strip()}\n"

    try:
        append_seguro(ruta, cuerpo)
    except Exception as exc:
        log_fn(f"tool=log_entrenamiento status=error message={exc}")
        return {"status": "error", "message": str(exc)}

    resumen = ", ".join(e.get("nombre", "?") for e in ejercicios)
    log_fn(
        f"tool=log_entrenamiento params={{ejercicios=[{resumen}], "
        f"duracion_min={duracion_min}}} status=ok result_path={ruta}"
    )
    return {
        "status": "ok",
        "message": f"Entrenamiento del {fecha} registrado: {resumen}.",
        "path": str(ruta),
    }
