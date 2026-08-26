#!/usr/bin/env bash
# asistente-toggle.sh — Trigger toggle de SOMI.
#
# Estados:
#   IDLE              -> empieza grabación
#   RECORDING         -> detiene grabación y lanza pipeline en background
#   PIPELINE_RUNNING  -> cancela todo el árbol (LLM/TTS/paplay) y empieza nueva grabación
#
# Ficheros de estado:
#   /tmp/somi-recording.pid   PID de parecord
#   /tmp/somi-pipeline.pgid   PGID del proceso pipeline (con setsid)

set -euo pipefail

BASE="$HOME/.local/share/asistente-voz"
TMP_DIR="$BASE/tmp"
LOG_DIR="$BASE/data/logs"
RECORD_PID_FILE="/tmp/somi-recording.pid"
PIPELINE_PGID_FILE="/tmp/somi-pipeline.pgid"
WAV_FILE="$TMP_DIR/recording.wav"
LOG_FILE="$LOG_DIR/toggle.log"
PIPELINE_LOG="$LOG_DIR/pipeline-runtime.log"
PIPELINE_PY="$HOME/Documents/projects/python/SOMI/lib/pipeline.py"
# Python del venv: tiene f5_tts y soundfile instalados
VENV_PYTHON="$HOME/.local/share/asistente-voz/venv/bin/python"

mkdir -p "$TMP_DIR" "$LOG_DIR"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S.%3N') [pid $$] $*" >> "$LOG_FILE"
}

notify() {
    notify-send -a "SOMI" -h "string:x-canonical-private-synchronous:somi" "$@" || true
}

pipeline_running() {
    [[ -f "$PIPELINE_PGID_FILE" ]] || return 1
    local pgid
    pgid=$(cat "$PIPELINE_PGID_FILE" 2>/dev/null || true)
    [[ -n "$pgid" ]] || { rm -f "$PIPELINE_PGID_FILE"; return 1; }
    # kill -0 -PGID comprueba existencia del grupo
    if kill -0 -- "-$pgid" 2>/dev/null; then
        return 0
    fi
    rm -f "$PIPELINE_PGID_FILE"
    return 1
}

cancel_pipeline() {
    local pgid
    pgid=$(cat "$PIPELINE_PGID_FILE" 2>/dev/null || true)
    rm -f "$PIPELINE_PGID_FILE"
    if [[ -z "$pgid" ]]; then
        return 0
    fi
    log "cancel: SIGTERM al pgid $pgid"
    kill -TERM -- "-$pgid" 2>/dev/null || true
    # Espera 2s para que el pipeline pueda hacer cleanup (e.g. unload del LLM)
    local i=0
    while kill -0 -- "-$pgid" 2>/dev/null && (( i < 20 )); do
        sleep 0.1
        i=$((i+1))
    done
    if kill -0 -- "-$pgid" 2>/dev/null; then
        log "cancel: SIGKILL al pgid $pgid"
        kill -KILL -- "-$pgid" 2>/dev/null || true
    fi
}

start_recording() {
    rm -f "$WAV_FILE"
    log "start: lanzando parecord (16kHz mono s16le)"
    parecord --rate=16000 --channels=1 --format=s16le "$WAV_FILE" &
    local rec_pid=$!
    echo "$rec_pid" > "$RECORD_PID_FILE"
    log "start: pid=$rec_pid"
    notify "🎤 Grabando..." "Pulsa Alt+Z otra vez para parar"
}

stop_and_launch_pipeline() {
    local rec_pid
    rec_pid=$(cat "$RECORD_PID_FILE" 2>/dev/null || true)
    rm -f "$RECORD_PID_FILE"

    if [[ -z "$rec_pid" ]] || ! kill -0 "$rec_pid" 2>/dev/null; then
        log "stop: pid huérfano o muerto ($rec_pid)"
        notify -u critical "⚠️ Estado limpio" "PID huérfano descartado"
        return 0
    fi

    log "stop: SIGINT a parecord $rec_pid"
    kill -INT "$rec_pid" 2>/dev/null || true
    local i=0
    while kill -0 "$rec_pid" 2>/dev/null && (( i < 30 )); do
        sleep 0.1
        i=$((i+1))
    done
    if kill -0 "$rec_pid" 2>/dev/null; then
        kill -KILL "$rec_pid" 2>/dev/null || true
    fi

    if [[ ! -s "$WAV_FILE" ]]; then
        log "stop: WAV vacío ($WAV_FILE)"
        notify -u critical "❌ Grabación vacía" "Revisa el micrófono"
        return 0
    fi

    local dur
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$WAV_FILE" 2>/dev/null || echo "?")
    log "stop: WAV listo, dur=${dur}s"
    notify "🧠 Pensando..." "Grabación: ${dur}s"

    # Lanza el pipeline en un nuevo process group (setsid) para poder matarlo entero después.
    setsid "$VENV_PYTHON" "$PIPELINE_PY" "$WAV_FILE" >> "$PIPELINE_LOG" 2>&1 &
    local pipe_pid=$!
    # Pequeña espera para que setsid setee el nuevo session/pgid antes de leerlo
    sleep 0.05
    local pgid
    pgid=$(ps -o pgid= -p "$pipe_pid" 2>/dev/null | tr -d ' ' || true)
    if [[ -n "$pgid" ]]; then
        echo "$pgid" > "$PIPELINE_PGID_FILE"
        log "launch: pipeline pid=$pipe_pid pgid=$pgid"
    else
        log "launch: no pude leer PGID de $pipe_pid (proceso ya terminó?)"
    fi
}

log "===== invocado ====="

if pipeline_running; then
    log "estado: PIPELINE_RUNNING -> cancelar + nueva grabación"
    cancel_pipeline
    notify "❌ Cancelado" "Empezando nueva grabación..."
    start_recording
elif [[ -f "$RECORD_PID_FILE" ]]; then
    log "estado: RECORDING -> stop + lanzar pipeline"
    stop_and_launch_pipeline
else
    log "estado: IDLE -> start"
    start_recording
fi

log "===== fin ====="
