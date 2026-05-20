#!/usr/bin/env bash
# asistente-clear.sh — Limpia el historial de conversación, rotándolo a un archivo con timestamp.
# Disparado por Alt+Shift+Z en CP-6.

set -euo pipefail

BASE="$HOME/.local/share/asistente-voz"
HIST="$BASE/data/conversation.json"
ROT_DIR="$BASE/data/history"
LOG="$BASE/data/logs/clear.log"

mkdir -p "$ROT_DIR" "$(dirname "$LOG")"

ts=$(date '+%Y%m%d-%H%M%S')
echo "$(date '+%Y-%m-%d %H:%M:%S') invoked" >> "$LOG"

if [[ -f "$HIST" ]]; then
    target="$ROT_DIR/conversation-${ts}.json"
    mv "$HIST" "$target"
    echo "  rotated $HIST -> $target" >> "$LOG"
    notify-send -a "SOMI" -h "string:x-canonical-private-synchronous:somi" \
        "🧹 Historial limpiado" "Nueva conversación lista"
else
    notify-send -a "SOMI" -h "string:x-canonical-private-synchronous:somi" \
        "🧹 Ya estaba vacío" "Sin historial que limpiar"
fi
