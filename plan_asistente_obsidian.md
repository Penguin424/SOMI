# Plan de Implementación: Asistente de Voz Local con Tools para Obsidian

## Contexto del Proyecto

Asistente de voz **100% local** corriendo en **CachyOS + Omarchy (Hyprland)**. Stack actual ya funcional:

- **STT**: Whisper (script de terminal)
- **LLM**: Llama 3.1 8B vía Ollama
- **TTS**: XTTS (Coqui) con voz clonada
- **Trigger**: hotkey `Alt+Z` activa/desactiva micrófono
- **Flujo actual**: hotkey → graba audio → Whisper transcribe → Python pasa texto a Ollama → respuesta → XTTS → reproducción

## Objetivo de Esta Fase

Agregar 3 capacidades nuevas:

1. **Overlay visual estilo Cyberpunk 2077** durante reproducción del TTS
2. **Tool use** para que el asistente cree/modifique notas en bóveda de Obsidian
3. **RAG local** alimentado de la bóveda de Obsidian (fase posterior)

Este documento cubre principalmente las tools (núcleo del valor diario) y la integración. El overlay y el RAG son fases separadas que se construyen sobre esta base.

## Principio Fundamental: Interacción 100% por Voz

**Todo el sistema se opera por voz.** El usuario nunca debe necesitar teclado/mouse para ejecutar una tool. El flujo es siempre:

1. Usuario presiona `Alt+Z` (única interacción física)
2. Habla naturalmente — sin sintaxis especial ni comandos rígidos
3. Whisper transcribe
4. El modelo decide solo si es conversación o comando con tool
5. Si es tool: ejecuta la modificación en Obsidian
6. El modelo genera **confirmación verbal corta** (1-2 oraciones máx)
7. XTTS reproduce la confirmación en voz alta

**Implicaciones de diseño**:

- Los parámetros de las tools deben poder **extraerse de habla natural y desordenada**. El usuario NO va a dictar "tarea: comprar café, prioridad: alta". Va a decir "recuérdame comprar café, es urgente".
- La confirmación verbal debe ser **breve y natural**, no leer estructuras de datos. Ejemplo correcto: "Listo, agregué comprar café a tus pendientes con prioridad alta". Ejemplo incorrecto: "Tool agregar_pendiente ejecutada con parámetros tarea='comprar café' prioridad='alta'".
- Si falta un parámetro **crítico**, el asistente debe **preguntar por voz** y esperar la siguiente activación de `Alt+Z`. Ejemplo: usuario dice "califica la película" sin título — asistente responde "¿Qué película calificaste?" y espera.
- Si falta un parámetro **opcional**, simplemente omitirlo. No interrogar al usuario por cada campo.
- El modelo debe ser tolerante a frases ambiguas y resolver con valores por defecto sensatos (fecha = hoy, prioridad = media, etc.).
- Whisper puede equivocarse con números, nombres propios y términos técnicos. El system prompt debe instruir al modelo a **inferir y normalizar** (ej. "ochenta kilos" o "80 kg" o "ochenta" → 80).

---

## Arquitectura Objetivo

```
[Alt+Z] → Whisper → texto → router de intención
                              ├─ Conversación normal → Ollama → respuesta texto
                              └─ Comando/dictado → Ollama + tools → ejecuta tool → confirmación
                                                                      ↓
                                                              modifica .md en bóveda
                              ↓
                       respuesta texto → XTTS → audio + overlay Cyberpunk
```

---

## Estructura de la Bóveda de Obsidian

Asumir esta estructura (parametrizable vía config):

```
Vault/
├── Diario/
│   └── YYYY-MM-DD.md
├── Fitness/
│   └── Entrenamientos/
│       └── YYYY-MM-DD.md
├── Media/
│   ├── Series.md
│   └── Peliculas.md
├── Ingles/
│   ├── Vocabulario.md
│   ├── Gramatica.md
│   └── Notas/
├── Snippets/
│   ├── Linux.md
│   ├── Proton.md
│   ├── Git.md
│   ├── Hyprland.md
│   └── Otros.md
├── Pendientes.md
└── Inbox.md
```

