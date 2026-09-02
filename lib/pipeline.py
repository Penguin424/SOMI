#!/usr/bin/env python3
"""SOMI pipeline: WAV -> STT (servidor de voz) -> LLM (LM Studio remoto) ->
TTS (servidor de voz) -> paplay.

Uso: pipeline.py <wav_file>
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

# Hace importable el directorio tools/ que está en la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

import llm_client
import voice_api

CONFIG_PATH = Path(__file__).parent.parent / "config.toml"

SILENCE_MARKERS = (
    "[BLANK_AUDIO]", "[blank_audio]",
    "[NO_SPEECH]", "[no_speech]",
    "(música)", "[Música]", "[música]",
    "(music)", "[Music]", "[music]",
    "(silence)", "[silence]",
    # Alucinaciones típicas de whisper-small sobre audio mudo/ruido — el
    # modelo `small` remoto las produce más que el `medium` local anterior.
    "Subtítulos realizados por la comunidad de Amara.org",
    "¡Gracias por ver el video!",
    "Gracias por ver el vídeo",
)


def expand(p: str) -> str:
    return os.path.expanduser(str(p))


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def notify(title: str, body: str = "", urgency: str = "normal") -> None:
    subprocess.run(
        [
            "notify-send", "-a", "SOMI",
            "-u", urgency,
            "-h", "string:x-canonical-private-synchronous:somi",
            title, body,
        ],
        check=False,
    )


def _log_writer(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a", encoding="utf-8")

    def write(msg: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{ts} {msg}\n"
        fh.write(line)
        fh.flush()
        print(line, end="", file=sys.stderr)

    return write


# --------- STT (servidor de voz remoto) ---------
def transcribe(wav: Path, cfg: dict, log) -> str | None:
    t0 = time.monotonic()
    try:
        text = voice_api.transcribir(wav, cfg, log)
    except voice_api.VoiceAPIError as e:
        log(f"STT error: {e}")
        raise
    log(f"STT elapsed={time.monotonic() - t0:.2f}s")
    text = (text or "").strip()
    if not text or len(text) < 3 or any(m in text for m in SILENCE_MARKERS):
        log(f"STT silence/no-voice: '{text}'")
        return None
    return text


# --------- Historia ---------
def load_history(cfg: dict, log) -> list[dict]:
    hist_file = Path(expand(cfg["history"]["file"]))
    if not hist_file.exists():
        return []
    age_min = (time.time() - hist_file.stat().st_mtime) / 60
    expire = cfg["history"]["expire_minutes"]
    if age_min > expire:
        rot_dir = Path(expand(cfg["history"]["rotated_dir"]))
        rot_dir.mkdir(parents=True, exist_ok=True)
        target = rot_dir / f"conversation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        shutil.move(str(hist_file), str(target))
        log(f"history: rotated ({age_min:.1f}min > {expire}min) -> {target.name}")
        return []
    try:
        with open(hist_file, encoding="utf-8") as f:
            data = json.load(f)
        if _es_formato_ollama_viejo(data):
            rot_dir = Path(expand(cfg["history"]["rotated_dir"]))
            rot_dir.mkdir(parents=True, exist_ok=True)
            target = rot_dir / f"conversation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            shutil.move(str(hist_file), str(target))
            log(f"history: formato Ollama antiguo detectado, rotado -> {target.name}")
            return []
        log(f"history: loaded {len(data)} messages (age {age_min:.1f}min)")
        return data
    except Exception as e:
        log(f"history: corrupt ({e}), starting fresh")
        return []


def _es_formato_ollama_viejo(data: list[dict]) -> bool:
    """Detecta historiales guardados antes de migrar a LM Studio: los mensajes
    de tool_calls/tool ahí no llevan "id"/"tool_call_id" (la API OpenAI sí los exige)."""
    for msg in data:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            if any("id" not in tc for tc in msg["tool_calls"]):
                return True
        if msg.get("role") == "tool" and "tool_call_id" not in msg:
            return True
    return False


def save_history(history: list[dict], cfg: dict) -> None:
    hist_file = Path(expand(cfg["history"]["file"]))
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    with open(hist_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _system_prompt_con_fecha(cfg: dict) -> str:
    """Inyecta la fecha/hora actual en el system prompt.

    Sin esto, tools como agregar_pendiente/calificar_media (que piden fechas
    en YYYY-MM-DD) no tienen forma de resolver expresiones relativas como
    "mañana": el modelo se queda deliberando cómo calcular la fecha y termina
    abandonando la llamada a la tool, devolviendo solo una confirmación
    verbal sin haber guardado nada."""
    ahora = datetime.now()
    dia_semana = _DIAS_ES[ahora.weekday()]
    mes = _MESES_ES[ahora.month - 1]
    fecha_legible = f"{dia_semana} {ahora.day} de {mes} de {ahora.year}"
    linea_fecha = (
        f"\n\nFecha y hora actual: {fecha_legible}, {ahora.strftime('%H:%M')} "
        f"(ISO: {ahora.strftime('%Y-%m-%d')}). Úsala para calcular fechas relativas "
        f'como "mañana", "el viernes" o "la próxima semana" en formato YYYY-MM-DD.'
    )
    return cfg["llm"]["system_prompt"] + linea_fecha


# --------- LLM (LM Studio remoto) ---------
def llm_chat(history: list[dict], user_text: str, cfg: dict, log) -> str:
    history.append({"role": "user", "content": user_text})
    system_prompt = _system_prompt_con_fecha(cfg)
    messages = [{"role": "system", "content": system_prompt}] + history

    tools_habilitado = cfg.get("tools", {}).get("habilitado", False)
    tool_schemas = None
    if tools_habilitado:
        from tools.registry import schemas_para_ollama, ejecutar_tool
        tool_schemas = schemas_para_ollama()

    log(f"LLM: msgs={len(messages)} user='{user_text[:80]}' tools={tools_habilitado}")
    t0 = time.monotonic()
    msg = llm_client.chat(messages, cfg, log, tools=tool_schemas)
    log(f"LLM elapsed={time.monotonic() - t0:.2f}s")

    tool_calls: list = msg.get("tool_calls") or []

    if tools_habilitado and tool_calls:
        # Guarda el turno del asistente con sus tool_calls en el historial
        # (formato OpenAI: cada llamada trae su propio "id")
        history.append({
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": tool_calls,
        })

        for llamada in tool_calls:
            nombre = llamada["function"]["name"]
            args = llamada["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
            log(f"TOOL: {nombre} args={args}")
            if nombre == "consultar_experto":
                experto = args.get("experto", "claude") if isinstance(args, dict) else "experto"
                notify(f"🤖 Consultando a {experto}...", "Puede tardar hasta un minuto")
            resultado = ejecutar_tool(nombre, args, cfg)
            log(f"TOOL: {nombre} -> status={resultado.get('status')}")
            # Cuando hay error lo expresamos en lenguaje natural para que el modelo
            # no lo ignore — algunos modelos tienden a pasar por alto el campo status=error
            if resultado.get("status") == "error":
                tool_content = (
                    f"La herramienta {nombre} falló con el siguiente error: "
                    f"{resultado.get('message', 'error desconocido')}. "
                    f"Informa al usuario de que no se pudo guardar."
                )
            else:
                tool_content = json.dumps(resultado, ensure_ascii=False)
            history.append({
                "role": "tool",
                "tool_call_id": llamada["id"],
                "name": nombre,
                "content": tool_content,
            })

        # Segunda llamada: el modelo genera la confirmación verbal
        messages2 = [{"role": "system", "content": system_prompt}] + history
        t1 = time.monotonic()
        msg2 = llm_client.chat(messages2, cfg, log)
        log(f"LLM (confirmación) elapsed={time.monotonic() - t1:.2f}s")
        content = msg2["content"].strip()
    else:
        content = msg["content"].strip()

    history.append({"role": "assistant", "content": content})
    return content


# --------- TTS (servidor de voz remoto) ---------
_OVERLAY_SCRIPT = Path(__file__).parent.parent / "overlay" / "somi-overlay.py"
_LAYER_SHELL_SO  = "/usr/lib/libgtk4-layer-shell.so"


def play(wav: Path) -> None:
    overlay = _launch_overlay()
    subprocess.run(["paplay", str(wav)], check=False)
    _kill_overlay(overlay)


def hablar(text: str, cfg: dict, log) -> bool:
    """Sintetiza y reproduce la respuesta.

    En modo streaming (default) sintetiza y reproduce a la vez: el overlay
    aparece al llegar el primer trozo de audio, no antes de empezar la
    petición. Devuelve False si el servidor de voz falla."""
    from text_tts import normalizar_para_tts

    text_norm = normalizar_para_tts(text)
    if text_norm != text:
        log(f"TTS normalizado: '{text_norm[:80]}'")
    text = text_norm

    if cfg["tts"].get("stream", True):
        return _hablar_stream(text, cfg, log)
    return _hablar_wav(text, cfg, log)


def _hablar_stream(text: str, cfg: dict, log) -> bool:
    try:
        fmt, trozos = voice_api.abrir_stream(text, cfg, log)
    except voice_api.VoiceAPIError as e:
        log(f"TTS error: {e}")
        return False

    proc = subprocess.Popen(
        [
            "paplay", "--raw",
            f"--rate={fmt['rate']}",
            f"--channels={fmt['channels']}",
            "--format=s16le",
        ],
        stdin=subprocess.PIPE,
    )
    overlay = None
    t0 = time.monotonic()
    ok = True
    try:
        for i, trozo in enumerate(trozos):
            if i == 0:
                log(f"TTS (stream) primer audio a los {time.monotonic() - t0:.2f}s")
                overlay = _launch_overlay()
            proc.stdin.write(trozo)
    except voice_api.VoiceAPIError as e:
        log(f"TTS error durante el stream: {e}")
        ok = False
    except BrokenPipeError:
        log("TTS: paplay cerró stdin (¿turno cancelado?)")
        ok = False
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.wait()
        _kill_overlay(overlay)
    return ok


def _hablar_wav(text: str, cfg: dict, log) -> bool:
    out_path = Path(expand(cfg["runtime"]["response_wav"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    try:
        voice_api.descargar_wav(text, cfg, log, out_path)
    except voice_api.VoiceAPIError as e:
        log(f"TTS error: {e}")
        return False
    play(out_path)
    return True


def _launch_overlay() -> subprocess.Popen | None:
    if not _OVERLAY_SCRIPT.exists():
        return None
    try:
        env = os.environ.copy()
        # gtk4-layer-shell debe preceder a libwayland en el linker
        if Path(_LAYER_SHELL_SO).exists():
            env["LD_PRELOAD"] = _LAYER_SHELL_SO
        proc = subprocess.Popen(
            [sys.executable, str(_OVERLAY_SCRIPT)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.25)   # margen para que la ventana aparezca
        return proc
    except Exception:
        return None


def _kill_overlay(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


# --------- main ---------
def main() -> int:
    if len(sys.argv) != 2:
        print("usage: pipeline.py <wav_file>", file=sys.stderr)
        return 2
    wav = Path(sys.argv[1])
    if not wav.exists():
        print(f"WAV not found: {wav}", file=sys.stderr)
        return 2

    cfg = load_config()
    log = _log_writer(Path(expand(cfg["runtime"]["log_file"])))

    # SIGTERM handler: salida limpia (Alt+Z durante el pipeline). Ya no hay
    # VRAM de LLM que liberar: el modelo vive en el servidor remoto.
    def _on_sigterm(signum, frame):
        log("SIGTERM recibido — salida")
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_sigterm)
    t_start = time.monotonic()
    log("==================== turn start ====================")

    try:
        user_text = transcribe(wav, cfg, log)
    except voice_api.VoiceAPIError as e:
        notify("❌ STT falló", str(e)[:120], urgency="critical")
        log(f"abort: STT error: {e}")
        return 1
    if user_text is None:
        notify("🤷 No te oí", "Vuelve a pulsar e intenta de nuevo")
        log("abort: STT empty/silence")
        return 0
    log(f"USER: {user_text}")

    history = load_history(cfg, log)
    try:
        assistant_text = llm_chat(history, user_text, cfg, log)
    except Exception as e:
        log(f"LLM error: {e}")
        notify("❌ LLM caído", str(e)[:80], urgency="critical")
        return 1
    log(f"BIRD: {assistant_text}")
    save_history(history, cfg)

    # El log de "turn total" mide STT+LLM (el trabajo antes de que se oiga
    # nada); la reproducción/streaming va después y no cuenta como parte del
    # "proceso" en sí.
    log(f"turn total={time.monotonic() - t_start:.2f}s")

    if not hablar(assistant_text, cfg, log):
        notify("❌ TTS falló", "Mira logs/pipeline.log", urgency="critical")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
