> **Nota:** este documento describe el **servidor de voz** (STT + TTS), un
> servicio Docker que corre en la máquina Windows/WSL2 y que SOMI consume por
> red en `https://chat-somi.underpenguin.com`. **Su código no vive en este
> repo** — aquí solo está el cliente. Para instalar y usar SOMI, ver el
> [README](../README.md).

# TTS Server (Chatterbox Multilingüe)

Servidor de síntesis de voz con clonación zero-shot en español, compatible con
la API de OpenAI (`/v1/audio/speech`).

## Requisitos previos

- Docker Desktop con integración WSL2 y GPU habilitada (Settings > Resources >
  WSL Integration, y Settings > Resources > GPU).
- Driver NVIDIA actualizado en Windows (no instalar drivers dentro del
  contenedor).
- **RTX 5070 (Blackwell) requiere CUDA 12.8+.** Este proyecto usa
  `pytorch/pytorch:2.7.0-cuda12.8-cudnn9-runtime` como base — no bajar de esa
  versión de CUDA/PyTorch.
- Antes de arrancar este servicio, bajar el quant de Qwen en LM Studio a
  Q5/Q4 para dejar VRAM libre (Chatterbox multilingüe necesita ~3.5 GB
  residentes).

## Fase 1 — Verificar que Docker ve la GPU

```bash
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

Debe mostrar la RTX 5070. Si falla, no continuar: revisar la integración WSL2
de Docker Desktop y el driver de NVIDIA.

## Arranque

```bash
cp .env.example .env
# editar .env: definir TTS_API_KEY (si se deja vacío, arranca sin auth con warning)
docker compose up -d --build
docker compose logs -f tts   # confirmar "Modelo cargado. VRAM ocupada: ... MB"
```

El primer arranque descarga los pesos del modelo a un volumen (`hf-cache`) y
puede tardar varios minutos. Arranques posteriores son instantáneos.

## Pruebas de aceptación

```bash
# la GPU se ve desde dentro del contenedor
docker exec tts-server nvidia-smi

# salud (sin auth)
curl http://localhost:8020/health

# subir una voz de referencia
curl -X POST http://localhost:8020/v1/voices \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -F "file=@somi_ref.wav" \
  -F "id=somi" \
  -F "name=So Mi (español)"

# listar voces
curl http://localhost:8020/v1/voices -H "Authorization: Bearer $TTS_API_KEY"

# generar audio
curl -X POST http://localhost:8020/v1/audio/speech \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"Hola, ¿en qué te puedo ayudar?","voice":"somi"}' \
  --output salida.wav

# preview de una voz
curl http://localhost:8020/v1/voices/somi/preview \
  -H "Authorization: Bearer $TTS_API_KEY" --output preview.wav

# sin token debe dar 401
curl -X POST http://localhost:8020/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"prueba","voice":"somi"}'
```

Verificar también:

- Accesible desde otra máquina de la LAN usando la IP del host Windows
  (`http://<ip-windows>:8020/health`), no solo `localhost`.
- `docker compose down && docker compose up -d` conserva `./voices` y no
  vuelve a descargar los pesos del modelo.
- `nvidia-smi` en Windows muestra el total de VRAM por debajo de 12 GB con
  LM Studio corriendo en paralelo.

## Integrar con tu app de tools

Este servidor es la **capa de voz**. El "cerebro" (LLM + tus tools + la
personalidad) vive en **tu app**: las tools se ejecutan donde está su código,
aquí no. El reparto es:

```
tu app (cerebro: LLM + tools + prompt Songbird)
  │
  │  1. audio del usuario  ──>  POST /v1/audio/transcriptions  ──>  texto
  │  2. texto + tus tools + system prompt  ──>  LM Studio (con thinking si lo necesitas)
  │  3. respuesta en texto  ──>  POST /v1/audio/speech  ──>  audio con la voz clonada
```

Paso 1 — transcribir la voz del usuario:

```bash
curl -X POST http://localhost:8020/v1/audio/transcriptions \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -F "file=@pregunta.ogg" \
  -F "language=es"
# {"text":"..."}
```

Paso 3 — convertir la respuesta de tu modelo en audio:

```bash
curl -X POST http://localhost:8020/v1/audio/speech \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"Texto que dirá Songbird","voice":"somi"}' \
  --output respuesta.wav
```

`voice=somi` es la voz clonada ya registrada (ver `POST /v1/voices` arriba para
añadir otras).

**Importante: no mandes markdown a `/v1/audio/speech`.** El sintetizador lee los
asteriscos, almohadillas y guiones de lista literalmente. El servidor limpia los
símbolos más comunes, pero lo correcto es que tu system prompt pida texto
hablado. Usa el de `prompts/songbird.md`, que ya lo cubre.

