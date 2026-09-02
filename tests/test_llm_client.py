"""Tests del cliente LM Studio remoto (chat + embeddings), sin red real."""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import llm_client
from llm_client import LLMError, cargar_api_key, chat, embed


def _cfg(tmp_path: Path) -> dict:
    token_file = tmp_path / "lm-token"
    token_file.write_text("sk-test-123\n", encoding="utf-8")
    return {
        "llm": {
            "endpoint": "https://somi.underpenguin.com/v1",
            "api_key_file": str(token_file),
            "model": "qwen/qwen3.5-9b",
            "timeout": 30,
        },
        "embeddings": {
            "endpoint": "https://somi.underpenguin.com/v1",
            "api_key_file": str(token_file),
            "model": "text-embedding-nomic-embed-text-v1.5",
            "timeout": 30,
        },
    }


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _clear_key_cache():
    llm_client._KEY_CACHE.clear()
    yield
    llm_client._KEY_CACHE.clear()


class TestCargarApiKey:
    def test_lee_y_limpia_token(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        assert cargar_api_key(cfg["llm"]) == "sk-test-123"

    def test_archivo_ausente(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        cfg["llm"]["api_key_file"] = str(tmp_path / "no-existe")
        with pytest.raises(LLMError):
            cargar_api_key(cfg["llm"])

    def test_archivo_vacio(self, tmp_path: Path) -> None:
        vacio = tmp_path / "vacio"
        vacio.write_text("   \n", encoding="utf-8")
        with pytest.raises(LLMError):
            cargar_api_key({"api_key_file": str(vacio)})


class TestChat:
    def test_manda_bearer_y_url_correcta(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            captured["body"] = json.loads(req.data)
            return _FakeResponse({
                "choices": [{"message": {"role": "assistant", "content": "hola", "tool_calls": []}}]
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg = chat([{"role": "user", "content": "hola"}], cfg)

        assert captured["url"] == "https://somi.underpenguin.com/v1/chat/completions"
        assert captured["auth"] == "Bearer sk-test-123"
        assert captured["body"]["model"] == "qwen/qwen3.5-9b"
        assert captured["body"]["reasoning_effort"] == "none"
        assert msg["content"] == "hola"

    def test_incluye_tools_si_se_pasan(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        captured: dict = {}
        tool_schema = [{"type": "function", "function": {"name": "agregar_pendiente"}}]

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeResponse({
                "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": []}}]
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            chat([{"role": "user", "content": "recuérdame algo"}], cfg, tools=tool_schema)

        assert captured["body"]["tools"] == tool_schema

    def test_sin_tools_no_manda_el_campo(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeResponse({
                "choices": [{"message": {"role": "assistant", "content": "hola", "tool_calls": []}}]
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            chat([{"role": "user", "content": "hola"}], cfg)

        assert "tools" not in captured["body"]

    def test_respuesta_con_tool_calls_conserva_id_y_arguments_string(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        tool_calls = [{
            "type": "function",
            "id": "call_abc123",
            "function": {"name": "agregar_pendiente", "arguments": '{"tarea":"comprar café"}'},
        }]

        def fake_urlopen(req, timeout=None):
            return _FakeResponse({
                "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": tool_calls}}]
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            msg = chat([{"role": "user", "content": "recuérdame comprar café"}], cfg)

        assert msg["tool_calls"][0]["id"] == "call_abc123"
        assert isinstance(msg["tool_calls"][0]["function"]["arguments"], str)

    def test_401_da_llmerror_de_token(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":"invalid_api_key"}')
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="token"):
                chat([{"role": "user", "content": "hola"}], cfg)

    def test_404_da_llmerror_de_modelo(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="modelo"):
                chat([{"role": "user", "content": "hola"}], cfg)

    def test_sin_red_da_llmerror_de_conexion(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="contactar"):
                chat([{"role": "user", "content": "hola"}], cfg)

    def test_502_dice_que_el_backend_no_esta_arrancado_sin_volcar_html(
        self, tmp_path: Path
    ) -> None:
        """El 502 lo genera el proxy, no LM Studio: su cuerpo es una página HTML
        que no cabe ni tiene sentido en una notificación."""
        cfg = _cfg(tmp_path)
        html = b"<html>\n<head><title>502 Bad Gateway</title></head>\n<body></body>\n</html>"

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(html))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError) as exc:
                chat([{"role": "user", "content": "hola"}], cfg)

        assert "arrancado" in str(exc.value)
        assert "502" in str(exc.value)
        assert "<html" not in str(exc.value)

    def test_500_de_la_app_conserva_el_cuerpo_util(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        body = b'{"error":"model failed to load"}'

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, io.BytesIO(body))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(LLMError, match="model failed to load"):
                chat([{"role": "user", "content": "hola"}], cfg)


class TestEmbed:
    def test_devuelve_vectores_en_orden_de_index(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)

        def fake_urlopen(req, timeout=None):
            return _FakeResponse({
                "data": [
                    {"index": 1, "embedding": [0.2, 0.2]},
                    {"index": 0, "embedding": [0.1, 0.1]},
                ]
            })

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            vecs = embed(["primero", "segundo"], cfg)

        assert vecs == [[0.1, 0.1], [0.2, 0.2]]

    def test_usa_modelo_y_endpoint_de_embeddings(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            return _FakeResponse({"data": [{"index": 0, "embedding": [0.1]}]})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            embed(["hola"], cfg)

        assert captured["url"] == "https://somi.underpenguin.com/v1/embeddings"
        assert captured["body"]["model"] == "text-embedding-nomic-embed-text-v1.5"
