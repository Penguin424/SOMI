"""Tests de compatibilidad de load_history tras migrar de Ollama a LM Studio."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from pipeline import load_history


def _cfg(tmp_path: Path) -> dict:
    return {
        "history": {
            "file": str(tmp_path / "conversation.json"),
            "rotated_dir": str(tmp_path / "history"),
            "expire_minutes": 60,
        }
    }


def _logs() -> list[str]:
    lines: list[str] = []
    return lines


def _log_capturado(lines: list[str]):
    def log(msg: str) -> None:
        lines.append(msg)
    return log


class TestFormatoOllamaViejo:
    def test_tool_calls_sin_id_se_rota(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        hist_file = Path(cfg["history"]["file"])
        hist_file.write_text(json.dumps([
            {"role": "user", "content": "recuérdame algo"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "agregar_pendiente", "arguments": "{}"}}],
            },
            {"role": "tool", "content": "{}"},
        ]), encoding="utf-8")

        lines: list[str] = []
        result = load_history(cfg, _log_capturado(lines))

        assert result == []
        assert not hist_file.exists()
        rotados = list((tmp_path / "history").glob("conversation-*.json"))
        assert len(rotados) == 1

    def test_formato_openai_nuevo_no_se_rota(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        hist_file = Path(cfg["history"]["file"])
        historial = [
            {"role": "user", "content": "recuérdame algo"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {"name": "agregar_pendiente", "arguments": "{}"},
                }],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "agregar_pendiente", "content": "{}"},
        ]
        hist_file.write_text(json.dumps(historial), encoding="utf-8")

        result = load_history(cfg, _log_capturado([]))

        assert result == historial
        assert hist_file.exists()

    def test_historial_sin_tools_no_se_rota(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        hist_file = Path(cfg["history"]["file"])
        historial = [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "hola, ¿en qué te ayudo?"},
        ]
        hist_file.write_text(json.dumps(historial), encoding="utf-8")

        result = load_history(cfg, _log_capturado([]))

        assert result == historial
