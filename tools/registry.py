"""Registro central de tools disponibles para Ollama."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from tools.entrada_diario import SCHEMA as _SCHEMA_DIARIO, ejecutar as _entrada_diario
from tools.agregar_pendiente import SCHEMA as _SCHEMA_PENDIENTE, ejecutar as _agregar_pendiente
from tools.guardar_snippet import SCHEMA as _SCHEMA_SNIPPET, ejecutar as _guardar_snippet
from tools.crear_nota import SCHEMA as _SCHEMA_NOTA, ejecutar as _crear_nota
from tools.log_entrenamiento import SCHEMA as _SCHEMA_ENTRENO, ejecutar as _log_entrenamiento
from tools.calificar_media import SCHEMA as _SCHEMA_MEDIA, ejecutar as _calificar_media
from tools.nota_ingles import SCHEMA as _SCHEMA_INGLES, ejecutar as _nota_ingles
from tools.buscar_en_vault import SCHEMA as _SCHEMA_BUSCAR, ejecutar as _buscar_en_vault
from tools.consultar_experto import SCHEMA as _SCHEMA_EXPERTO, ejecutar as _consultar_experto

_SCHEMAS: list[dict] = [
    _SCHEMA_DIARIO,
    _SCHEMA_PENDIENTE,
    _SCHEMA_SNIPPET,
    _SCHEMA_NOTA,
    _SCHEMA_ENTRENO,
    _SCHEMA_MEDIA,
    _SCHEMA_INGLES,
    _SCHEMA_BUSCAR,
    _SCHEMA_EXPERTO,
]

_FUNS: dict[str, Callable] = {
    "entrada_diario": _entrada_diario,
    "agregar_pendiente": _agregar_pendiente,
    "guardar_snippet": _guardar_snippet,
    "crear_nota": _crear_nota,
    "log_entrenamiento": _log_entrenamiento,
    "calificar_media": _calificar_media,
    "nota_ingles": _nota_ingles,
    "buscar_en_vault": _buscar_en_vault,
    "consultar_experto": _consultar_experto,
}


def schemas_para_ollama() -> list[dict]:
    """Devuelve la lista de schemas lista para pasarle a Ollama."""
    return _SCHEMAS


def _reparar_json_truncado(s: str) -> str:
    """Añade los brackets/llaves de cierre que Llama 3.1 omite al truncar la respuesta."""
    stack: list[str] = []
    en_string = False
    escape_next = False

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and en_string:
            escape_next = True
            continue
        if ch == '"':
            en_string = not en_string
            continue
        if en_string:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    cierre = {"{": "}", "[": "]"}
    for abierto in reversed(stack):
        s += cierre[abierto]
    return s


def _deserializar_arg(valor: Any) -> Any:
    """Convierte strings JSON a listas/dicts.
    Llama 3.1 8B tiene dos comportamientos problemáticos con arrays:
    - Los serializa como strings en lugar de objetos nativos.
    - Los trunca antes del bracket de cierre cuando el contenido es largo.
    """
    if not isinstance(valor, str):
        return valor
    stripped = valor.strip()
    if not stripped.startswith(("[", "{")):
        return valor
    # Intento 1: JSON válido
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Intento 2: JSON truncado — añadir los cierres que faltan
    try:
        return json.loads(_reparar_json_truncado(stripped))
    except json.JSONDecodeError:
        pass
    return valor


def ejecutar_tool(nombre: str, argumentos: dict, cfg: dict) -> dict:
    """Ejecuta la tool indicada con los argumentos de Ollama."""
    if nombre not in _FUNS:
        return {"status": "error", "message": f"Tool '{nombre}' no registrada."}

    vault_path = Path(cfg["vault"]["path"])
    log_fn = _crear_log_fn(Path(os.path.expanduser(cfg["tools"]["log_file"])))

    # Llama 3.1 8B a veces devuelve arrays como strings JSON — normalizamos antes de llamar
    argumentos_norm = {k: _deserializar_arg(v) for k, v in argumentos.items()}

    try:
        return _FUNS[nombre](**argumentos_norm, vault_path=vault_path, log_fn=log_fn)
    except TypeError as exc:
        msg = f"Parámetros incorrectos para '{nombre}': {exc}"
        log_fn(f"tool={nombre} status=error message={msg}")
        return {"status": "error", "message": msg}
    except Exception as exc:
        msg = str(exc)
        log_fn(f"tool={nombre} status=error message={msg}")
        return {"status": "error", "message": msg}


def _crear_log_fn(log_file: Path) -> Callable[[str], None]:
    def log(msg: str) -> None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    return log