**Ruta de la bóveda**: leer de un archivo de configuración (`config.yaml` o variables de entorno). NO hardcodear.

---

## Convenciones Técnicas

### Frontmatter obligatorio en cada entrada/archivo nuevo

```yaml
---
tipo: entrenamiento | media | ingles | diario | snippet | nota | pendiente
fecha: YYYY-MM-DD
hora: HH:MM
tags: []
---
```

Esto habilita queries con Dataview en Obsidian y metadata para el RAG posterior.

### Operaciones permitidas

- **Solo append/create** en esta fase. No editar ni borrar contenido existente.
- Si un archivo del día ya existe (ej. diario), anexar con separador `## HH:MM`.
- Si una tabla existe (Series.md, Peliculas.md), insertar fila nueva sin reescribir el resto.

### Logging

Cada tool call debe loguearse en `~/.local/share/asistente/tools.log` con formato:

```
[2026-05-19 14:32:11] tool=entrada_diario params={...} status=ok result_path=...
```

---

## Catálogo de Tools a Implementar

Implementar en este orden (cada fase debe quedar funcional antes de pasar a la siguiente):

### Fase 1: Tools básicas (validación del patrón)

#### `entrada_diario`
**Propósito**: Anexar una entrada al diario del día.
**Parámetros**:
- `contenido` (string, requerido)
- `tag` (string, opcional: `reflexion | evento | idea | animo`)

**Comportamiento**:
- Si no existe `Diario/YYYY-MM-DD.md`, créalo con frontmatter `tipo: diario`.
- Anexa con timestamp `## HH:MM` y el contenido debajo.
- Si hay tag, agrégalo como `#tag` al final de la entrada.

#### `agregar_pendiente`
**Propósito**: Añadir tarea a `Pendientes.md`.
**Parámetros**:
- `tarea` (string, requerido)
- `prioridad` (enum opcional: `alta | media | baja`)
- `fecha_limite` (string opcional, formato YYYY-MM-DD)
- `contexto` (string opcional: `trabajo | casa | compras | etc.`)

**Comportamiento**:
- Anexa como checkbox: `- [ ] tarea` con prioridad como emoji o tag (`🔴 #alta`), fecha como `📅 2026-05-20`, contexto como `#contexto/trabajo`.
- Si el archivo no existe, créalo con frontmatter.

---

### Fase 2: Tools de texto libre

#### `guardar_snippet`
**Propósito**: Guardar comandos/configs técnicas.
**Parámetros**:
- `categoria` (enum: `linux | proton | git | hyprland | otro`)
- `titulo` (string, requerido)
- `contenido` (string, requerido — se guarda como bloque de código)
- `tags` (array de strings, opcional)
- `descripcion` (string, opcional)

**Comportamiento**:
- Anexa al archivo `Snippets/{Categoria}.md` con formato:
  ```
  ## {titulo}
  {descripcion}
  ```bash
  {contenido}
  ```
  Tags: #tag1 #tag2
  ```

#### `crear_nota`
**Propósito**: Escape hatch para notas que no encajan en otras tools.
**Parámetros**:
- `titulo` (string, requerido)
- `contenido` (string, requerido)
- `carpeta` (string, opcional, default `Inbox/`)
- `tags` (array, opcional)

**Comportamiento**:
- Crea archivo nuevo `{carpeta}/{titulo-slug}.md` con frontmatter completo.
- Si el archivo ya existe, anexar `_{timestamp}` al nombre.

---

### Fase 3: Tools estructuradas

#### `log_entrenamiento`
**Propósito**: Registrar sesión de fuerza.
**Parámetros**:
- `ejercicios` (array, requerido):
  ```json
  [
    {
      "nombre": "press banca",
      "sets": [
        {"peso": 80, "reps": 8, "unidad": "kg"},
        {"peso": 80, "reps": 8, "unidad": "kg"}
      ]
    }
  ]
  ```
