#!/usr/bin/env bash
# somi-doctor.sh — Diagnóstico de la instalación de SOMI.
#
# Solo lectura: no toca configuración, no reinicia nada, no imprime tokens.
# Sale con 0 si todo está OK, 1 si algo falla (los avisos no cambian el exit).

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE="$HOME/.local/share/asistente-voz"
VENV_PYTHON="$BASE/venv/bin/python"
BINDINGS="$HOME/.config/hypr/bindings.lua"
CONFIG="$REPO/config.toml"
LAYER_SHELL_SO="/usr/lib/libgtk4-layer-shell.so"

FAILS=0
WARNS=0

if [[ -t 1 ]]; then
    G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; B=$'\e[1m'; N=$'\e[0m'
else
    G=""; R=""; Y=""; B=""; N=""
fi

section() { printf '\n%s== %s ==%s\n' "$B" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
fail() { printf '  %s✗%s %s\n' "$R" "$N" "$1"; FAILS=$((FAILS+1)); }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1"; WARNS=$((WARNS+1)); }
info() { printf '    %s\n' "$1"; }

# --------------------------------------------------------------------------
section "Repo y keybind"

info "repo: $REPO"

if [[ -f "$BINDINGS" ]]; then
    if grep -qF "$REPO/bin/asistente-toggle.sh" "$BINDINGS"; then
        ok "Alt+Z apunta a este repo"
    elif grep -q "asistente-toggle.sh" "$BINDINGS"; then
        fail "el keybind apunta a OTRA copia del repo (¿clonado dos veces?)"
        grep -n "asistente-toggle.sh" "$BINDINGS" | sed 's/^/    /'
    else
        fail "no hay ningún bind a asistente-toggle.sh en $BINDINGS"
    fi
    grep -qF "$REPO/bin/asistente-clear.sh" "$BINDINGS" \
        && ok "Alt+Shift+Z (clear) apunta a este repo" \
        || warn "sin bind de asistente-clear.sh a este repo"
else
    fail "no existe $BINDINGS"
fi

if git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
    info "rama:   $(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
    info "commit: $(git -C "$REPO" log -1 --format='%h %s' 2>/dev/null)"
    dirty=$(git -C "$REPO" status --porcelain)
    if [[ -n "$dirty" ]]; then
        n=$(wc -l <<<"$dirty")
        warn "$n cambio(s) sin commitear (corren igualmente, pero no están guardados)"
        head -8 <<<"$dirty" | sed 's/^/    /'
        (( n > 8 )) && info "... y $((n - 8)) más"
    else
        ok "árbol de trabajo limpio"
    fi
else
    warn "el repo no es un checkout de git"
fi

# --------------------------------------------------------------------------
section "Entorno de Python"

if [[ -x "$VENV_PYTHON" ]]; then
    ok "venv: $("$VENV_PYTHON" --version 2>&1)"
    if err=$("$VENV_PYTHON" -c 'import gi, num2words' 2>&1); then
        ok "imports del venv (gi, num2words)"
    else
        fail "faltan dependencias en el venv — uv pip install -r $REPO/requirements.txt"
        info "${err##*$'\n'}"
    fi
else
    fail "no existe el python del venv ($VENV_PYTHON)"
fi

# --------------------------------------------------------------------------
section "Binarios del sistema"

for cmd in parecord paplay pactl ffprobe notify-send rg curl; do
    command -v "$cmd" >/dev/null 2>&1 \
        && ok "$cmd" \
        || fail "falta $cmd"
done
[[ -f "$LAYER_SHELL_SO" ]] \
    && ok "gtk4-layer-shell" \
    || warn "falta $LAYER_SHELL_SO — el overlay no se mostrará"

# --------------------------------------------------------------------------
section "Estado y credenciales"

for d in "$BASE/tmp" "$BASE/data/logs"; do
    [[ -d "$d" ]] && ok "${d/#$HOME/\~}" || fail "falta el directorio ${d/#$HOME/\~}"
done
for f in "$BASE/lm-token" "$BASE/voice-api-token"; do
    if [[ -s "$f" ]]; then
        perms=$(stat -c '%a' "$f")
        [[ "$perms" == "600" ]] \
            && ok "${f/#$HOME/\~} (600)" \
            || warn "${f/#$HOME/\~} presente pero con permisos $perms (esperado 600)"
    else
        fail "falta o está vacío ${f/#$HOME/\~}"
    fi
done

# --------------------------------------------------------------------------
section "config.toml"

PY="${VENV_PYTHON}"
[[ -x "$PY" ]] || PY="$(command -v python3)"

cfg_dump=""
if [[ ! -f "$CONFIG" ]]; then
    fail "no existe $CONFIG"
elif ! cfg_dump=$("$PY" - "$CONFIG" <<'PY' 2>&1
import sys, tomllib
from pathlib import Path
with open(sys.argv[1], "rb") as fh:
    cfg = tomllib.load(fh)
for k in ("stt", "tts", "llm"):
    print(f"{k}_endpoint={cfg.get(k, {}).get('endpoint', '')}")
print(f"llm_model={cfg.get('llm', {}).get('model', '')}")
print(f"llm_key_file={Path(cfg.get('llm', {}).get('api_key_file', '')).expanduser()}")
print(f"voice_key_file={Path(cfg.get('tts', {}).get('api_key_file', '')).expanduser()}")
print(f"vault={cfg.get('vault', {}).get('path', '')}")
print(f"tools_habilitado={cfg.get('tools', {}).get('habilitado', True)}")
PY
    ); then
    fail "config.toml no parsea"
    info "${cfg_dump##*$'\n'}"
    cfg_dump=""
else
    ok "config.toml parsea"
    eval "$(printf '%s\n' "$cfg_dump" | sed 's/^\([a-z_]*\)=\(.*\)$/\1="\2"/')"
    info "modelo LLM: ${llm_model:-?}"
    [[ -d "${vault:-}" ]] \
        && ok "vault: $vault" \
        || fail "el vault no existe: ${vault:-<sin definir>}"
    [[ "${tools_habilitado:-True}" == "True" ]] \
        || warn "[tools] habilitado = false — el LLM no puede llamar a las tools"
fi

# --------------------------------------------------------------------------
section "Servidores remotos"

http_code() { curl -s -m 10 -o /dev/null -w '%{http_code}' "$@" 2>/dev/null; }

if [[ -n "${tts_endpoint:-}" ]]; then
    voice_base="${tts_endpoint%/v1}"
    code=$(http_code "$voice_base/health")
    [[ "$code" == "200" ]] \
        && ok "servidor de voz (STT/TTS): $voice_base — HTTP 200" \
        || fail "servidor de voz no responde: $voice_base/health — HTTP ${code:-sin respuesta}"
fi

if [[ -n "${llm_endpoint:-}" && -s "${llm_key_file:-/dev/null}" ]]; then
    models=$(curl -s -m 10 -H "Authorization: Bearer $(cat "$llm_key_file")" \
                  "$llm_endpoint/models" 2>/dev/null)
    if [[ -z "$models" ]]; then
        fail "el LLM no responde: $llm_endpoint/models"
    elif grep -qF "\"${llm_model}\"" <<<"$models"; then
        ok "LLM responde y '$llm_model' está cargado"
    elif grep -q '"id"' <<<"$models"; then
        fail "'$llm_model' NO está cargado en LM Studio"
        info "cargados: $(grep -o '"id"[[:space:]]*:[[:space:]]*"[^"]*"' <<<"$models" \
                          | sed 's/.*"\([^"]*\)"$/\1/' | paste -sd', ')"
    else
        fail "respuesta inesperada del LLM (¿token inválido?): ${models:0:120}"
    fi
