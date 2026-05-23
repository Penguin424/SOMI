"""Tool: nota_ingles — registra aprendizaje de inglés en la bóveda."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from tools.obsidian_utils import append_seguro, asegurar_archivo, crear_con_frontmatter, ahora

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "nota_ingles",
        "description": (
            "Registra un aprendizaje de inglés: vocabulario, gramática, expresiones o notas. "
            "Úsala cuando el usuario quiera guardar una palabra nueva, una expresión, "
            "una regla gramatical o cualquier apunte de inglés."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "enum": ["vocabulario", "gramatica", "expresion", "nota_general"],
                    "description": "Tipo de aprendizaje a registrar.",
                },
                "contenido": {
                    "type": "string",
                    "description": (
                        "La palabra, expresión o tema. "
                        "Para vocabulario: la palabra en inglés. "
                        "Para gramática: el tema o regla. "
                        "Para expresión: la frase en inglés."
                    ),
                },
                "traduccion": {
                    "type": "string",
                    "description": "Traducción al español.",
                },
                "ejemplo": {
                    "type": "string",
                    "description": "Frase de ejemplo en inglés.",
                },
            },
            "required": ["categoria", "contenido"],
        },
    },
}


def _agregar_vocabulario(
    contenido: str,
    traduccion: str | None,
    ejemplo: str | None,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    fecha, hora = ahora()
    ruta = vault_path / "Ingles" / "Vocabulario.md"
    asegurar_archivo(ruta, {"tipo": "vocabulario", "fecha": fecha, "hora": hora, "tags": []})

    partes = [contenido.strip()]
    partes.append(traduccion.strip() if traduccion else "")
    partes.append(ejemplo.strip() if ejemplo else "")
    linea = " :: ".join(partes) + "\n"

    append_seguro(ruta, linea)
    log_fn(f"tool=nota_ingles params={{categoria=vocabulario, contenido='{contenido[:40]}'}} status=ok result_path={ruta}")
    return {"status": "ok", "message": f"Vocabulario '{contenido}' guardado.", "path": str(ruta)}


def _agregar_expresion(
    contenido: str,
    traduccion: str | None,
    ejemplo: str | None,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    fecha, hora = ahora()
    ruta = vault_path / "Ingles" / "Vocabulario.md"
    asegurar_archivo(ruta, {"tipo": "vocabulario", "fecha": fecha, "hora": hora, "tags": []})

    partes = [contenido.strip()]
    partes.append(traduccion.strip() if traduccion else "")
    partes.append(ejemplo.strip() if ejemplo else "")
    # El prefijo [expr] distingue expresiones de palabras sueltas para Spaced Repetition
    linea = "[expr] " + " :: ".join(partes) + "\n"

    append_seguro(ruta, linea)
    log_fn(f"tool=nota_ingles params={{categoria=expresion, contenido='{contenido[:40]}'}} status=ok result_path={ruta}")
    return {"status": "ok", "message": f"Expresión '{contenido}' guardada.", "path": str(ruta)}


def _agregar_gramatica(
    contenido: str,
    ejemplo: str | None,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    fecha, hora = ahora()
    ruta = vault_path / "Ingles" / "Gramatica.md"
    asegurar_archivo(ruta, {"tipo": "gramatica", "fecha": fecha, "hora": hora, "tags": []})

    seccion = f"\n## {contenido.strip()}\n"
    if ejemplo and ejemplo.strip():
        seccion += f"Ejemplo: {ejemplo.strip()}\n"

    append_seguro(ruta, seccion)
    log_fn(f"tool=nota_ingles params={{categoria=gramatica, contenido='{contenido[:40]}'}} status=ok result_path={ruta}")
    return {"status": "ok", "message": f"Nota de gramática '{contenido}' guardada.", "path": str(ruta)}


def _crear_nota_general(
    contenido: str,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    fecha, hora = ahora()
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    ruta = vault_path / "Ingles" / "Notas" / f"{ts}.md"
    frontmatter = {"tipo": "nota", "fecha": fecha, "hora": hora, "tags": ["ingles"]}
    crear_con_frontmatter(ruta, frontmatter, contenido.strip() + "\n")

    log_fn(f"tool=nota_ingles params={{categoria=nota_general}} status=ok result_path={ruta}")
    return {"status": "ok", "message": "Nota de inglés creada.", "path": str(ruta)}


def ejecutar(
    categoria: str,
    contenido: str,
    traduccion: str | None = None,
    ejemplo: str | None = None,
    *,
    vault_path: Path,
    log_fn: Callable[[str], None],
) -> dict:
    if not contenido or not contenido.strip():
        return {"status": "error", "message": "El contenido no puede estar vacío."}

    if categoria == "vocabulario":
        return _agregar_vocabulario(contenido, traduccion, ejemplo, vault_path, log_fn)
    if categoria == "expresion":
        return _agregar_expresion(contenido, traduccion, ejemplo, vault_path, log_fn)
    if categoria == "gramatica":
        return _agregar_gramatica(contenido, ejemplo, vault_path, log_fn)
    if categoria == "nota_general":
        return _crear_nota_general(contenido, vault_path, log_fn)

    return {"status": "error", "message": f"Categoría '{categoria}' no válida."}
