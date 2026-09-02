# SOMI — asistente de voz local

Asistente de voz por pulsación (push-to-talk con toggle) para Hyprland. Grabas
con `Alt+Z`, vuelves a pulsar y el turno completo —transcripción, respuesta del
LLM y síntesis de voz— sale por los altavoces con un HUD estilo Cyberpunk 2077
mientras habla. La personalidad es **Song So Mi / Songbird**, definida en el
`system_prompt` de `config.toml`.

El cómputo pesado no corre aquí: STT, TTS y el LLM son servicios remotos. Este
repo es el **cliente** que los orquesta.

## Cómo funciona

```
ALT+Z  (~/.config/hypr/bindings.lua)  ->  bin/asistente-toggle.sh
  IDLE      -> parecord 16 kHz mono s16le -> ~/.local/share/asistente-voz/tmp/recording.wav
  RECORDING -> SIGINT a parecord + setsid $VENV/bin/python lib/pipeline.py <wav>
  RUNNING   -> mata el process group entero (LLM/TTS/paplay) y vuelve a grabar
                   │
                   ├─ STT   POST <stt.endpoint>/audio/transcriptions
                   ├─ LLM   POST <llm.endpoint>/chat/completions   (+ tools de tools/)
                   ├─ TTS   POST <tts.endpoint>/audio/speech       (stream -> paplay)
                   └─ overlay/somi-overlay.py  (GTK4 layer-shell, muere con el audio)

ALT+SHIFT+Z  ->  bin/asistente-clear.sh   (rota el historial de conversación)
```

| Pieza | Dónde vive |
|---|---|
| Código (scripts, pipeline, tools, overlay) | **este repo** |
| Configuración | `config.toml` (raíz del repo, se relee en cada turno) |
| venv de Python | `~/.local/share/asistente-voz/venv` |
| Tokens, historial, logs, WAVs temporales | `~/.local/share/asistente-voz/` |
| Keybinds | `~/.config/hypr/bindings.lua` |
| STT + TTS | servidor Docker en la máquina Windows — ver [docs/servidor-voz.md](docs/servidor-voz.md) |
| LLM + embeddings | LM Studio en la máquina Windows |

**No hay paso de compilación ni instalación del código.** El keybind apunta con
rutas absolutas a `bin/` de este repo, y `lib/pipeline.py` resuelve
`config.toml`, `tools/` y `overlay/` relativos a su propia ubicación. Lo que
guardes en el repo es lo que corre en el siguiente `Alt+Z`.

## Instalación

### 1. Clonar el repo

```bash
git clone <url> ~/Documents/projects/python/SOMI
```

Las rutas de los keybinds (paso 5) asumen esa ubicación. Si lo pones en otro
sitio, ajústalas.

### 2. Crear el venv e instalar dependencias

```bash
uv venv --python 3.12 ~/.local/share/asistente-voz/venv
uv pip install --python ~/.local/share/asistente-voz/venv/bin/python \
    -r requirements.txt          # requirements-dev.txt para poder correr los tests
```

El overlay se lanza con `sys.executable`, es decir el python del venv
(`lib/pipeline.py`), y el venv **no** hereda los paquetes del sistema: por eso
`PyGObject` tiene que estar dentro del venv y no basta con tenerlo en el
sistema.

### 3. Directorios de estado y tokens

```bash
mkdir -p ~/.local/share/asistente-voz/{tmp,models,data/logs,data/history}

# tokens (una sola línea cada uno, sin salto final)
printf '%s' 'TOKEN_DE_LM_STUDIO'   > ~/.local/share/asistente-voz/lm-token
printf '%s' 'TOKEN_DEL_SERVIDOR_VOZ' > ~/.local/share/asistente-voz/voice-api-token
chmod 600 ~/.local/share/asistente-voz/{lm-token,voice-api-token}
```

Los tokens viven **fuera** del repo a propósito: nunca se commitean.

### 4. Paquetes del sistema (Arch / CachyOS)

```bash
sudo pacman -S --needed libpulse ffmpeg libnotify ripgrep gtk4-layer-shell
```

`libpulse` trae `parecord`/`paplay`/`pactl` (grabar y reproducir), `ffmpeg` trae
`ffprobe` (duración de la grabación), `libnotify` las notificaciones,
`ripgrep` la búsqueda en el vault de Obsidian y `gtk4-layer-shell` el overlay
(se precarga `/usr/lib/libgtk4-layer-shell.so` vía `LD_PRELOAD`).

### 5. Keybinds de Hyprland

En `~/.config/hypr/bindings.lua`:

```lua
-- SOMI voice assistant
hl.bind("ALT + Z", hl.dsp.exec_cmd("/home/penguin/Documents/projects/python/SOMI/bin/asistente-toggle.sh"), { description = "SOMI toggle (grabar/parar/cancelar)" })
hl.bind("ALT + SHIFT + Z", hl.dsp.exec_cmd("/home/penguin/Documents/projects/python/SOMI/bin/asistente-clear.sh"), { description = "SOMI clear history" })
```

### 6. Ajustar `config.toml`

Endpoints de `[stt]`, `[tts]`, `[llm]` y `[embeddings]`, el `model` que tengas
cargado en LM Studio, y `[vault] path` apuntando a tu vault de Obsidian.

### 7. Comprobar que todo está en su sitio

```bash
./bin/somi-doctor.sh
```

Verifica keybind, venv, binarios, tokens, config y que los dos servidores
remotos respondan. Si sale todo ✓, pulsa `Alt+Z` y habla.

## Actualizar y verificar la versión

No hay build, ni daemon, ni copia instalada del código: **siempre corre lo que
hay en el repo**. Guardas un `.py` y el siguiente `Alt+Z` ya lo usa;
`config.toml` se relee en cada turno; los `.pyc` no engañan porque Python los
invalida por fecha y tamaño.

Para confirmarlo:

```bash
./bin/somi-doctor.sh                  # incluye rama, último commit y si hay cambios sin commitear
ps -ef | grep pipeline.py             # desde qué ruta corre el turno actual
tail -f ~/.local/share/asistente-voz/data/logs/pipeline.log   # pulsa Alt+Z y míralo en vivo
```

Lo que **sí** puede quedarse desactualizado es la otra mitad, que no vive en
este repo:

- el **servidor de voz** (Docker en la Windows) — ver [docs/servidor-voz.md](docs/servidor-voz.md);
- el **modelo cargado en LM Studio**, que tiene que coincidir con `[llm] model`
  de `config.toml`. `somi-doctor.sh` lo comprueba.

## Logs

| Fichero (bajo `~/.local/share/asistente-voz/data/logs/`) | Qué trae |
|---|---|
| `toggle.log` | máquina de estados del keybind: IDLE / RECORDING / cancelaciones |
| `pipeline.log` | el turno: tiempos de STT, LLM y TTS, texto del usuario y respuesta |
| `pipeline-runtime.log` | stdout/stderr crudo del pipeline (tracebacks) |
| `clear.log` | rotaciones del historial |

## Tests

```bash
~/.local/share/asistente-voz/venv/bin/python -m pytest -q
```

## Estructura

```
bin/          scripts disparados por los keybinds + somi-doctor.sh
lib/          pipeline.py (orquestador), voice_api.py (STT/TTS), llm_client.py, text_tts.py
tools/        tools que el LLM puede llamar (Obsidian: notas, pendientes, diario, entrenos…)
overlay/      HUD GTK4 que aparece mientras habla
tests/        pytest
config.toml   endpoints, modelos, system prompt, paths
docs/         documentación del servidor de voz remoto
plan.md       plan de desarrollo
```