- `notas` (string, opcional)
- `duracion_min` (int, opcional)

**Comportamiento**:
- Crea `Fitness/Entrenamientos/YYYY-MM-DD.md` con frontmatter `tipo: entrenamiento`, lista de ejercicios en frontmatter (para queries Dataview).
- En el cuerpo, una tabla por ejercicio:
  ```
  ## Press banca
  | Set | Peso | Reps |
  |-----|------|------|
  | 1   | 80kg | 8    |
  ```

---

### Fase 4: Tools temáticas

#### `calificar_media`
**Propósito**: Anexar calificación a tabla de series o películas.
**Parámetros**:
- `tipo` (enum: `serie | pelicula`)
- `titulo` (string, requerido)
- `temporada` (int, opcional, solo si tipo=serie)
- `episodio` (int, opcional, solo si tipo=serie)
- `calificacion` (float, requerido, escala 0-10)
- `comentario` (string, opcional)
- `fecha_visto` (string, opcional, default = hoy)

**Comportamiento**:
- Si `tipo=serie`, anexar fila a `Media/Series.md`.
- Si `tipo=pelicula`, anexar fila a `Media/Peliculas.md`.
- Si el archivo no existe, crear con encabezado de tabla apropiado.
- Encabezado series: `| Título | Temporada | Episodio | Calificación | Fecha | Comentario |`
- Encabezado películas: `| Título | Calificación | Fecha | Comentario |`

#### `nota_ingles`
**Propósito**: Registrar aprendizaje de inglés.
**Parámetros**:
- `categoria` (enum: `vocabulario | gramatica | expresion | nota_general`)
- `contenido` (string, requerido)
- `ejemplo` (string, opcional)
- `traduccion` (string, opcional)

**Comportamiento**:
- Para `vocabulario`: anexar a `Ingles/Vocabulario.md` en formato `palabra :: traducción :: ejemplo` (compatible con Spaced Repetition).
- Para `gramatica`: anexar sección a `Ingles/Gramatica.md` con `## Tema` + contenido + ejemplo.
- Para `expresion`: anexar a `Ingles/Vocabulario.md` en sección "Expresiones".
- Para `nota_general`: crear archivo en `Ingles/Notas/` con timestamp.

---

### Fase 5: Lectura (mini-RAG previo al RAG completo)

#### `buscar_en_vault`
**Propósito**: Buscar info en la bóveda sin necesidad del RAG vectorial todavía.
**Parámetros**:
- `query` (string, requerido)
- `tipo` (string opcional: filtra por frontmatter `tipo`)
- `max_resultados` (int, opcional, default 5)

**Comportamiento**:
- Usar `ripgrep` (rg) o `grep -r` sobre la bóveda.
- Si se pasa `tipo`, filtrar primero archivos con ese frontmatter.
- Devolver lista de matches con: ruta del archivo, líneas relevantes con contexto (±2 líneas), score simple.
- El modelo después sintetiza la respuesta usando estos resultados.

---

### Fase 6: Escalado a modelos externos vía CLI

#### `consultar_experto`
**Propósito**: Delegar preguntas complejas a otro LLM más capaz cuando Llama 3.1 8B no es suficiente, o cuando el usuario lo pide explícitamente. Esta fase asume que el usuario tiene instalados CLIs como `gemini` (Gemini CLI de Google) y `claude` (Claude Code CLI de Anthropic). **No usa APIs con keys, solo CLIs ya autenticados localmente.**

**Parámetros**:
- `modelo` (enum requerido: `gemini | claude | auto`)
- `pregunta` (string, requerido — la pregunta reformulada y completa)
- `razon` (string, opcional — por qué se escaló, útil para logs)

**Disparadores (cuándo el modelo llama esta tool)**:

