"""Tests de la Fase 3: log_entrenamiento."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime

from tools.log_entrenamiento import ejecutar as log_entrenamiento


def noop_log(msg: str) -> None:
    pass


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# Formato compacto: series como entero, no array de objetos
PRESS_BANCA_4X8 = {"nombre": "press banca", "series": 4, "reps": 8, "peso": 80, "unidad": "kg"}
SENTADILLA_3X10 = {"nombre": "sentadilla", "series": 3, "reps": 10, "peso": 100, "unidad": "kg"}
DOMINADAS_FALLO = {"nombre": "dominadas", "series": 3, "reps": "fallo"}


class TestLogEntrenamiento:
    def test_crea_archivo_en_ruta_correcta(self, vault: Path) -> None:
        resultado = log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        fecha = datetime.now().strftime("%Y-%m-%d")
        assert (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").exists()

    def test_frontmatter_tiene_tipo_entrenamiento(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "tipo: entrenamiento" in texto

    def test_frontmatter_descripcion_ejercicio_para_dataview(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        # Debe aparecer en formato "press banca (4x8 @ 80 kg)"
        assert "press banca" in texto
        assert "4x8" in texto
        assert "80 kg" in texto

    def test_frontmatter_incluye_duracion_si_se_pasa(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], duracion_min=60, vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "duracion_min: 60" in texto

    def test_cuerpo_tiene_h2_por_ejercicio(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8, SENTADILLA_3X10], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "## Press Banca" in texto
        assert "## Sentadilla" in texto

    def test_tabla_expande_todas_las_series(self, vault: Path) -> None:
        """4 series → 4 filas en la tabla, no solo 1."""
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "| 1 | 80 kg | 8 |" in texto
        assert "| 2 | 80 kg | 8 |" in texto
        assert "| 3 | 80 kg | 8 |" in texto
        assert "| 4 | 80 kg | 8 |" in texto

    def test_tabla_con_peso_incluye_columna_peso(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "| Set | Peso | Reps |" in texto

    def test_tabla_sin_peso_para_peso_corporal(self, vault: Path) -> None:
        log_entrenamiento([DOMINADAS_FALLO], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "| Set | Reps |" in texto
        assert "| Set | Peso | Reps |" not in texto

    def test_tres_series_al_fallo_generan_tres_filas(self, vault: Path) -> None:
        log_entrenamiento([DOMINADAS_FALLO], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "| 1 | fallo |" in texto
        assert "| 2 | fallo |" in texto
        assert "| 3 | fallo |" in texto

    def test_sesion_con_mezcla_de_ejercicios(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8, SENTADILLA_3X10, DOMINADAS_FALLO], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "## Press Banca" in texto
        assert "## Sentadilla" in texto
        assert "## Dominadas" in texto
        assert "80 kg" in texto
        assert "fallo" in texto

    def test_notas_aparecen_al_final(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], notas="Buen día, subí el peso", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "Notas: Buen día" in texto

    def test_segunda_sesion_mismo_dia_se_anexa_con_separador(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        log_entrenamiento([DOMINADAS_FALLO], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert "Press Banca" in texto
        assert "Dominadas" in texto
        assert "---" in texto

    def test_segunda_sesion_no_duplica_frontmatter(self, vault: Path) -> None:
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        log_entrenamiento([DOMINADAS_FALLO], vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Fitness" / "Entrenamientos" / f"{fecha}.md").read_text()
        assert texto.count("tipo: entrenamiento") == 1

    def test_ejercicios_vacios_devuelve_error(self, vault: Path) -> None:
        resultado = log_entrenamiento([], vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_resultado_contiene_ruta(self, vault: Path) -> None:
        resultado = log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=noop_log)
        assert "path" in resultado
        assert resultado["path"].endswith(".md")

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        log_entrenamiento([PRESS_BANCA_4X8], vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("log_entrenamiento" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)


class TestDeserializacionRegistry:
    """Llama 3.1 8B devuelve arrays como strings JSON y los trunca — el registry debe normalizarlos."""

    def test_ejercicios_como_string_json_se_deserializa(self) -> None:
        from tools.registry import _deserializar_arg
        ejercicios_str = '[{"nombre": "press banca", "series": 4, "reps": 8, "peso": 80}]'
        resultado = _deserializar_arg(ejercicios_str)
        assert isinstance(resultado, list)
        assert resultado[0]["nombre"] == "press banca"

    def test_string_no_json_no_se_toca(self) -> None:
        from tools.registry import _deserializar_arg
        assert _deserializar_arg("texto normal") == "texto normal"

    def test_lista_real_no_se_toca(self) -> None:
        from tools.registry import _deserializar_arg
        lista = [{"nombre": "sentadilla"}]
        assert _deserializar_arg(lista) is lista

    def test_json_truncado_sin_bracket_final(self) -> None:
        """Reproduce el bug real: array que termina sin ] de cierre."""
        from tools.registry import _deserializar_arg
        truncado = '[{"nombre": "press banca", "series": 4, "reps": 8, "peso": 80}'  # sin ]
        resultado = _deserializar_arg(truncado)
        assert isinstance(resultado, list)
        assert resultado[0]["series"] == 4

    def test_json_truncado_multiples_ejercicios(self) -> None:
        from tools.registry import _deserializar_arg
        truncado = (
            '[{"nombre": "press banca", "series": 4, "reps": 8, "peso": 80},'
            '{"nombre": "sentadilla", "series": 3, "reps": 10, "peso": 100},'
            '{"nombre": "dominadas", "series": 3, "reps": "fallo"}'  # sin ]
        )
        resultado = _deserializar_arg(truncado)
        assert isinstance(resultado, list)
        assert len(resultado) == 3

    def test_ejecutar_tool_con_json_truncado(self, tmp_path: Path) -> None:
        from tools.registry import ejecutar_tool
        vault = tmp_path / "vault"
        vault.mkdir()
        truncado = '[{"nombre": "press banca", "series": 4, "reps": 8, "peso": 80}'  # sin ]
        cfg = {"vault": {"path": str(vault)}, "tools": {"log_file": "/tmp/test_tools.log"}}
        resultado = ejecutar_tool("log_entrenamiento", {"ejercicios": truncado}, cfg)
        assert resultado["status"] == "ok"
        fecha = datetime.now().strftime("%Y-%m-%d")
        ruta = vault / "Fitness" / "Entrenamientos" / f"{fecha}.md"
        assert ruta.exists()
        # 4 series deben expandirse en 4 filas
        texto = ruta.read_text()
        assert "| 4 |" in texto