elif [[ -n "${llm_endpoint:-}" ]]; then
    warn "sin token del LLM, no puedo comprobar los modelos cargados"
fi

# --------------------------------------------------------------------------
section "Estado en runtime"

if [[ -f /tmp/somi-recording.pid ]]; then
    pid=$(cat /tmp/somi-recording.pid 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        info "grabación en curso (pid $pid)"
    else
        warn "/tmp/somi-recording.pid huérfano (pid $pid muerto) — se limpia al pulsar Alt+Z"
    fi
fi
if [[ -f /tmp/somi-pipeline.pgid ]]; then
    pgid=$(cat /tmp/somi-pipeline.pgid 2>/dev/null)
    if kill -0 -- "-$pgid" 2>/dev/null; then
        info "pipeline en curso (pgid $pgid)"
    else
        warn "/tmp/somi-pipeline.pgid huérfano (pgid $pgid muerto) — se limpia al pulsar Alt+Z"
    fi
fi
last_turn=$(grep -a 'turn start' "$BASE/data/logs/pipeline.log" 2>/dev/null | tail -1 | cut -d' ' -f1-2)
[[ -n "$last_turn" ]] && info "último turno: $last_turn"

# --------------------------------------------------------------------------
printf '\n'
if (( FAILS == 0 )); then
    printf '%s✓ SOMI listo%s (%d avisos)\n' "$G" "$N" "$WARNS"
    exit 0
fi
printf '%s✗ %d comprobación(es) fallida(s)%s (%d avisos)\n' "$R" "$FAILS" "$N" "$WARNS"
exit 1