1. **Explícito por usuario**: el usuario menciona el nombre del modelo.
   - "Pregúntale a Gemini..."
   - "Que conteste Claude..."
   - "Usa el CLI de Gemini para..."
   - "Esta pregunta hazla más retadora con Claude..."
2. **Auto-escalado**: el modelo local detecta que no puede responder bien.
   - Preguntas sobre eventos posteriores a su corte de entrenamiento.
   - Razonamiento muy complejo o multi-paso.
   - Código avanzado o debugging profundo.
   - Cuando dice "no estoy seguro" más de una vez en el mismo turno.
3. **Segunda opinión solicitada**: "verifica esto con Claude", "qué dice Gemini de esto".

**Comportamiento del wrapper**:

```python
import subprocess

def consultar_experto(modelo: str, pregunta: str, razon: str = ""):
    comandos = {
        "gemini": ["gemini", "-p", pregunta],
        "claude": ["claude", "-p", pregunta],
    }
    
    if modelo == "auto":
        modelo = "gemini"  # default configurable
    
    if modelo not in comandos:
        return {"status": "error", "message": f"Modelo {modelo} no disponible"}
    
    try:
        result = subprocess.run(
            comandos[modelo],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr.strip()[:200]}
        
        respuesta_cruda = result.stdout.strip()
        return {
            "status": "ok",
            "modelo_usado": modelo,
            "respuesta": respuesta_cruda
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": f"{modelo} tardó más de 60 segundos"}
    except FileNotFoundError:
        return {"status": "error", "message": f"CLI de {modelo} no instalado"}
```

**Verificación de comandos exactos**: el implementador debe verificar las flags reales de cada CLI antes de hardcodear. Algunos CLIs requieren modo no-interactivo explícito (ej. `--print` o `-p` para output directo sin REPL). Las opciones actuales conocidas:
- Claude Code CLI: `claude -p "pregunta"` para modo print/headless.
- Gemini CLI: `gemini -p "pregunta"` o equivalente.

Si las flags cambian, ajustar el diccionario `comandos`.

**Aviso de espera al usuario**:

Los CLIs pueden tardar 5-30 segundos. El modelo debe **avisar antes de esperar** para que el usuario no piense que el asistente se trabó:

> Usuario: "Pregúntale a Gemini cómo optimizar este query SQL..."
> Asistente (inmediato): "Un momento, le pregunto a Gemini."
> *(silencio mientras corre el CLI)*
> Asistente (después): "Gemini sugiere usar un índice compuesto en las columnas..."

**Resumen obligatorio antes del TTS**:

Las respuestas de Gemini/Claude pueden ser largas (cientos de palabras). El modelo local debe **siempre resumir** la respuesta del experto antes de pasarla al TTS, salvo que el usuario pida explícitamente "léeme la respuesta completa". Regla:

- Respuesta < 50 palabras: leer textual.
- Respuesta 50-200 palabras: leer la idea central y ofrecer detalle ("¿Quieres que te explique más?").
- Respuesta > 200 palabras: resumen en 2-3 oraciones + ofrecer guardar la respuesta completa en una nota de Obsidian.

**Integración con `crear_nota`**:

Para respuestas largas que valen la pena conservar, el modelo puede encadenar tools: ejecuta `consultar_experto`, luego ofrece "¿Quiero guardar la respuesta completa en tus notas?". Si el usuario confirma, llama `crear_nota` con el contenido y carpeta `Inbox/Respuestas/`.

**Configuración relacionada en `config.yaml`**:

```yaml
expertos:
  habilitado: true
  modelo_default: gemini       # para auto-escalado
  timeout_segundos: 60
  clis_disponibles:
    gemini:
      comando: gemini
      flag_prompt: -p
    claude:
      comando: claude
      flag_prompt: -p
  resumir_respuestas: true
  max_palabras_lectura_textual: 50
```

**Privacidad**:

Los CLIs mandan tu pregunta a los servidores de Google/Anthropic. Importante:

