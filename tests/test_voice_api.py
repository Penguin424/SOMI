"""Tests del cliente del servidor de voz remoto (STT + TTS), sin red real."""
from __future__ import annotations

import io
import json
import struct
import sys
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

import llm_client
import voice_api
from voice_api import VoiceAPIError, abrir_stream, descargar_wav, transcribir


def _cfg(tmp_path: Path) -> dict:
    token_file = tmp_path / "voice-api-token"
    token_file.write_text("Ac03901582.\n", encoding="utf-8")
    return {
        "stt": {
            "endpoint": "https://chat-somi.underpenguin.com/v1",
            "api_key_file": str(token_file),
            "language": "es",
            "timeout": 30,
        },
        "tts": {
            "endpoint": "https://chat-somi.underpenguin.com/v1",
            "api_key_file": str(token_file),
            "voice": "somi",
            "stream": True,
            "timeout": 30,
        },
    }


def _build_wav(
    pcm: bytes,
    rate: int = 24000,
    channels: int = 1,
    bits: int = 16,
    extra_chunk: bytes | None = None,
) -> bytes:
    """Arma un WAV mínimo a mano, opcionalmente con un chunk desconocido
    (p.ej. 'LIST') entre 'fmt ' y 'data', para probar que el parser no asume
    los 44 bytes de cabecera fijos habituales."""
    fmt_data = struct.pack(
        "<HHIIHH", 1, channels, rate, rate * channels * bits // 8, channels * bits // 8, bits
    )
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt_data)) + fmt_data
    if extra_chunk is not None:
        body += b"LIST" + struct.pack("<I", len(extra_chunk)) + extra_chunk
        if len(extra_chunk) % 2:
            body += b"\x00"
    body += b"data" + struct.pack("<I", len(pcm)) + pcm
    return b"RIFF" + struct.pack("<I", len(body)) + body


class _FakeJSONResponse:
    """Respuesta no-streaming (JSON): mismo shape que en test_llm_client.py."""

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self, n: int = -1) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeStreamResponse:
    """Respuesta binaria (audio) que entrega los bytes en trozos pequeños,
    para forzar al parser de la cabecera WAV a leer más de una vez."""

    def __init__(self, data: bytes, chunk_cap: int = 8192):
        self._data = data
        self._pos = 0
        self._chunk_cap = chunk_cap
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        remaining = len(self._data) - self._pos
        if n is None or n < 0:
            n = remaining
        n = min(n, self._chunk_cap, remaining)
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


@pytest.fixture(autouse=True)
def _clear_key_cache():
    llm_client._KEY_CACHE.clear()
    yield
    llm_client._KEY_CACHE.clear()