### Personalidad Songbird

`prompts/songbird.md` contiene el system prompt listo para pegar en tu app. Es
también el valor por defecto de `LLM_SYSTEM_PROMPT` en este servidor, así que
`POST /v1/voice/chat` sirve para probar la personalidad sin escribir cliente.

### Thinking por petición (voz rápida, tools que razonan)

Qwen3.5 es un modelo *thinking*: razonando puede tardar **minutos** por turno, lo
cual mata una conversación por voz. Este servidor manda en cada petición dos
señales para desactivarlo (`chat_template_kwargs.enable_thinking` y el sufijo
`/no_think`), de modo que **la voz responde rápido sin apagar el razonamiento
globalmente**.

**Tu build de LM Studio ignora `chat_template_kwargs`** (bug conocido: se mandó
el flag *y* `/no_think` y el modelo razonó igual, 745 tokens en 94s). Pero el
**contenido del mensaje sí llega** a la plantilla Jinja, así que el toggle se
consigue leyendo el sufijo desde el propio texto.

En LM Studio → modelo `qwen3.5-9b@q4_k_m` → *Prompt Template* (Jinja), añade
esta línea **al principio del todo**:

```jinja
{%- set enable_thinking = '/no_think' not in messages[-1]['content'] %}
```

Si esa línea diera error de plantilla (por mensajes sin texto plano), usa la
variante defensiva:

```jinja
{%- set enable_thinking = not (messages and messages[-1]['content'] is string and '/no_think' in messages[-1]['content']) %}
```

Guarda y **recarga el modelo**. A partir de ahí:

- este servidor manda `/no_think` en cada petición de voz → responde rápido;
- tu app de tools no lo manda → Qwen razona con normalidad.

No pongas `{%- set enable_thinking = false %}`: eso lo apaga **también** para tu
app de tools, que es justo lo que queremos evitar.

Verifícalo mirando `usage.completion_tokens_details.reasoning_tokens` en la
respuesta de LM Studio: debe ser `0` con `/no_think` y `>0` sin él.

**Plan B**, si la plantilla no coopera: apuntar solo la voz a un modelo
no-thinking con `LLM_MODEL=hermes-3-llama-3.2-3b` (medido: ~6s en caliente,
`reasoning_tokens` 0) y dejar Qwen para las tools. El coste es que LM Studio
hace *swap* entre modelos (~20-60s por cambio) salvo que mantengas los dos
cargados, lo que consume más VRAM.

### Bucle de voz completo (opcional)

`POST /v1/voice/chat` hace voz→texto→LLM→voz en una sola llamada, contra el
LM Studio configurado en `.env`. **No usa tus tools** (el LLM se llama directo),
así que sirve como demo y banco de pruebas de la voz y la personalidad:

```bash
curl -X POST http://localhost:8020/v1/voice/chat \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -F "file=@pregunta.wav" \
  -F "voice=somi" \
  --output respuesta.wav -D headers.txt
# headers.txt trae X-Transcript y X-Reply-Text (url-encoded)
```

**`POST /v1/text/chat`** es el mismo flujo pero con **texto en vez de audio**
como entrada (texto → LLM → voz) — para probar la personalidad sin grabar
nada, o para integraciones que ya tienen el texto del usuario:

```bash
curl -X POST http://localhost:8020/v1/text/chat \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"Hola Somi, ¿cómo estás?","voice":"somi"}' \
  --output respuesta.wav -D headers.txt
```

Acepta también `"system_prompt": "..."` para sobrescribir la personalidad solo
en esa llamada (sin tocar `.env` ni reiniciar el contenedor) y `"stream": true`
igual que `/v1/audio/speech`.

La respuesta trae también `X-Timing` con el reparto por etapa
(`stt=2.3;llm=3.3;tts=14.6`), que es lo primero que hay que mirar cuando un
turno tarde de más.

**Configuración validada** (la que da mejor latencia y estabilidad medidas):

| Componente | Modelo | Cuantización | VRAM aprox. |
|---|---|---|---|
| TTS (este servidor) | Chatterbox multilingüe | — | 3.0 GB |
| LLM | `qwen3.5-4b` | Q8_0 | ~4.3 GB |
| Embeddings | `text-embedding-bge-m3@q8_0` | Q8_0 | ~1.1 GB |

Con Qwen3.5 hay que aplicar el arreglo de plantilla de la sección anterior **al
modelo concreto que uses**: la plantilla se edita por modelo, así que editar la
del 9B no afecta al 4B.