- NO encadenar automáticamente `buscar_en_vault` → `consultar_experto`. Si el modelo va a mandar contenido de tu bóveda a un experto externo, debe **pedir confirmación verbal** primero: "Esto va a mandar parte de tus notas a Gemini, ¿confirmas?".
- Logear cada llamada externa en `tools.log` con la pregunta enviada (para auditoría posterior).
- Considerar un comando de voz para apagar/encender expertos: "modo privado" → desactiva tools externas en esa sesión.

**Ejemplo de interacción por voz**:

> **Usuario**: "Pregúntale a Claude cómo se diferencia el algoritmo de Raft del de Paxos."
>
> **Asistente** (inmediato): "Un momento, le pregunto a Claude."
>
> *(15 segundos)*
>
> **Asistente**: "Claude dice que Raft fue diseñado para ser más fácil de entender que Paxos, con un líder único y términos numerados, mientras Paxos es más general pero más complejo de implementar. ¿Quieres que guarde la explicación completa en tus notas?"
>
> **Usuario** *(presiona Alt+Z)*: "Sí, guárdala."
>
> **Asistente**: "Guardada en Inbox como 'Raft vs Paxos'."

---

## Implementación Técnica

### Estructura de archivos del proyecto

```
asistente/
├── config.yaml                    # rutas, modelo, voz, etc.
├── main.py                        # punto de entrada actual (modificar)
├── stt.py                         # whisper (existente)
├── tts.py                         # xtts (existente)
├── llm.py                         # ollama wrapper
├── tools/
│   ├── __init__.py
│   ├── registry.py                # registro central de tools para Ollama
│   ├── obsidian_utils.py          # helpers: leer/escribir frontmatter, append seguro, slugify
│   ├── entrada_diario.py
│   ├── agregar_pendiente.py
│   ├── guardar_snippet.py
│   ├── crear_nota.py
│   ├── log_entrenamiento.py
│   ├── calificar_media.py
│   ├── nota_ingles.py
│   ├── buscar_en_vault.py
│   └── consultar_experto.py
├── overlay/                       # fase 2 (Cyberpunk overlay)
│   └── ...
├── rag/                           # fase 3
│   └── ...
└── logs/
    └── tools.log
```

### Patrón de cada tool

Cada tool debe:

1. Definir su JSON Schema compatible con Ollama tool calling.
2. Implementar función Python que recibe los parámetros y devuelve `{"status": "ok"|"error", "message": "...", "path": "..."}`.
3. Validar parámetros antes de tocar disco.
4. Loguear la llamada.
5. Devolver mensaje corto que el modelo usará para confirmar verbalmente al usuario.

### Integración con Ollama

Llama 3.1 8B soporta tool calling nativo. Ejemplo de llamada:

```python
import ollama

response = ollama.chat(
    model='llama3.1:8b',
    messages=[
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_text}
    ],
    tools=[tool.schema for tool in registered_tools]
)

if response['message'].get('tool_calls'):
    for call in response['message']['tool_calls']:
        result = execute_tool(call['function']['name'], call['function']['arguments'])
        # Pasar resultado de vuelta al modelo para que genere confirmación verbal
        ...
```

### System prompt sugerido

Debe incluir:

- Identidad/personalidad del asistente.
- Lista de tools disponibles con cuándo usarlas.
- **Regla crítica**: tras ejecutar una tool, generar respuesta verbal corta confirmando qué se hizo (1-2 oraciones máx, para que el TTS no se eternice).
- Ejemplos few-shot de inputs → tool calls correctos. Especialmente importantes:
  - "Registra que hice press banca, 4 series de 8 con 80 kilos" → `log_entrenamiento`
  - "Anota que vi el capítulo 3 de Severance y le doy 9" → `calificar_media`
  - "Guarda este comando para Steam: PROTON_HACKS=1..." → `guardar_snippet`
  - "Me siento cansado hoy, dormí mal" → `entrada_diario` con tag `animo`
  - "Recuérdame comprar café" → `agregar_pendiente`

