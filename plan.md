# Asistente de Voz Local - Plan de Implementación

## Contexto del proyecto

Quiero construir un asistente de voz personal que funcione **100% local**, activado por atajo de teclado, que me permita hablar con un LLM y recibir respuesta hablada usando una voz clonada.

## Hardware y entorno

- **GPU**: NVIDIA RTX 4060 Ti 8GB VRAM
- **CPU**: AMD Ryzen 5 5600G
- **RAM**: 32GB
- **Almacenamiento**: 2TB SSD
- **OS**: CachyOS (basado en Arch Linux)
- **Entorno de escritorio**: Omarchy (Hyprland + utilidades)
- **Compositor**: Hyprland (Wayland)
- **Audio**: PipeWire (asumido por defecto en CachyOS/Omarchy)
- **Notificaciones**: dunst o mako (verificar cuál usa Omarchy)
- **Terminal**: por defecto en Omarchy

## Stack tecnológico decidido

| Componente | Herramienta | Razón |
|------------|-------------|-------|
| LLM runtime | **Ollama** | Auto-unload nativo con `OLLAMA_KEEP_ALIVE`, simple de operar |
| LLM modelo | **Qwen2.5-7B-Instruct Q4_K_M** | Cabe en 8GB VRAM, buen español, deja margen para contexto |
| STT | **whisper.cpp** | Soporte CUDA nativo, rapidísimo, sin dependencias Python pesadas |
| STT modelo | **large-v3** (o medium si hay problemas de VRAM concurrente) | Calidad alta en español |
| TTS / clonación de voz | **F5-TTS** | Calidad superior a XTTS, clona con pocos segundos de audio |
| Captura de audio | `arecord` (ALSA) o `parecord` (PipeWire) | Nativo, sin dependencias |
| Atajo global | **Hyprland bind** | Nativo del compositor, sin daemon extra |
| Feedback visual | `notify-send` / `dunstify` | Notificaciones nativas |
| Reproducción de audio | `paplay` o `mpv` | Estándar en Linux |

## Requisitos funcionales

### Flujo principal
1. Presiono `Alt+Z` → empieza a grabar (notificación visual: "🎤 Grabando...")
2. Presiono `Alt+Z` de nuevo → detiene grabación (notificación: "🧠 Pensando...")
3. El audio se transcribe con whisper.cpp
4. El texto transcrito se manda a Ollama (Qwen2.5-7B)
5. La respuesta del LLM se sintetiza con F5-TTS usando mi voz clonada
6. El audio resultante se reproduce automáticamente
7. Notificación final desaparece, asistente queda listo para nueva petición

### Comportamiento del LLM
- Ollama debe configurarse con `OLLAMA_KEEP_ALIVE=5m` para que el modelo se descargue de VRAM automáticamente tras 5 minutos de inactividad
- Esto libera VRAM cuando uso la GPU para otras cosas (gaming, edición, etc.)
- La primera petición tras descarga aceptará la latencia de carga (~5-10s)

### Manejo de estado
- El asistente debe mantener un **historial de conversación** durante la sesión (para que el LLM tenga contexto entre turnos)
- Opcional pero deseable: comando o atajo separado para "limpiar historial" / nueva conversación
- El historial puede persistirse en disco (archivo JSON en `~/.local/share/asistente/`) para retomar conversaciones

### Modo toggle vs push-to-talk
- Implementar el modo **toggle** (presionar para empezar, presionar para terminar)
- Es más cómodo para respuestas largas y deja las manos libres

## Estructura sugerida del proyecto

```
~/.local/share/asistente-voz/
├── bin/
│   ├── asistente-toggle.sh      # Script que dispara Hyprland con Alt+Z
│   └── asistente-clear.sh       # Limpiar historial / nueva conversación
├── lib/
│   ├── pipeline.py              # Orquestación STT → LLM → TTS
│   ├── stt.py                   # Wrapper de whisper.cpp
│   ├── llm.py                   # Cliente Ollama
│   └── tts.py                   # Wrapper de F5-TTS
├── models/
│   ├── whisper/                 # Modelos GGUF de whisper.cpp
│   └── f5-tts/
│       └── reference-voice.wav  # Sample de mi voz para clonar
├── config.toml                  # Configuración (modelos, paths, prompts)
├── data/
│   ├── conversation.json        # Historial actual
│   └── logs/
└── tmp/
    ├── recording.wav
    └── response.wav
```

## Detalles de implementación importantes

### 1. Script bash de toggle (el "trigger")
- Debe detectar si ya hay una grabación en curso (PID file en `/tmp/`)
- Si NO hay grabación: inicia `arecord`/`parecord` en background, guarda PID, envía notificación
- Si SÍ hay grabación: mata el proceso de grabación, dispara el pipeline Python con el WAV resultante
- Debe ser idempotente y manejar casos borde (PID huérfano, archivo de audio corrupto, etc.)

