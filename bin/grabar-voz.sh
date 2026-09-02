#!/usr/bin/env bash
# Graba una muestra de voz desde el micrófono por defecto (PipeWire).
# Salida: ~/.local/share/asistente-voz/models/f5-tts/reference-voice.wav (24kHz mono S16LE).
#
# NOTA: el TTS ya no corre en local (F5-TTS) — la voz clonada vive en el
# servidor remoto (chat-somi.underpenguin.com). Para registrar una voz nueva
# ahí, sube este wav con POST /v1/voices (ver README.md). Este script queda
# solo para producir el wav de referencia.

set -euo pipefail

OUTPUT_DIR="$HOME/.local/share/asistente-voz/models/f5-tts"
mkdir -p "$OUTPUT_DIR"
OUT="$OUTPUT_DIR/reference-voice.wav"
TMP="$(mktemp --suffix=.wav)"
trap 'rm -f "$TMP"' EXIT

TEXTO='Hola, soy una persona normal grabando una muestra de voz para entrenar mi asistente. Hoy es jueves veintiuno y son las cuatro y media de la tarde. ¿Te parece bien si empezamos? Quiero que esta voz suene natural, no robótica, con pausas reales y entonación viva.'

echo
echo "=============================================="
echo "  Grabación de voz para F5-TTS — SOMI"
echo "=============================================="
echo
echo "Vas a leer este texto en voz alta (~15-20s):"
echo
echo "--- texto ---"
echo "$TEXTO"
echo "-------------"
echo
echo "Consejos:"
echo "  · Habla a tu volumen y velocidad natural."
echo "  · No te apures. F5-TTS clonará lo que oiga, incluso el tono."
echo "  · Si te equivocas mucho, puedes reintentar al final."
echo
echo "Fuente: $(pactl get-default-source)"
echo
read -rp "Pulsa ENTER para empezar a grabar..."
echo
echo "🎤 Grabando... pulsa ENTER cuando termines de leer."

parecord --rate=24000 --channels=1 --format=s16le "$TMP" &
REC_PID=$!

# Espera ENTER para detener
read -r
kill -TERM "$REC_PID" 2>/dev/null || true
wait "$REC_PID" 2>/dev/null || true

DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP" 2>/dev/null || echo "?")
echo
echo "✅ Grabado (${DUR}s). Reproduciendo..."
paplay "$TMP"

echo
read -rp "¿Guardar como reference-voice.wav? [s=sí / r=reintentar / n=descartar]: " resp
case "${resp,,}" in
    s)
        mv "$TMP" "$OUT"
        trap - EXIT
        echo "💾 Guardado: $OUT"
        ls -lh "$OUT"
        ;;
    r)
        echo "🔁 Reintentando..."
        exec "$0"
        ;;
    *)
        echo "❌ Descartado."
        exit 1
        ;;
esac
