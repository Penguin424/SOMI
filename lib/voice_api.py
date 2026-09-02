"""Cliente HTTP para el servidor de voz remoto (STT + TTS, API compatible OpenAI).

Mismo estilo que `llm_client.py`: solo stdlib `urllib`, síncrono, errores
traducidos a mensajes que caben en una notificación. Reutiliza
`llm_client.cargar_api_key()` para no duplicar el cache de tokens.
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from pathlib import Path

import llm_client

CHUNK_SIZE = 8192


class VoiceAPIError(Exception):
    """Error de alto nivel, pensado para mostrarse directo en una notificación."""


def expand(p: str) -> str:
    return os.path.expanduser(str(p))


def _multipart_body(campos: dict[str, str], archivo: tuple[str, str, bytes]) -> tuple[bytes, str]:
    """Codifica un cuerpo multipart/form-data a mano (sin requests/httpx).

    `archivo` es (nombre_campo, nombre_fichero, contenido)."""
    boundary = uuid.uuid4().hex
    partes: list[bytes] = []

    for nombre, valor in campos.items():
        partes.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{nombre}"\r\n\r\n{valor}\r\n'.encode(
                "utf-8"
            )
        )

    campo_archivo, nombre_archivo, contenido = archivo
    ctype = mimetypes.guess_type(nombre_archivo)[0] or "audio/wav"
    partes.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{campo_archivo}"; '
            f'filename="{nombre_archivo}"\r\nContent-Type: {ctype}\r\n\r\n'
        ).encode("utf-8")
    )
    partes.append(contenido)
    partes.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    return b"".join(partes), boundary


def _abrir(req: urllib.request.Request, timeout: int, contexto: str):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body_txt = ""
        try:
            body_txt = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        if e.code == 401:
            raise VoiceAPIError("token inválido para el servidor de voz") from e
        if e.code == 404:
            raise VoiceAPIError("voz o endpoint no encontrado en el servidor de voz") from e
        if e.code in (502, 503, 504):
            # El proxy contesta pero el backend no: el cuerpo es la página HTML
            # de error del proxy, inútil dentro de una notificación.
            raise VoiceAPIError(
                f"el servidor de voz no está arrancado (el proxy devolvió {e.code}); "
                "enciéndelo y reintenta"
            ) from e
        raise VoiceAPIError(f"servidor de voz ({contexto}) respondió {e.code}: {body_txt}") from e
    except urllib.error.URLError as e:
        raise VoiceAPIError(f"no se pudo contactar con el servidor de voz: {e.reason}") from e
    except TimeoutError as e:
        raise VoiceAPIError("el servidor de voz no respondió a tiempo") from e


def transcribir(wav: Path, cfg: dict, log=None) -> str:
    """POST {stt.endpoint}/audio/transcriptions (multipart: file + language) -> texto."""
    stt_cfg = cfg["stt"]
    token = llm_client.cargar_api_key(stt_cfg)
    url = stt_cfg["endpoint"].rstrip("/") + "/audio/transcriptions"
    timeout = stt_cfg.get("timeout", 120)

    contenido = wav.read_bytes()
    body, boundary = _multipart_body(
        {"language": stt_cfg.get("language", "es")},
        ("file", wav.name, contenido),
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
    )
    if log:
        log(f"STT POST {url} file={wav.name} ({len(contenido)} bytes)")
    with _abrir(req, timeout, "transcripción") as r:
        resp = json.loads(r.read())
    try:
        return resp["text"]
    except (KeyError, TypeError) as e:
        raise VoiceAPIError(f"respuesta del servidor de voz sin 'text': {e}") from e


def _payload_tts(texto: str, cfg: dict, stream: bool) -> dict:
    tts_cfg = cfg["tts"]
    return {
        "input": texto,
        "voice": tts_cfg.get("voice", "somi"),
        "response_format": "wav",
        "stream": stream,
    }


def _leer_wav_header(primer_chunk: bytes, sock) -> tuple[dict, bytes]:
    """Recorre los chunks RIFF de `primer_chunk` (+lecturas extra si hace falta)
    hasta encontrar 'fmt ' y 'data'. Devuelve (formato, resto_de_audio_ya_leido)."""
    buf = bytearray(primer_chunk)

    def _asegurar(n: int) -> None:
        while len(buf) < n:
            extra = sock.read(CHUNK_SIZE)
            if not extra:
                raise VoiceAPIError("el servidor de voz cortó el audio antes de la cabecera WAV")
            buf.extend(extra)

    _asegurar(12)
    if buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise VoiceAPIError("el servidor de voz no devolvió un WAV válido")

    pos = 12
    fmt: dict | None = None
    while True:
        _asegurar(pos + 8)
        chunk_id = bytes(buf[pos : pos + 4])
        chunk_size = int.from_bytes(buf[pos + 4 : pos + 8], "little")
        data_start = pos + 8

        if chunk_id == b"fmt ":
            _asegurar(data_start + chunk_size)
            fmt_chunk = bytes(buf[data_start : data_start + chunk_size])
            channels = int.from_bytes(fmt_chunk[2:4], "little")
            rate = int.from_bytes(fmt_chunk[4:8], "little")
            bits = int.from_bytes(fmt_chunk[14:16], "little")
            fmt = {"rate": rate, "channels": channels, "sample_width": bits // 8}
            pos = data_start + chunk_size + (chunk_size % 2)
            continue

        if chunk_id == b"data":
            if fmt is None:
                raise VoiceAPIError("el servidor de voz mandó 'data' antes que 'fmt ' en el WAV")
            # El tamaño de 'data' en streaming suele ser un placeholder (0 o
            # gigante, Content-Length indeterminado): lo que importa es que
            # todo lo que venga después de este punto es PCM crudo.
            return fmt, bytes(buf[data_start:])

        # chunk desconocido: saltarlo
        pos = data_start + chunk_size + (chunk_size % 2)


def abrir_stream(texto: str, cfg: dict, log=None) -> tuple[dict, Iterator[bytes]]:
    """POST {tts.endpoint}/audio/speech con stream:true.

    Devuelve (formato_pcm, iterador de trozos de audio PCM crudo)."""
    tts_cfg = cfg["tts"]
    token = llm_client.cargar_api_key(tts_cfg)
    url = tts_cfg["endpoint"].rstrip("/") + "/audio/speech"
    timeout = tts_cfg.get("timeout", 300)

    payload = json.dumps(_payload_tts(texto, cfg, stream=True)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    if log:
        log(f"TTS (stream) POST {url} gen='{texto[:80]}'")

    resp = _abrir(req, timeout, "síntesis")
    primer_chunk = resp.read(CHUNK_SIZE)
    if not primer_chunk:
        resp.close()
        raise VoiceAPIError("el servidor de voz devolvió una respuesta vacía")
    fmt, resto = _leer_wav_header(primer_chunk, resp)

    def _trozos() -> Iterator[bytes]:
        emitido_audio = bool(resto)
        try:
            if resto:
                yield resto
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                emitido_audio = True
                yield chunk
        finally:
            resp.close()
        if not emitido_audio:
            raise VoiceAPIError("el servidor de voz no mandó bytes de audio")

    return fmt, _trozos()


def descargar_wav(texto: str, cfg: dict, log, out: Path) -> Path:
    """POST {tts.endpoint}/audio/speech con stream:false; escribe el WAV completo en `out`."""
    tts_cfg = cfg["tts"]
    token = llm_client.cargar_api_key(tts_cfg)
    url = tts_cfg["endpoint"].rstrip("/") + "/audio/speech"
    timeout = tts_cfg.get("timeout", 300)

    payload = json.dumps(_payload_tts(texto, cfg, stream=False)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    if log:
        log(f"TTS POST {url} gen='{texto[:80]}'")

    with _abrir(req, timeout, "síntesis") as resp:
        contenido = resp.read()
    if not contenido:
        raise VoiceAPIError("el servidor de voz devolvió un audio vacío")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(contenido)
    return out
