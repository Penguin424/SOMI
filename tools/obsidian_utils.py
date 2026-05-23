"""Utilidades para leer y escribir archivos Markdown en la bóveda de Obsidian."""
from __future__ import annotations

import fcntl
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


def slugify(texto: str) -> str:
    """Convierte texto a slug apto para nombre de archivo."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    texto = re.sub(r"[^\w\s-]", "", texto)
    texto = re.sub(r"[\s_-]+", "-", texto)
    return texto.strip("-")


def construir_frontmatter(campos: dict[str, Any]) -> str:
    """Genera bloque YAML de frontmatter a partir de un dict."""
    lineas = ["---"]
    for clave, valor in campos.items():
        if isinstance(valor, list):
            if valor:
                lineas.append(f"{clave}:")
                for item in valor:
                    lineas.append(f"  - {item}")
            else:
                lineas.append(f"{clave}: []")
        elif valor is None:
            lineas.append(f"{clave}: ~")
        else:
            lineas.append(f"{clave}: {valor}")
    lineas.append("---")
    lineas.append("")
    return "\n".join(lineas)


def tiene_frontmatter(ruta: Path) -> bool:
    """Devuelve True si el archivo existe y empieza con frontmatter YAML."""
    if not ruta.exists():
        return False
    with open(ruta, encoding="utf-8") as f:
        primera = f.readline().strip()
    return primera == "---"


def append_seguro(ruta: Path, contenido: str) -> None:
    """Append con bloqueo exclusivo para evitar condiciones de carrera."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(contenido)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def crear_con_frontmatter(ruta: Path, frontmatter: dict[str, Any], cuerpo: str = "") -> None:
    """Crea un archivo nuevo con frontmatter YAML. No sobreescribe si ya existe."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        return
    texto = construir_frontmatter(frontmatter)
    if cuerpo:
        texto += cuerpo
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)


def asegurar_archivo(ruta: Path, frontmatter_inicial: dict[str, Any]) -> None:
    """Crea el archivo con frontmatter si no existe. Si ya existe, no lo toca."""
    if not tiene_frontmatter(ruta):
        crear_con_frontmatter(ruta, frontmatter_inicial)


def ahora() -> tuple[str, str]:
    """Devuelve (fecha YYYY-MM-DD, hora HH:MM) del momento actual."""
    dt = datetime.now()
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