### Router de intención (opcional pero recomendado)

Antes de mandar a Ollama con tools, un clasificador rápido decide: ¿es conversación o es comando para tool?

Opción A: usar Llama mismo en un primer pass con prompt simple ("clasifica como CONVERSACION o COMANDO").
Opción B: heurística con keywords ("registra", "anota", "guarda", "recuérdame", "calificar") → fuerza modo tool.

Recomendación: **Opción B** al principio por velocidad, luego upgrade a A si hay muchos falsos negativos.

---

## Configuración (`config.yaml`)

```yaml
vault:
  path: /home/usuario/Obsidian/MiVault
  
ollama:
  model: llama3.1:8b
  host: http://localhost:11434
  
whisper:
  model: small  # o el que uses
  language: es
  
tts:
  voice_sample: /ruta/al/sample.wav
  language: es

paths:
  log_file: ~/.local/share/asistente/tools.log
  
behavior:
  modo_tool_keywords: [registra, anota, guarda, apunta, recuérdame, califica, log]
  confirmacion_verbal_max_palabras: 20
```

---

## Testing

Cada tool debe tener un test que:

1. Use una bóveda de prueba en `/tmp/test_vault/`.
2. Ejecute la tool con parámetros válidos y verifique el archivo resultante.
3. Ejecute con parámetros inválidos y verifique el manejo de error.
4. Verifique que el frontmatter esté correcto.

Suite de smoke test al final que ejecute cada tool una vez y verifique que no rompe nada.

---

## Ejemplos de Interacción por Voz

Estos ejemplos sirven como **few-shot prompts** para el system prompt y como guía de lo que debe funcionar end-to-end. Todos los ejemplos asumen que el usuario presionó `Alt+Z`, habló, y el sistema responde por voz.

### Ejemplo 1: Pendiente simple

> **Usuario**: "Recuérdame comprar café mañana."
>
> **Tool detectada**: `agregar_pendiente`
> **Parámetros inferidos**: `tarea="comprar café"`, `fecha_limite="2026-05-20"`
>
> **Respuesta verbal**: "Hecho, anoté comprar café para mañana."

### Ejemplo 2: Entrenamiento con extracción compleja

> **Usuario**: "Apunta mi entreno de hoy. Hice press banca, cuatro series de ocho con ochenta kilos. Luego sentadilla, tres por diez con cien. Y dominadas, tres series al fallo."
>
> **Tool detectada**: `log_entrenamiento`
> **Parámetros inferidos**:
> ```json
> {
>   "ejercicios": [
>     {"nombre": "press banca", "sets": [{"peso": 80, "reps": 8, "unidad": "kg"}] × 4},
>     {"nombre": "sentadilla", "sets": [{"peso": 100, "reps": 10, "unidad": "kg"}] × 3},
>     {"nombre": "dominadas", "sets": [{"peso": null, "reps": "fallo"}] × 3}
>   ]
> }
> ```
>
> **Respuesta verbal**: "Registré tu entrenamiento: press banca, sentadilla y dominadas. Buen trabajo."

### Ejemplo 3: Diario

> **Usuario**: "Anota en mi diario que hoy me sentí muy productivo, terminé el proyecto del asistente y me quedé despierto hasta tarde."
>
> **Tool detectada**: `entrada_diario`
> **Parámetros inferidos**: `contenido="Hoy me sentí muy productivo, terminé el proyecto del asistente y me quedé despierto hasta tarde."`, `tag="reflexion"`
>
> **Respuesta verbal**: "Lo agregué a tu diario de hoy."

### Ejemplo 4: Calificar serie

> **Usuario**: "Califica el capítulo cinco de la temporada dos de Severance, le doy nueve."
>
> **Tool detectada**: `calificar_media`
> **Parámetros inferidos**: `tipo="serie"`, `titulo="Severance"`, `temporada=2`, `episodio=5`, `calificacion=9.0`
>
> **Respuesta verbal**: "Listo, anoté Severance temporada 2 episodio 5 con un 9."

