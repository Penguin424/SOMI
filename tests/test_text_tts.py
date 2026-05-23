"""Tests de la normalización de texto para TTS."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from text_tts import normalizar_para_tts


class TestNumeros:
    def test_entero_a_palabras(self) -> None:
        assert "ochenta" in normalizar_para_tts("levanté 80 kilos")
        assert "80" not in normalizar_para_tts("levanté 80 kilos")

    def test_decimal_a_palabras(self) -> None:
        out = normalizar_para_tts("le doy 8.5")
        assert "ocho" in out and "cinco" in out
        assert "8.5" not in out

    def test_decimal_con_coma(self) -> None:
        out = normalizar_para_tts("le doy 8,5")
        assert "ocho" in out and "cinco" in out

    def test_anio(self) -> None:
        assert "dos mil veintiséis" in normalizar_para_tts("salió en 2026")


class TestSimbolos:
    def test_porcentaje(self) -> None:
        out = normalizar_para_tts("60% de humedad")
        assert "por ciento" in out
        assert "%" not in out

    def test_grados(self) -> None:
        out = normalizar_para_tts("25°C")
        assert "grados" in out
        assert "°" not in out

    def test_ampersand(self) -> None:
        out = normalizar_para_tts("tú & yo")
        assert "&" not in out
        assert " y " in out


class TestMarkdownYEmojis:
    def test_negritas(self) -> None:
        out = normalizar_para_tts("esto es **importante**")
        assert "importante" in out
        assert "*" not in out

    def test_cursivas(self) -> None:
        out = normalizar_para_tts("esto es *clave*")
        assert "clave" in out
        assert "*" not in out

    def test_emoji_eliminado(self) -> None:
        out = normalizar_para_tts("buen trabajo 🔥💪")
        assert "🔥" not in out
        assert "💪" not in out
        assert "buen trabajo" in out

    def test_vinetas(self) -> None:
        out = normalizar_para_tts("- primero\n- segundo")
        assert not out.startswith("-")


class TestHoras:
    def test_hora_separa_colon(self) -> None:
        out = normalizar_para_tts("son las 20:30")
        assert ":" not in out
        assert "veinte" in out and "treinta" in out


class TestRobustez:
    def test_texto_vacio(self) -> None:
        assert normalizar_para_tts("") == ""

    def test_texto_normal_sin_cambios(self) -> None:
        out = normalizar_para_tts("Hola, todo está listo.")
        assert out == "Hola, todo está listo."

    def test_conserva_puntuacion(self) -> None:
        out = normalizar_para_tts("¿Qué película viste? ¡Genial!")
        assert "¿" in out and "?" in out and "¡" in out and "!" in out

    def test_colapsa_espacios(self) -> None:
        out = normalizar_para_tts("hola    mundo")
        assert "  " not in out
