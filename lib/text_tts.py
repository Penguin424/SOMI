"""Normalización de texto para TTS.

F5-Spanish lee literalmente lo que recibe: cifras, símbolos y markdown salen
con dicción pobre o entrecortada. Esta capa convierte el texto del LLM a algo
que el modelo pronuncie limpio y en español (números a palabras, símbolos a
palabras, sin markdown ni emojis).
"""
from __future__ import annotations

import re

from num2words import num2words

# Emojis y pictogramas (rangos Unicode comunes)
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # símbolos suplementarios y emoticonos
    "\U00002600-\U000027BF"   # misc symbols + dingbats
    "\U00002190-\U000021FF"   # flechas
    "\U00002B00-\U00002BFF"   # flechas/figuras
    "\U0000FE00-\U0000FE0F"   # selectores de variación
    "\U00002022"              # bullet •
    "]",
    flags=re.UNICODE,
)

# Símbolos que suenan mejor como palabra (o que conviene silenciar)
_SIMBOLOS = {
    "%": " por ciento ",
    "&": " y ",
    "+": " más ",
    "=": " igual ",
    "@": " arroba ",
    "°": " grados ",
    "º": " grados ",
    "€": " euros ",
    "$": " dólares ",
    "/": " ",
    "#": " ",
    "*": " ",
    "_": " ",
    "`": " ",
    "~": " ",
    "|": " ",
    "<": " ",
    ">": " ",
    "^": " ",
}

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _num_a_palabras(match: "re.Match[str]") -> str:
    token = match.group(0)
    try:
        if "." in token or "," in token:
            return num2words(float(token.replace(",", ".")), lang="es")
        return num2words(int(token), lang="es")
    except Exception:
        return token


def normalizar_para_tts(texto: str) -> str:
    """Devuelve el texto listo para F5-Spanish: español plano, sin cifras ni símbolos."""
    if not texto:
        return texto

    t = texto

    # 1. Quitar emojis y pictogramas
    t = _EMOJI.sub("", t)

    # 2. Desenfatizar markdown conservando el contenido (**x**, *x*, `x`)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"\*(.+?)\*", r"\1", t)
    t = re.sub(r"`(.+?)`", r"\1", t)

    # 3. Quitar viñetas al inicio de línea ("- algo", "* algo")
    t = re.sub(r"(?m)^\s*[-*•]\s+", "", t)

    # 4. Horas y rangos: separar el ':' entre dígitos ("20:30" -> "20 30")
    t = re.sub(r"(?<=\d):(?=\d)", " ", t)

    # 5. Símbolos -> palabras
    for sim, rep in _SIMBOLOS.items():
        t = t.replace(sim, rep)

    # 6. Números -> palabras en español
    t = _NUM_RE.sub(_num_a_palabras, t)

    # 7. Colapsar espacios y saltos sobrantes
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r" *\n *", "\n", t)

    return t.strip()