**Latencias medidas** (8 turnos seguidos, frase de ~180 caracteres): total
**12-17s, media ~14s**; STT ~2.3s estable, **LLM ~0.5s**, y **TTS ~10s, que es
el 70% del turno**. El TTS es el techo: no baja tocando LM Studio ni la VRAM.
La mitigación es el **streaming de audio** (sección siguiente): no reduce el
tiempo total, pero el oyente empieza a escuchar mucho antes.

Lecciones de la puesta a punto, por si hay que re-ajustar:

- La VRAM va **muy justa** (12 GB para los tres modelos). Los síntomas de estar
  al borde son picos del TTS (de 10s a 20-30s) y, en el extremo, `nvidia-smi`
  devolviendo valores absurdos (`17592181862080 MiB`, desbordamiento del driver
  WSL2) o un crash de la GPU.
- Lo que **sí** libera VRAM: bajar la cuantización de los modelos. Bajar el
  embedding de FP16 a Q8 quitó los picos de 24s.
- Lo que **no** libera VRAM apenas: `Parallel` y el tamaño de contexto en LM
  Studio (asigna el KV cache bajo demanda, no por adelantado). Medido: pasar de
  `Parallel 4` a `1` liberó 76 MiB, no los ~1.5 GB que cabría esperar.
- No todo modelo sirve: `meta-llama-3.1-8b-instruct` con la plantilla por
  defecto de LM Studio devuelve JSON de function-call (`{"name": ...}`) en vez
  de prosa, y el TTS lo lee literalmente.

### Streaming de audio

`POST /v1/audio/speech` y `POST /v1/voice/chat` aceptan `"stream": true` (o
`stream=true` como campo de formulario en `/v1/voice/chat`). En vez de esperar
a que **todo** el audio esté listo, el servidor lo envía **por frases**, a
medida que las va generando: el cliente puede empezar a reproducir mucho antes
de que termine de "hablar".

```bash
# streaming + reproducción en vivo (requiere ffplay, de ffmpeg)
curl -sN -X POST http://localhost:8020/v1/audio/speech \
  -H "Authorization: Bearer $TTS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":"Texto largo que Songbird va a decir.","voice":"somi","stream":true}' \
  | ffplay -nodisp -autoexit -loglevel quiet -
```

**Cómo funciona:** solo Chatterbox `generate()` existe (no hay streaming nativo
a nivel de tokens en la versión multilingüe — los forks que sí lo traen,
p.ej. `chatterbox-streaming`, son **solo inglés**). El streaming aquí es
**por frases**: el texto se trocea con `TTS_STREAM_CHUNK_CHARS` (default `50`),
cada trozo se sintetiza por separado y se envía en cuanto está listo, como WAV
sin cabecera de tamaño fijo (`Content-Length` indeterminado) seguido de PCM
16-bit crudo — así no hace falta re-codificar por trozo. Por eso el streaming
**solo soporta `response_format=wav`**; con `mp3` da `400`.

**Optimización clave:** generar un trozo re-procesaba antes el wav de
referencia de la voz completo (~13s la primera vez) en **cada** llamada. Ahora
esos *conditionals* se cachean por voz (invalidados si se re-sube el wav), así
que ese coste se paga una sola vez y no en cada frase — esto acelera **todas**
las peticiones, no solo las de streaming.

**Latencias medidas** (misma frase de ~180 caracteres, GPU compartida con LM
Studio):

| | primer audio | stream completo |
|---|---|---|
| Sin streaming (referencia) | — | ~13-14s |
| Streaming, `chunk_chars=120` | ~6.6s | ~13s |
| **Streaming, `chunk_chars=50` (default)** | **~3.7-7s** | ~14-16s |

Es un **tradeoff**, no una mejora gratis: trozos más pequeños bajan el tiempo
hasta el primer sonido, pero suman **más pausas** entre frases (cada trozo se
sintetiza de forma independiente, sin continuidad prosódica entre ellos) y un
total ligeramente mayor, porque el coste fijo por llamada (~2s en esta GPU) se
paga más veces. El default (`50`) prioriza reaccionar rápido — es lo que
importa en una conversación — a costa de esas pausas y de ~2s más en el total.
Si prefieres frases más fluidas a cambio de tardar más en arrancar, sube
`TTS_STREAM_CHUNK_CHARS` en `.env` (p.ej. `120` o el `TTS_MAX_CHARS` completo
para desactivar el streaming de facto).

**Concurrencia:** el semáforo de GPU se mantiene tomado durante **todo** el
stream de una petición, no por trozo — dos streams simultáneos se encolan
igual que en modo no-streaming, nunca se entrelazan (verificado: transcripción
de cada uno por separado, sin mezcla).

### Página de pruebas

