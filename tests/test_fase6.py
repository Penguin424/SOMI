"""Tests de la Fase 6: consultar_experto."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tools.consultar_experto import ejecutar as consultar_experto


def noop_log(msg: str) -> None:
    pass


def _mock_run_ok(stdout: str = "Respuesta del experto"):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = stdout
    mock.stderr = ""
    return mock


def _mock_run_error(returncode: int = 1, stderr: str = "auth error"):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = ""
    mock.stderr = stderr
    return mock


class TestConsultarExperto:
    def test_claude_ok(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("4")) as mock_run:
            resultado = consultar_experto("¿Cuánto es 2+2?", experto="claude", log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert resultado["respuesta"] == "4"
        assert resultado["experto"] == "claude"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "¿Cuánto es 2+2?" in cmd

    def test_gemini_ok(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("Hola desde Gemini")):
            resultado = consultar_experto("Hola", experto="gemini", log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert resultado["experto"] == "gemini"

    def test_experto_por_defecto_es_claude(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("ok")) as mock_run:
            consultar_experto("test", log_fn=noop_log)
        assert mock_run.call_args[0][0][0] == "claude"

    def test_experto_invalido_cae_a_claude(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("ok")) as mock_run:
            resultado = consultar_experto("test", experto="chatgpt", log_fn=noop_log)
        assert mock_run.call_args[0][0][0] == "claude"
        assert resultado["status"] == "ok"

    def test_pregunta_vacia_devuelve_error(self) -> None:
        resultado = consultar_experto("", log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_pregunta_solo_espacios_devuelve_error(self) -> None:
        resultado = consultar_experto("   ", log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_cli_no_instalado_devuelve_error(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            resultado = consultar_experto("test", experto="claude", log_fn=noop_log)
        assert resultado["status"] == "error"
        assert "instalado" in resultado["message"]

    def test_timeout_devuelve_error(self) -> None:
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)):
            resultado = consultar_experto("test", experto="claude", log_fn=noop_log)
        assert resultado["status"] == "error"
        assert "respondió" in resultado["message"]

    def test_returncode_no_cero_devuelve_error(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_error(1, "auth required")):
            resultado = consultar_experto("test", experto="gemini", log_fn=noop_log)
        assert resultado["status"] == "error"
        assert "auth required" in resultado["message"]

    def test_respuesta_vacia_devuelve_error(self) -> None:
        mock = _mock_run_ok("")
        with patch("subprocess.run", return_value=mock):
            resultado = consultar_experto("test", experto="claude", log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_respuesta_larga_se_trunca(self) -> None:
        respuesta_larga = "x" * 3000
        with patch("subprocess.run", return_value=_mock_run_ok(respuesta_larga)):
            resultado = consultar_experto("test", experto="claude", log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert len(resultado["respuesta"]) <= 2003  # 2000 + "..."

    def test_ambos_llama_a_claude_y_gemini(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("ok")) as mock_run:
            resultado = consultar_experto("test", experto="ambos", log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert resultado["experto"] == "ambos"
        assert len(resultado["resultados"]) == 2
        clientes = {call[0][0][0] for call in mock_run.call_args_list}
        assert "claude" in clientes
        assert "gemini" in clientes

    def test_ambos_devuelve_resultados_individuales(self) -> None:
        def mock_run(cmd, **kwargs):
            if "claude" in cmd[0]:
                return _mock_run_ok("respuesta claude")
            return _mock_run_ok("respuesta gemini")

        with patch("subprocess.run", side_effect=mock_run):
            resultado = consultar_experto("test", experto="ambos", log_fn=noop_log)

        resultados = {r["experto"]: r for r in resultado["resultados"]}
        assert resultados["claude"]["respuesta"] == "respuesta claude"
        assert resultados["gemini"]["respuesta"] == "respuesta gemini"

    def test_ambos_con_un_error_sigue_ok(self) -> None:
        def mock_run(cmd, **kwargs):
            if "claude" in cmd[0]:
                return _mock_run_ok("respuesta")
            return _mock_run_error(1, "auth error")

        with patch("subprocess.run", side_effect=mock_run):
            resultado = consultar_experto("test", experto="ambos", log_fn=noop_log)

        assert resultado["status"] == "ok"
        assert any(r["status"] == "ok" for r in resultado["resultados"])
        assert any(r["status"] == "error" for r in resultado["resultados"])

    def test_loguea_la_llamada(self) -> None:
        mensajes: list[str] = []
        with patch("subprocess.run", return_value=_mock_run_ok("ok")):
            consultar_experto("test", experto="claude", log_fn=lambda m: mensajes.append(m))
        assert any("consultar_experto" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)

    def test_experto_case_insensitive(self) -> None:
        with patch("subprocess.run", return_value=_mock_run_ok("ok")) as mock_run:
            consultar_experto("test", experto="CLAUDE", log_fn=noop_log)
        assert mock_run.call_args[0][0][0] == "claude"
