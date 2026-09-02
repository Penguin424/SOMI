"""Cliente HTTP para LM Studio remoto (API compatible con OpenAI).

Sustituye al cliente Ollama local: chat con tool calling y embeddings, ambos
contra el mismo servidor (`somi.underpenguin.com`) autenticado con un token
Bearer leído de un archivo fuera del repo.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

_KEY_CACHE: dict[str, str] = {}


class LLMError(Exception):
    """Error de alto nivel, pensado para mostrarse directo en una notificación."""


def expand(p: str) -> str:
    return os.path.expanduser(str(p))


def cargar_api_key(seccion: dict) -> str:
    """Lee el token Bearer desde `seccion['api_key_file']`, con cache en memoria."""
    path = expand(seccion["api_key_file"])
    if path in _KEY_CACHE:
        return _KEY_CACHE[path]
    try:
        with open(path, encoding="utf-8") as f:
            token = f.read().strip()
    except FileNotFoundError:
        raise LLMError(f"No encuentro el token en {path}") from None
    except OSError as e:
        raise LLMError(f"No pude leer el token en {path}: {e}") from e
    if not token:
        raise LLMError(f"El archivo de token {path} está vacío")
    _KEY_CACHE[path] = token
    return token


def _post(url: str, body: dict, token: str, timeout: int) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_txt = ""
        try:
            body_txt = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        if e.code == 401:
            raise LLMError("token inválido o ausente para el servidor LM Studio") from e
        if e.code == 404:
            raise LLMError("modelo no encontrado en el servidor LM Studio") from e
        if e.code in (502, 503, 504):
            # El proxy contesta pero el backend no: el cuerpo es la página HTML
            # de error del proxy, inútil dentro de una notificación.
            raise LLMError(
                f"el servidor LM Studio no está arrancado (el proxy devolvió {e.code}); "
                "enciéndelo y reintenta"
            ) from e
        raise LLMError(f"servidor LM Studio respondió {e.code}: {body_txt}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"no se pudo contactar con el servidor LM Studio: {e.reason}") from e
    except TimeoutError as e:
        raise LLMError("el servidor LM Studio no respondió a tiempo") from e


def chat(messages: list[dict], cfg: dict, log=None, tools: list[dict] | None = None) -> dict:
    """Llama a `{endpoint}/chat/completions` y devuelve el `message` del primer choice."""
    llm_cfg = cfg["llm"]
    token = cargar_api_key(llm_cfg)
    payload: dict = {
        "model": llm_cfg["model"],
        "messages": messages,
        "stream": False,
        # Evita el modo "thinking" de Qwen3: sin esto, el modelo puede gastar
        # miles de tokens de razonamiento por turno, matando la latencia de
        # un asistente de voz.
        "reasoning_effort": "none",
    }
    if tools:
        payload["tools"] = tools

    timeout = llm_cfg.get("timeout", 120)
    url = llm_cfg["endpoint"].rstrip("/") + "/chat/completions"
    if log:
        log(f"LLM POST {url} msgs={len(messages)} tools={bool(tools)}")
    resp = _post(url, payload, token, timeout)
    try:
        return resp["choices"][0]["message"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"respuesta del servidor LM Studio sin choices/message: {e}") from e


def embed(textos: list[str], cfg: dict, log=None) -> list[list[float]]:
    """Llama a `{endpoint}/embeddings` y devuelve los vectores en el orden de `textos`."""
    emb_cfg = cfg["embeddings"]
    token = cargar_api_key(emb_cfg)
    payload = {"model": emb_cfg["model"], "input": textos}
    timeout = emb_cfg.get("timeout", 60)
    url = emb_cfg["endpoint"].rstrip("/") + "/embeddings"
    if log:
        log(f"EMBED POST {url} n={len(textos)}")
    resp = _post(url, payload, token, timeout)
    try:
        datos = sorted(resp["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in datos]
    except (KeyError, TypeError) as e:
        raise LLMError(f"respuesta del servidor de embeddings mal formada: {e}") from e
