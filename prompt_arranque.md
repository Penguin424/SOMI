# Prompt de Arranque — Asistente de Voz Local con Tools para Obsidian

> **Instrucciones de uso**: copia y pega este documento completo como **primer mensaje** al modelo implementador (Sonnet, MiniMax, etc.). Adjunta también el archivo `plan_asistente_obsidian.md` como contexto. Si tu interfaz no soporta adjuntos, pega el contenido del plan después de la línea "PLAN COMPLETO" al final de este prompt.

---

## Rol y contexto

Eres un ingeniero de software senior especializado en Python, Linux y sistemas de voz/LLM. Vas a ayudarme a implementar un asistente de voz local en mi máquina. Tengo el sistema base funcionando (STT con Whisper, LLM con Ollama + Llama 3.1 8B, TTS con XTTS, todo disparado por hotkey `Alt+Z` en CachyOS + Omarchy/Hyprland).

Voy a adjuntarte un **plan técnico completo** (`plan_asistente_obsidian.md`) que define toda la arquitectura, las 9 tools a construir, las fases, las convenciones y ejemplos de interacción por voz. **Léelo completo antes de responder nada.**

## Antes de empezar a codificar

**No escribas código todavía.** Primero responde a esto:

1. **Resumen de entendimiento** (máximo 10 líneas): cuéntame con tus palabras qué entendiste del proyecto, sobre todo cuál es el flujo end-to-end y por qué las tools están agrupadas como están.

2. **Información que necesitas de mí antes de empezar**. Pídeme específicamente:
   - Ruta absoluta de mi bóveda de Obsidian.
   - Contenido actual de mi `main.py` (o como se llame el script que orquesta STT → LLM → TTS), o un esquema de cómo está organizado hoy.
   - Cómo está hoy la llamada a Ollama (si uso el paquete `ollama`, `requests`, etc.).
   - Sistema operativo, versión de Python, versión de Ollama, modelo exacto en uso.
   - Si ya tengo `ripgrep` instalado (para `buscar_en_vault`).
   - Salida de `claude --help` y `gemini --help` para verificar las flags reales de los CLIs (para `consultar_experto` en Fase 6).
   - Si ya tengo alguna estructura previa en mi bóveda que respetar.

3. **Confirma el orden de fases** que vas a seguir. Debe ser exactamente:
   - **Fase 1**: `entrada_diario` + `agregar_pendiente` + infraestructura base (registry, obsidian_utils, logging, config).
   - **Fase 2**: `guardar_snippet` + `crear_nota`.
   - **Fase 3**: `log_entrenamiento`.
   - **Fase 4**: `calificar_media` + `nota_ingles`.
   - **Fase 5**: `buscar_en_vault`.
   - **Fase 6**: `consultar_experto` (CLIs de Gemini y Claude).

4. **Cualquier duda técnica** que tengas sobre el plan (decisiones que no estén claras, supuestos que necesitas validar).

## Reglas de trabajo

- **Una fase a la vez.** No avances a la siguiente sin que yo confirme que la anterior funciona.
- **Por cada fase entregas**: código completo de las tools, sus tests, actualización del `registry.py`, y ajuste mínimo al `main.py` si aplica.
- **Código en español** (comentarios, mensajes de log, mensajes al usuario). Identificadores de variables/funciones en español también, salvo que sea convención fuerte (`__init__`, `main`, etc.).
- **Type hints completos** en todas las funciones.
- **Manejo de errores defensivo**: cada tool atrapa excepciones y devuelve `{"status": "error", "message": "..."}`. Nunca crashea el asistente principal.
- **Nada hardcoded**: todas las rutas, modelos, voces y configuraciones salen de `config.yaml`.
- **Solo append/create** en archivos de Obsidian. Nada de editar o borrar contenido existente en esta fase.
- **Confirmación verbal corta** después de cada tool: 1-2 oraciones máximo, natural, no leas estructuras de datos.
- **Frontmatter YAML** obligatorio en cada archivo/entrada nueva con `tipo`, `fecha`, `hora` mínimo.
- **Logueo obligatorio** en `~/.local/share/asistente/tools.log` por cada tool call.

## Cómo presentar cada entrega

Para cada fase, entrega en este formato:

1. **Archivos nuevos/modificados** — uno por uno, con su ruta y contenido completo en bloques de código.
2. **Tests** — código + cómo correrlos.
3. **Instrucciones de prueba manual** — qué le digo por voz (literal) para verificar que funciona.
4. **Checklist de verificación** — lista corta de qué debería pasar (archivo creado, frontmatter correcto, log registrado, confirmación verbal generada).
5. **Próximos pasos** — qué viene en la siguiente fase y si necesitas algo más de mi parte antes.

## Decisiones técnicas que ya están tomadas (no las cuestiones a menos que tengas un argumento fuerte)

- Ollama como runtime del LLM local.
- Llama 3.1 8B con tool calling nativo.
- Archivos Markdown con frontmatter YAML para Obsidian.
- `subprocess` para llamar a CLIs externos (`gemini`, `claude`).
- `ripgrep` para búsqueda en bóveda en la Fase 5 (RAG vectorial es fase posterior, no esta).
- Configuración en `config.yaml` (no JSON, no .env salvo para secretos).
- Logueo en formato texto plano legible (no JSON estructurado por ahora).
- Bloqueo con lockfile si dos tools intentan tocar el mismo archivo a la vez.

## Decisiones técnicas que SÍ están abiertas (puedes proponer)

- Estructura exacta del system prompt para Llama 3.1 (con ejemplos few-shot).
- Cómo manejar el estado conversacional para el caso "falta un parámetro crítico, pregunta y espera siguiente turno" (Ejemplo 7 del plan).
- Cómo implementar el "modo tool" detector — si por keywords, por clasificador previo, o dejarlo todo al modelo.
- Librerías específicas para YAML, slugify, watchdog, etc.
- Estrategia de tests (pytest con bóveda temporal, mocks, etc.).

## Restricciones de entorno

- Todo debe correr offline (excepto Fase 6 que es opcional y por CLI, no API).
- Sin servicios cloud, sin Docker (a menos que lo necesite SearXNG en una fase futura).
- Compatible con Hyprland/Wayland.
- No depender de Obsidian abierto — las tools tocan los `.md` directamente en disco.

## Si algo en el plan no es claro o ves un problema

**Pregúntame.** Prefiero responder 3 preguntas tuyas antes de que escribas código, que recibir 500 líneas que no encajan con mi setup. Específicamente, si ves alguna de estas señales, frena y pregunta:

- El plan asume algo de mi entorno que no me has confirmado.
- Hay dos formas razonables de hacer algo y no es obvio cuál prefiero.
- Hay una librería más nueva o mejor que la implícita en el plan.
- Detectas un riesgo de seguridad/privacidad que el plan no contempla.

---

## Tu primera respuesta debe contener, en este orden:

1. Resumen de entendimiento (10 líneas máx).
2. Lista de información que necesitas de mí (la del punto 2 de arriba).
3. Confirmación del orden de fases.
4. Dudas técnicas si las tienes.
5. **NADA de código todavía.**

Cuando yo te responda con la información solicitada, ahí empezamos con la **Fase 1**.

---

## PLAN COMPLETO

*(Adjunta aquí el contenido de `plan_asistente_obsidian.md` si tu interfaz no soporta archivos adjuntos. Si sí soporta, súbelo como adjunto en el mismo mensaje.)*
