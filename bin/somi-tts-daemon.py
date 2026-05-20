#!/usr/bin/env python3
"""SOMI F5-TTS daemon.

Mantiene el modelo cargado entre turnos. Escucha en /tmp/somi-tts.sock (Unix
socket). En idle el modelo vive en CPU/RAM; para cada petición hace swap a
GPU, infiere, vuelve a CPU. Así Llama 3.1 puede ocupar VRAM sin oversubscribe.

Protocolo: el cliente envía un JSON por línea, recibe un JSON por línea.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
import tomllib
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config.toml"
SOCKET_PATH = "/tmp/somi-tts.sock"


def expand(p: str) -> str:
    return os.path.expanduser(str(p))


def _logp(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def main() -> int:
    t0 = time.monotonic()
    from f5_tts.api import F5TTS  # noqa: F401 (imported here to time it)
    import soundfile as sf
    import torch
    _logp(f"import: {time.monotonic() - t0:.2f}s")

    with open(CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)

    t0 = time.monotonic()
    tts = F5TTS(
        model=cfg["tts"]["model_name"],
        ckpt_file=expand(cfg["tts"]["ckpt"]),
        vocab_file=expand(cfg["tts"]["vocab"]),
    )
    _logp(f"load: {time.monotonic() - t0:.2f}s on {tts.device}")

    # Cold-store en CPU para no robar VRAM mientras no hay petición.
    def to_cpu() -> None:
        tts.ema_model = tts.ema_model.to("cpu")
        tts.vocoder = tts.vocoder.to("cpu")
        tts.device = "cpu"
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def to_gpu() -> None:
        tts.ema_model = tts.ema_model.to("cuda")
        tts.vocoder = tts.vocoder.to("cuda")
        tts.device = "cuda"

    to_cpu()
    _logp("ready (model parked on CPU)")

    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o600)
    server.listen(1)

    def cleanup(*_: object) -> None:
        _logp("cleanup, shutting down")
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        finally:
            sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    while True:
        conn, _addr = server.accept()
        conn.settimeout(120.0)
        try:
            # Lee hasta encontrar un newline
            buf = bytearray()
            while True:
                chunk = conn.recv(8192)
                if not chunk:
                    break
                buf.extend(chunk)
                if buf.endswith(b"\n"):
                    break
            req = json.loads(buf.decode("utf-8"))

            t_swap_in = time.monotonic()
            to_gpu()
            swap_in = time.monotonic() - t_swap_in

            t_infer = time.monotonic()
            wav, sr, _ = tts.infer(
                ref_file=req["ref_audio"],
                ref_text=req["ref_text"],
                gen_text=req["gen_text"],
                seed=req.get("seed"),
                nfe_step=req.get("nfe_step", 32),
                cfg_strength=req.get("cfg_strength", 2.0),
                speed=req.get("speed", 1.0),
                show_info=lambda *a, **k: None,
                progress=None,
            )
            infer_t = time.monotonic() - t_infer

            t_write = time.monotonic()
            sf.write(req["out_path"], wav, sr)
            write_t = time.monotonic() - t_write

            t_swap_out = time.monotonic()
            to_cpu()
            swap_out = time.monotonic() - t_swap_out

            resp = {
                "status": "ok",
                "dur_s": float(len(wav) / sr),
                "timings": {
                    "swap_in": round(swap_in, 3),
                    "infer": round(infer_t, 3),
                    "write": round(write_t, 3),
                    "swap_out": round(swap_out, 3),
                },
            }
            _logp(
                f"served '{req['gen_text'][:60]}...' "
                f"swap_in={swap_in:.2f} infer={infer_t:.2f} swap_out={swap_out:.2f}"
            )
        except Exception as e:
            resp = {"status": "error", "error": str(e)}
            _logp(f"error: {e}")
            # Asegurar que el modelo vuelva a CPU si falló en mitad
            try:
                to_cpu()
            except Exception:
                pass

        try:
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main() or 0)