### Ejemplo 5: Snippet técnico

> **Usuario**: "Guarda este comando de Proton: gamemoderun mango hud porcentaje uno, espacio, comando. Es para correr juegos con MangoHud y GameMode."
>
> **Tool detectada**: `guardar_snippet`
> **Parámetros inferidos**:
> ```json
> {
>   "categoria": "proton",
>   "titulo": "Lanzar juego con MangoHud y GameMode",
>   "contenido": "gamemoderun MANGOHUD=1 %command%",
>   "descripcion": "Para correr juegos con MangoHud y GameMode"
> }
> ```
>
> **Respuesta verbal**: "Guardé el snippet en Proton."
>
> **Nota**: este ejemplo muestra el problema clásico con Whisper y comandos técnicos. El modelo debe **inferir la intención técnica** y normalizar "mango hud porcentaje uno" a `MANGOHUD=1`. Si la confianza es baja, el modelo puede leer el contenido en voz alta para confirmar: "Guardé: gamemoderun MANGOHUD igual uno comando. ¿Es correcto?".

### Ejemplo 6: Inglés - vocabulario

> **Usuario**: "Anota en inglés la palabra serendipity, significa encontrar algo bueno por casualidad."
>
> **Tool detectada**: `nota_ingles`
> **Parámetros inferidos**: `categoria="vocabulario"`, `contenido="serendipity"`, `traduccion="encontrar algo bueno por casualidad"`
>
> **Respuesta verbal**: "Agregué serendipity a tu vocabulario."

### Ejemplo 7: Parámetro crítico faltante

> **Usuario**: "Califica la película que vi anoche, le doy ocho."
>
> **Tool detectada**: `calificar_media` — pero falta el título.
>
> **Respuesta verbal**: "¿Qué película viste?"
>
> *(El usuario presiona Alt+Z de nuevo)*
>
> **Usuario**: "Dune dos."
>
> **Respuesta verbal**: "Listo, anoté Dune Parte 2 con un 8."
>
> **Nota implementación**: esto requiere **estado conversacional** — el modelo debe recordar que la tool `calificar_media` está en construcción y que falta el título. Implementar con un buffer de contexto de la última N rondas (3-5 turnos basta).

### Ejemplo 8: Conversación normal (NO debe disparar tool)

> **Usuario**: "Oye, ¿qué opinas del nuevo CPU de AMD?"
>
> **Tool detectada**: ninguna.
>
> **Respuesta verbal**: respuesta conversacional normal del modelo, sin modificar ningún archivo.
>
> **Nota**: este caso es importante. El modelo NO debe inventar una tool solo porque suena a "registrar algo". Conversación es conversación.

### Ejemplo 9: Búsqueda en bóveda

> **Usuario**: "¿Cuánto levanté en press banca la semana pasada?"
>
> **Tool detectada**: `buscar_en_vault` con `query="press banca"`, `tipo="entrenamiento"`.
>
> **Respuesta verbal**: "La semana pasada hiciste press banca con 80 kilos por ocho repeticiones, cuatro series."

### Ejemplo 10: Comando ambiguo

> **Usuario**: "Anota que comí pizza."
>
> **Tool detectada**: ambigua — podría ser `entrada_diario` o `crear_nota`.
>
> **Comportamiento esperado**: usar `entrada_diario` por defecto (lo más probable) y mencionar dónde se guardó:
>
> **Respuesta verbal**: "Lo anoté en tu diario de hoy."

### Ejemplo 11: Escalado explícito a Gemini