`GET /` sirve una página HTML de un solo archivo (`app/static/test.html`), sin
dependencias externas, para probar todo lo anterior sin `curl`/`ffplay`:

- **Chat con Songbird**: escribe un mensaje, se manda a `/v1/text/chat` con
  `stream:true` y la respuesta se oye en cuanto empieza a llegar. Trae un campo
  plegable para sobrescribir el system prompt sin tocar `.env`.
- **Decir texto**: el texto que escribas se reproduce tal cual con la voz
  clonada (`/v1/audio/speech`), sin pasar por el LLM.
- Cabecera con el **token** (se guarda en `localStorage` del navegador, nunca
  se manda a ningún sitio salvo a este mismo servidor) y el **selector de voz**
  poblado desde `GET /v1/voices`.
- Ambas secciones muestran el **tiempo hasta el primer audio** y el tiempo
  total del stream — el número que hace tangible la mejora del streaming.

**Cómo reproduce el streaming en el navegador:** no usa `<audio>` (la petición
es POST, y un `Blob` esperaría el cuerpo completo, anulando el streaming). Usa
`fetch()` + `ReadableStream` + Web Audio API: salta los 44 bytes de la cabecera
WAV del primer chunk, arrastra el byte suelto entre lecturas cuando el tamaño
del chunk es impar (las muestras son PCM de 16 bits — un solo byte de desfase
convierte el resto del audio en ruido), y programa cada trozo con
`startAt = max(ctx.currentTime, nextStartTime)` para que las frases suenen
encadenadas sin solaparse ni cortarse.

Se puede **apagar** con `TTS_ENABLE_TEST_PAGE=false` en `.env` (por defecto
está activa). No lleva secretos —el token lo escribe cada usuario en su
navegador—, pero si este servidor está expuesto a internet por NPM y no se
quiere una UI pública, apágala.

### Si aparece `CUDA error: unknown error`

Expulsar o recargar modelos en LM Studio mientras el contenedor está vivo puede
dejar su contexto CUDA corrupto: las peticiones fallan con **HTTP 500** y
`RuntimeError: CUDA error: unknown error` en `ref_wav.to(device)`, en unos pocos
segundos (no es un timeout). Se arregla reiniciando el contenedor, que crea un
contexto nuevo:

```bash
docker compose restart tts
```

Como el fallo es rápido, es fácil confundirlo con "va muy rápido"; comprueba
siempre el código HTTP y el tamaño del cuerpo, no solo el tiempo.

## Publicación con Nginx Proxy Manager

Proxy host apuntando a `<ip-windows>:8020`. En Advanced:

```nginx
proxy_buffering off;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
client_max_body_size 50M;
```

## Notas de configuración (`.env`)

| Variable            | Default | Descripción                                      |
|---------------------|---------|---------------------------------------------------|
| `TTS_API_KEY`       | (vacío) | Token bearer. Vacío = sin auth (con warning en log)|
| `TTS_PORT`          | 8020    | Puerto expuesto                                    |
| `TTS_MAX_CHARS`     | 2000    | Umbral para partir texto largo en fragmentos       |
| `TTS_DEFAULT_VOICE` | somi    | Voz usada si no se especifica `voice`              |
| `TTS_LANGUAGE`      | es      | Código de idioma pasado a Chatterbox               |
| `TTS_REQUEST_TIMEOUT` | 120   | Timeout en segundos por generación                 |
| `TTS_STREAM_CHUNK_CHARS` | 50 | Tamaño de trozo para `stream:true`. Más bajo = arranca antes, más pausas |
| `TTS_ENABLE_TEST_PAGE` | true | Sirve la página de pruebas en `GET /`. `false` la apaga (404) |
| `STT_MODEL_SIZE`    | small   | Modelo faster-whisper (`tiny`/`base`/`small`/`medium`) |
| `STT_DEVICE`        | cpu     | Dónde corre el STT. **Dejar en `cpu`**: la VRAM está al límite |
| `STT_COMPUTE_TYPE`  | int8    | Cuantización del STT en CPU                        |
| `STT_LANGUAGE`      | es      | Idioma por defecto al transcribir                  |
| `LLM_BASE_URL`      | `http://host.docker.internal:1234/v1` | LM Studio visto desde el contenedor |
| `LLM_MODEL`         | (ver `.env`) | Model id en LM Studio, p.ej. `qwen3.5-9b@q4_k_m` |
| `LLM_API_KEY`       | (vacío) | Token de LM Studio, si lo tiene configurado        |
| `LLM_SYSTEM_PROMPT` | Songbird | Personalidad del bucle de voz (ver `prompts/songbird.md`) |
| `LLM_TIMEOUT`       | 300     | Timeout en segundos de la llamada al LLM           |
