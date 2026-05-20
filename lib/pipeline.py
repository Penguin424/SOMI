#!/usr/bin/env python3
"""SOMI pipeline: WAV -> STT (whisper.cpp) -> LLM (Ollama) -> TTS (F5-Spanish) -> paplay.

Uso: pipeline.py <wav_file>
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.toml"
TTS_SOCKET = "/tmp/somi-tts.sock"

SILENCE_MARKERS = (
    "[BLANK_AUDIO]", "[blank_audio]",
    "[NO_SPEECH]", "[no_speech]",
    "(música)", "[Música]", "[música]",
    "(music)", "[Music]", "[music]",
    "(silence)", "[silence]",
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


# --------- STT ---------
def transcribe(wav: Path, cfg: dict, log) -> str | None:
    out_prefix = wav.parent / wav.stem
    cmd = [
        expand(cfg["stt"]["whisper_bin"]),
        "-m", expand(cfg["stt"]["whisper_model"]),
        "-f", str(wav),
        "-l", cfg["stt"]["language"],
        "-t", str(cfg["stt"]["threads"]),
        "--no-prints",
        "--output-txt",
        "--output-file", str(out_prefix),
    ]
    log(f"STT cmd: {' '.join(cmd)}")
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log(f"STT elapsed={time.monotonic() - t0:.2f}s rc={proc.returncode}")
    if proc.returncode != 0:
        log(f"STT stderr: {proc.stderr[-400:]}")
        return None
    txt_file = Path(str(out_prefix) + ".txt")
    if not txt_file.exists():
        log("STT: no txt file produced")
        return None
    text = txt_file.read_text(encoding="utf-8").strip()
    txt_file.unlink(missing_ok=True)
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
        log(f"history: loaded {len(data)} messages (age {age_min:.1f}min)")
        return data
    except Exception as e:
        log(f"history: corrupt ({e}), starting fresh")
        return []


def save_history(history: list[dict], cfg: dict) -> None:
    hist_file = Path(expand(cfg["history"]["file"]))
    hist_file.parent.mkdir(parents=True, exist_ok=True)
    with open(hist_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# --------- LLM (Ollama) ---------
def _http_post(url: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def llm_chat(history: list[dict], user_text: str, cfg: dict, log) -> str:
    history.append({"role": "user", "content": user_text})
    messages = [{"role": "system", "content": cfg["llm"]["system_prompt"]}] + history
    payload = {
        "model": cfg["llm"]["model"],
        "messages": messages,
        "stream": False,
        "keep_alive": cfg["llm"]["keep_alive"],
    }
    log(f"LLM: msgs={len(messages)} user='{user_text[:80]}'")
    t0 = time.monotonic()
    resp = _http_post(cfg["llm"]["endpoint"] + "/api/chat", payload)
    log(f"LLM elapsed={time.monotonic() - t0:.2f}s")
    content = resp["message"]["content"].strip()
    history.append({"role": "assistant", "content": content})
    return content


def llm_unload(cfg: dict, log) -> None:
    """Fuerza unload del modelo para liberar VRAM antes de cargar F5-TTS.
    Hace polling a /api/ps hasta confirmar que Ollama efectivamente liberó la GPU,
    porque keep_alive=0 es asíncrono y tarda 1-2s en aplicarse."""
    try:
        _http_post(
            cfg["llm"]["endpoint"] + "/api/generate",
            {"model": cfg["llm"]["model"], "keep_alive": 0},
            timeout=10,
        )
        log("LLM: unload requested (keep_alive=0)")
    except Exception as e:
        log(f"LLM: unload failed ({e})")
        return

    target = cfg["llm"]["model"]
    endpoint = cfg["llm"]["endpoint"] + "/api/ps"
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5.0:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as r:
                data = json.loads(r.read())
            loaded_names = [m.get("name", "") for m in data.get("models", [])]
            if target not in loaded_names:
                log(f"LLM: unload confirmed in {time.monotonic() - t0:.2f}s")
                return
        except Exception:
            pass
        time.sleep(0.2)
    log(f"LLM: unload not confirmed after 5s, proceeding anyway")


# --------- TTS (F5-Spanish) ---------
def _seed_from_cfg(cfg: dict) -> int | None:
    v = cfg["tts"].get("seed", "")
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str) and v.strip():
        try:
            return int(v.strip())
        except ValueError:
            return None
    return None


def _synthesize_via_daemon(text: str, cfg: dict, log, out_path: Path, ref_text: str) -> Path | None:
    """Si /tmp/somi-tts.sock existe, manda la petición al daemon F5-TTS."""
    if not Path(TTS_SOCKET).exists():
        return None
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(120.0)
    try:
        sock.connect(TTS_SOCKET)
    except OSError as e:
        log(f"TTS daemon socket present but unreachable ({e})")
        return None

    req = {
        "ref_audio": expand(cfg["tts"]["ref_audio"]),
        "ref_text": ref_text,
        "gen_text": text,
        "out_path": str(out_path),
        "seed": _seed_from_cfg(cfg),
        "nfe_step": cfg["tts"].get("nfe_step", 32),
        "cfg_strength": cfg["tts"].get("cfg_strength", 2.0),
        "speed": cfg["tts"].get("speed", 1.0),
    }
    log(f"TTS (daemon): gen='{text[:80]}'")
    t0 = time.monotonic()
    try:
        sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = bytearray()
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            buf.extend(chunk)
            if buf.endswith(b"\n"):
                break
        resp = json.loads(buf.decode("utf-8"))
    except Exception as e:
        log(f"TTS daemon comm error: {e}")
        return None
    finally:
        try:
            sock.close()
        except Exception:
            pass

    if resp.get("status") != "ok":
        log(f"TTS daemon returned error: {resp.get('error')}")
        return None
    t = resp.get("timings", {})
    log(
        f"TTS (daemon) total={time.monotonic() - t0:.2f}s "
        f"swap_in={t.get('swap_in')} infer={t.get('infer')} swap_out={t.get('swap_out')} "
        f"dur={resp.get('dur_s'):.2f}s"
    )
    return out_path


def _synthesize_cold(text: str, cfg: dict, log, out_path: Path, ref_text: str) -> Path | None:
    """Fallback: importa F5-TTS y genera en el proceso actual (cold start ~9s)."""
    t_import = time.monotonic()
    from f5_tts.api import F5TTS
    import soundfile as sf
    log(f"TTS (cold) import={time.monotonic() - t_import:.2f}s")

    t_load = time.monotonic()
    tts = F5TTS(
        model=cfg["tts"]["model_name"],
        ckpt_file=expand(cfg["tts"]["ckpt"]),
        vocab_file=expand(cfg["tts"]["vocab"]),
    )
    log(f"TTS (cold) load={time.monotonic() - t_load:.2f}s")

    seed = _seed_from_cfg(cfg)
    log(f"TTS (cold): gen='{text[:80]}' seed={seed}")
    t_infer = time.monotonic()
    try:
        wav, sr, _ = tts.infer(
            ref_file=expand(cfg["tts"]["ref_audio"]),
            ref_text=ref_text,
            gen_text=text,
            seed=seed,
            nfe_step=cfg["tts"].get("nfe_step", 32),
            cfg_strength=cfg["tts"].get("cfg_strength", 2.0),
            speed=cfg["tts"].get("speed", 1.0),
            show_info=lambda *a, **k: None,
            progress=None,
        )
    except Exception as e:
        log(f"TTS (cold) error: {e}")
        return None
    log(f"TTS (cold) infer={time.monotonic() - t_infer:.2f}s dur={len(wav)/sr:.2f}s")
    sf.write(str(out_path), wav, sr)
    return out_path


def synthesize(text: str, cfg: dict, log) -> Path | None:
    """Genera audio. Intenta daemon primero, cae a cold-start si no responde."""
    ref_text = Path(expand(cfg["tts"]["ref_text_file"])).read_text(encoding="utf-8").strip()
    out_path = Path(expand(cfg["runtime"]["response_wav"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    result = _synthesize_via_daemon(text, cfg, log, out_path, ref_text)
    if result is not None:
        return result
    log("TTS: daemon no disponible, fallback a cold start")
    return _synthesize_cold(text, cfg, log, out_path, ref_text)


def play(wav: Path) -> None:
    subprocess.run(["paplay", str(wav)], check=False)


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
    t_start = time.monotonic()
    log("==================== turn start ====================")

    user_text = transcribe(wav, cfg, log)
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

    llm_unload(cfg, log)

    out_wav = synthesize(assistant_text, cfg, log)
    if out_wav is None:
        notify("❌ TTS falló", "Mira logs/pipeline.log", urgency="critical")
        return 1

    log(f"turn total={time.monotonic() - t_start:.2f}s")
    play(out_wav)
    return 0


if __name__ == "__main__":
    sys.exit(main())