class TestTranscribir:
    def test_multipart_incluye_file_y_language(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        wav = tmp_path / "pregunta.wav"
        wav.write_bytes(b"RIFF....WAVEfmt ")
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            captured["content_type"] = req.get_header("Content-type")
            captured["body"] = req.data
            return _FakeJSONResponse({"text": "hola somi"})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            text = transcribir(wav, cfg)

        assert captured["url"] == "https://chat-somi.underpenguin.com/v1/audio/transcriptions"
        assert captured["auth"] == "Bearer Ac03901582."
        assert "multipart/form-data; boundary=" in captured["content_type"]
        body = captured["body"]
        assert b'name="language"' in body
        assert b"es" in body
        assert b'name="file"; filename="pregunta.wav"' in body
        assert b"RIFF....WAVEfmt " in body
        assert text == "hola somi"

    def test_401_da_voiceapierror_de_token(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        wav = tmp_path / "pregunta.wav"
        wav.write_bytes(b"data")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(VoiceAPIError, match="token"):
                transcribir(wav, cfg)

    def test_sin_red_da_voiceapierror_de_conexion(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        wav = tmp_path / "pregunta.wav"
        wav.write_bytes(b"data")

        def fake_urlopen(req, timeout=None):
            raise urllib.error.URLError("connection refused")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(VoiceAPIError, match="contactar"):
                transcribir(wav, cfg)

    def test_502_dice_que_el_backend_no_esta_arrancado_sin_volcar_html(
        self, tmp_path: Path
    ) -> None:
        """El 502 lo genera el proxy (openresty), no la app: su cuerpo es una
        página HTML que no cabe ni tiene sentido en una notificación."""
        cfg = _cfg(tmp_path)
        wav = tmp_path / "pregunta.wav"
        wav.write_bytes(b"data")
        html = b"<html>\n<head><title>502 Bad Gateway</title></head>\n<body></body>\n</html>"

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 502, "Bad Gateway", {}, io.BytesIO(html))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(VoiceAPIError) as exc:
                transcribir(wav, cfg)

        assert "arrancado" in str(exc.value)
        assert "502" in str(exc.value)
        assert "<html" not in str(exc.value)

    def test_500_de_la_app_conserva_el_cuerpo_util(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        wav = tmp_path / "pregunta.wav"
        wav.write_bytes(b"data")
        body = b'{"error":"CUDA error: unknown error"}'

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, io.BytesIO(body))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(VoiceAPIError, match="CUDA error"):
                transcribir(wav, cfg)


class TestAbrirStream:
    def test_parsea_formato_y_no_emite_bytes_de_cabecera(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        pcm = bytes(range(20)) * 6  # 120 bytes de "audio", nada especial
        wav = _build_wav(pcm, rate=24000, channels=1, bits=16)
        fake = _FakeStreamResponse(wav, chunk_cap=5)

        with patch("urllib.request.urlopen", return_value=fake):
            fmt, trozos = abrir_stream("hola somi", cfg)
            recibido = b"".join(trozos)

        assert fmt == {"rate": 24000, "channels": 1, "sample_width": 2}
        assert recibido == pcm
        assert fake.closed

    def test_chunk_desconocido_antes_de_data_no_rompe_el_parseo(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        pcm = bytes(range(30)) * 4
        wav = _build_wav(pcm, rate=22050, channels=2, bits=16, extra_chunk=b"\x01\x02\x03")
        fake = _FakeStreamResponse(wav, chunk_cap=7)

        with patch("urllib.request.urlopen", return_value=fake):
            fmt, trozos = abrir_stream("hola somi", cfg)
            recibido = b"".join(trozos)

        assert fmt == {"rate": 22050, "channels": 2, "sample_width": 2}
        assert recibido == pcm

    def test_stream_sin_audio_levanta_voiceapierror(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        wav = _build_wav(b"", rate=24000, channels=1, bits=16)
        fake = _FakeStreamResponse(wav, chunk_cap=5)

        with patch("urllib.request.urlopen", return_value=fake):
            _fmt, trozos = abrir_stream("hola somi", cfg)
            with pytest.raises(VoiceAPIError, match="audio"):
                list(trozos)

    def test_401_da_voiceapierror_de_token(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with pytest.raises(VoiceAPIError, match="token"):
                abrir_stream("hola somi", cfg)


class TestDescargarWav:
    def test_escribe_el_wav_completo(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        pcm = bytes(range(50))
        wav = _build_wav(pcm, rate=24000, channels=1, bits=16)
        fake = _FakeStreamResponse(wav)
        out = tmp_path / "respuesta.wav"

        with patch("urllib.request.urlopen", return_value=fake):
            resultado = descargar_wav("hola somi", cfg, log=None, out=out)

        assert resultado == out
        assert out.read_bytes() == wav

    def test_manda_stream_false(self, tmp_path: Path) -> None:
        cfg = _cfg(tmp_path)
        pcm = b"\x00\x01" * 10
        wav = _build_wav(pcm)
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return _FakeStreamResponse(wav)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            descargar_wav("hola somi", cfg, log=None, out=tmp_path / "r.wav")

        assert captured["body"]["stream"] is False
        assert captured["body"]["voice"] == "somi"