### 2. Pipeline Python
- **No usar Python para capturar el audio** — eso lo hace bash con arecord/parecord. Python solo procesa el WAV.
- Llamar a whisper.cpp por subprocess (binario `whisper-cli` o `main`)
- Cliente HTTP a Ollama en `http://localhost:11434/api/chat` (usa `keep_alive` por request)
- Llamar a F5-TTS por subprocess o usar su API Python
- Reproducir con `paplay` por subprocess (no bloquea el script si se hace bien)

### 3. Configuración de Ollama
- Servicio user systemd: `~/.config/systemd/user/ollama.service.d/override.conf`
- Variable: `Environment="OLLAMA_KEEP_ALIVE=5m"`
- Verificar que esté habilitado al inicio: `systemctl --user enable ollama`

### 4. whisper.cpp con CUDA
- Compilar desde fuente con `GGML_CUDA=1`
- Dependencias: CUDA toolkit (verificar versión compatible con driver actual)
- Modelo: descargar `ggml-large-v3.bin` (o `ggml-medium.bin` si problemas)
- Idioma: forzar español con flag `-l es` para mejor calidad

### 5. F5-TTS
- Instalar en venv dedicado (`~/.local/share/asistente-voz/venv/`)
- Requiere PyTorch con CUDA
- Sample de referencia: 10-30 segundos de mi voz limpia, mono, 24kHz idealmente
- Considerar latencia: F5-TTS no es streaming, espera respuesta completa del LLM antes de sintetizar

### 6. Atajo en Hyprland
En `~/.config/hypr/hyprland.conf` (o el archivo de binds que use Omarchy):

```
bind = ALT, Z, exec, ~/.local/share/asistente-voz/bin/asistente-toggle.sh
bind = ALT SHIFT, Z, exec, ~/.local/share/asistente-voz/bin/asistente-clear.sh
```

### 7. Prompt del sistema para el LLM
Definir en `config.toml` un system prompt que:
- Indique al modelo que responde por voz (respuestas concisas, sin markdown, sin listas largas)
- Idioma: español
- Tono: conversacional, directo
- Sin disclaimers innecesarios

## Criterios de éxito

- [ ] Presionar Alt+Z inicia grabación con feedback visual en <500ms
- [ ] Latencia total (fin de grabación → inicio de audio de respuesta) < 5 segundos para queries cortas con modelo ya cargado
- [ ] VRAM se libera tras 5 min de inactividad (verificable con `nvidia-smi`)
- [ ] El asistente mantiene contexto durante la sesión
- [ ] Funciona offline 100% (puedo desconectar internet y sigue funcionando)
- [ ] No hay interfaz gráfica residente — solo notificaciones cuando se usa
- [ ] El sistema se recupera limpiamente de errores (ej: micrófono desconectado, Ollama caído)

## Orden de implementación sugerido

1. **Verificar prerequisitos**: nvidia-smi funciona, CUDA toolkit, PipeWire activo, Hyprland actual
2. **Instalar y probar Ollama** con Qwen2.5-7B — confirmar que responde por API
3. **Compilar whisper.cpp con CUDA** y probar transcripción de un WAV de muestra
4. **Setup de F5-TTS** en venv, probar generación con sample de voz
5. **Script bash de captura** standalone — toggle de grabación funcional
6. **Pipeline Python end-to-end** sin el atajo (probar desde CLI con WAV existente)
7. **Integrar con Hyprland bind** y notificaciones
8. **Configurar auto-unload de Ollama** y persistencia de historial
9. **Pulir**: manejo de errores, logs, comando de limpiar conversación

## Lo que NO quiero

- ❌ Interfaz gráfica permanente (sin tray icons, sin ventanas residentes)
- ❌ Dependencias en la nube de cualquier tipo
- ❌ Modelos cargados en VRAM 24/7
- ❌ Wake words ("hey Claude") — explícitamente prefiero push-to-talk
- ❌ Streaming de TTS por ahora (puede ser una v2)
- ❌ Múltiples idiomas — solo español por ahora

## Preguntas abiertas a resolver durante implementación

1. ¿Conviene un servicio systemd-user para el pipeline Python que escuche un socket, o lanzar Python en cada invocación? (cold start vs proceso residente — evaluar trade-off)
2. ¿F5-TTS tiene buena calidad en español con un sample en español, o conviene XTTS v2 como fallback?
3. ¿Cómo manejar interrupciones? (ej: cancelar respuesta en curso si presiono Alt+Z otra vez)
4. ¿Qué hacer si whisper.cpp transcribe silencio o ruido? (umbral mínimo de confianza, longitud, etc.)