> **Usuario**: "Pregúntale a Gemini cuál es la diferencia entre TCP y QUIC."
>
> **Tool detectada**: `consultar_experto` con `modelo="gemini"`.
>
> **Respuesta inmediata**: "Un momento, le pregunto a Gemini."
>
> *(espera mientras corre el CLI)*
>
> **Respuesta verbal final**: "Gemini explica que TCP es orientado a conexión con handshake de tres vías, mientras QUIC corre sobre UDP, integra TLS, y reduce la latencia inicial. ¿Quieres más detalle?"

### Ejemplo 12: Auto-escalado por el modelo

> **Usuario**: "¿Cuándo salió la última versión de Python?"
>
> **Comportamiento esperado**: Llama 3.1 8B detecta que es información posterior a su corte de entrenamiento y llama `consultar_experto` con `modelo="auto"` y `razon="información reciente"`.
>
> **Respuesta inmediata**: "No estoy seguro de la fecha exacta, déjame preguntarle a Gemini."
>
> **Respuesta verbal final**: "Gemini dice que la última versión es Python [X.Y]."

### Ejemplo 13: Reto/segunda opinión

> **Usuario**: "Hazle a Claude esta pregunta para que sea más retadora: ¿cómo implementarías un sistema de consenso distribuido tolerante a fallos bizantinos?"
>
> **Tool detectada**: `consultar_experto` con `modelo="claude"`, `pregunta="..."`.
>
> **Respuesta inmediata**: "Un momento, le pregunto a Claude."
>
> **Respuesta verbal final**: resumen + "Es una respuesta larga, ¿la guardo en tus notas?"

### Ejemplo 14: Modo privado

> **Usuario**: "Activa modo privado."
>
> **Respuesta verbal**: "Modo privado activado. No usaré modelos externos en esta sesión."
>
> *(De aquí en adelante, llamadas a `consultar_experto` devuelven error con mensaje "modo privado activo".)*

---

## Lo que NO debe hacer la implementación

- ❌ Editar contenido existente en archivos (solo append/create).
- ❌ Borrar archivos.
- ❌ Hardcodear rutas — todo desde `config.yaml`.
- ❌ Tools sobre-específicas tipo `registrar_press_banca`. Mantener generalidad.
- ❌ Reescribir partes del proyecto que ya funcionan (STT, TTS). Solo integrar.
- ❌ Llamadas a internet. Todo offline.

---

## Entregables esperados de esta fase

1. Módulo `tools/` completo con las 8 tools.
2. `config.yaml` de ejemplo.
3. Modificación mínima a `main.py` para enchufar el flujo con tools.
4. System prompt con ejemplos few-shot.
5. Tests por tool.
6. README corto explicando cómo correr y cómo agregar tools nuevas en el futuro.

---

## Fases posteriores (referencia, no implementar todavía)

### Overlay Cyberpunk

- Usar `eww` (ElKowars wacky widgets) para Hyprland.
- Widget flotante, esquina superior derecha, sin decoración.
- Se dispara desde Python justo antes del `play` del TTS.
- Se cierra al terminar el audio.
- Estética: borde amarillo Cyberpunk, glitch sutil, imagen de "caller" + waveform.

### RAG

- Embeddings: `nomic-embed-text` vía Ollama.
- Vector store: ChromaDB local.
- Framework: LlamaIndex (tiene `ObsidianReader` que entiende wikilinks).
- Re-indexado: `watchdog` vigila cambios en la bóveda.
- Integración: la tool `buscar_en_vault` se actualiza para usar el RAG en lugar de ripgrep.

---

## Notas para el modelo que implemente esto

- Priorizar **simplicidad y robustez** sobre features. Mejor 8 tools sólidas que 15 frágiles.
- Si una decisión técnica no está clara, **preguntar antes de inventar**.
- Comentar el código en español (la persona usa español).
- Las funciones deben tener type hints completos.
- Manejo de errores: cada tool debe atrapar excepciones y devolver `{"status": "error", "message": "..."}` en lugar de crashear el asistente.
- Considerar concurrencia: si el usuario habla muy rápido y dispara dos tools casi simultáneas, usar lockfile sobre los archivos que se modifican.
