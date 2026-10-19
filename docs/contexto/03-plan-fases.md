# Plan por fases

Cada fase se hace en su propia rama y termina con algo que funciona, una explicación de Sergio, `docs/estado/progreso.md` actualizado y un Pull Request fusionado en `main`.

---

## Fase 0 · Entorno

**Objetivo:** dejar el ordenador listo.

- Comprobar Python, Git y VS Code. Crear el entorno virtual `.venv`.
- Crear `.gitignore`, `.env.example`, `requirements.txt` y la estructura de carpetas.
- Crear el repositorio en GitHub (privado al principio) y hacer el primer commit.
- Crear la API key de Gemini en Google AI Studio y guardarla en `.env`.

**Conceptos:** entorno virtual, dependencias, variables de entorno, por qué los secretos no van a GitHub, commit/push.
**Hecho cuando:** `git status` está limpio, el repo existe en GitHub y `.env` no aparece en él.

---

## Fase 1 · Hablar con un LLM desde Python

**Objetivo:** un script (`scripts/fase1_llm.py`) que envía un prompt a Gemini y muestra la respuesta.

- Leer la API key desde `.env`.
- Probar un prompt del sistema ("eres un agente de atención de un operador logístico…").
- Pedir una respuesta en JSON estructurado.

**Conceptos:** qué es una API, API key, petición/respuesta, JSON, prompt del sistema frente a mensaje del usuario, salida estructurada.
**Romper a propósito:** API key incorrecta (ver el error 400/401/403) y quitar internet.
**Preguntas de repaso:** ¿qué pasa por debajo cuando llamas al modelo? ¿Por qué pedir JSON?

---

## Fase 2 · El agente con herramientas (con datos falsos en memoria)

**Objetivo:** `app/agent.py` + `app/tools.py`. El agente recibe un `shipment_id` y decide qué herramientas usar. Las herramientas trabajan contra un diccionario en Python (aún sin Sheets).

- Definir las 4 herramientas (ver `docs/contexto/05-modelo-datos.md`) con firmas y descripciones claras.
- Implementar el bucle del agente: el modelo pide una herramienta → se ejecuta → se devuelve el resultado → repetir hasta terminar.
- Escribir las reglas de negocio en el prompt del sistema.
- Probar con los casos de prueba de `docs/contexto/05-modelo-datos.md`.

**Conceptos:** tool/function calling, bucle agente, por qué las descripciones de las herramientas importan, límites de iteraciones, determinismo frente a criterio del LLM.
**Romper a propósito:** un `shipment_id` que no existe; una herramienta que lanza una excepción; una descripción de herramienta ambigua.
**Preguntas de repaso:** ¿cómo decide el agente qué herramienta usar? ¿Qué haces si llama a la equivocada? ¿Qué reglas pondrías en código y cuáles en el prompt?

---

## Fase 3 · Integraciones reales

**Objetivo:** sustituir los datos falsos por sistemas reales, una integración cada vez.

1. **Google Sheets** (`integrations/sheets.py`): crear la hoja con las pestañas de `docs/contexto/05-modelo-datos.md`, cuenta de servicio en Google Cloud, compartir la hoja con ella, leer y escribir con `gspread`.
2. **Resend** (`integrations/email.py`): cuenta gratuita, API key, envío al email de Sergio.
3. **Telegram** (`integrations/telegram.py`): crear el bot con @BotFather, obtener el `chat_id`, enviar un mensaje con la API HTTP.

**Conceptos:** autenticación (API key frente a cuenta de servicio), permisos, rate limits, qué pasa cuando un sistema externo falla, reintentos.
**Romper a propósito:** quitar el permiso de la hoja a la cuenta de servicio; un email de destino inválido; un token de Telegram erróneo.
**Preguntas de repaso:** si el cliente usara un ERP en vez de una hoja, ¿qué cambiaría? ¿Qué preguntarías al equipo de IT del cliente?

---

## Fase 4 · La API y el webhook

**Objetivo:** `app/main.py` con FastAPI y el Apps Script que dispara el flujo.

- Endpoint `POST /webhook/shipment-delayed` que valida el token y el JSON y llama al agente.
- Endpoint `GET /health` para comprobar que el servicio vive.
- Probar en local con la documentación automática de FastAPI (`/docs`) y con una petición manual.
- Escribir `apps_script/webhook.gs` (se probará contra la URL pública en la fase 5).

**Conceptos:** servidor web, endpoint, métodos HTTP, códigos de estado, webhook (push) frente a polling (pull), validación de entradas, autenticación por token, idempotencia (¿qué pasa si llega el mismo aviso dos veces?).
**Romper a propósito:** token incorrecto (401), JSON mal formado (422), el mismo envío dos veces.
**Preguntas de repaso:** ¿por qué webhook y no consultar la hoja cada minuto? ¿Cómo evitas procesar un aviso dos veces?

---

## Fase 5 · Despliegue

**Objetivo:** el sistema funciona solo, sin el ordenador de Sergio encendido.

- Subir a GitHub y crear el web service en Render conectado al repo.
- Configurar las variables de entorno en Render (los mismos secretos que `.env`).
- Configurar el Apps Script con la URL pública y el token, y activar el trigger.
- Prueba de punta a punta: cambiar un envío a "retrasado" y ver email, Telegram y log.
- Revisar los logs de Render ante cualquier fallo.

**Conceptos:** local frente a producción, variables de entorno en la nube, logs, "cold start" del plan gratuito, despliegue continuo desde GitHub.
**Romper a propósito:** borrar una variable de entorno en Render y leer el error en los logs.
**Preguntas de repaso:** ¿qué harías para que esto aguantara 10.000 envíos al día? ¿Cómo lo monitorizarías?

---

## Fase 6 · Presentación

**Objetivo:** dejar el proyecto listo para enseñarlo.

- `README.md` como caso de cliente: problema, proceso actual, solución, diagrama, impacto, limitaciones y roadmap (ver `docs/contexto/01-contexto.md`).
- Vídeo de demo de 1-2 minutos.
- Repo público (decidido): antes de cambiar la visibilidad, revisar que no haya secretos en el historial (`git log -p`, buscar claves) y que los commits usen el email noreply.
- Texto para publicar el proyecto.
- Ensayo: contar el proyecto en 2 minutos y responder las preguntas de repaso de todas las fases.

---

## Extras opcionales (si sobra tiempo)

- Llamada de voz con un proveedor de voz (normalmente de pago).
- Panel sencillo con métricas del log (envíos gestionados, % escalados).
- Tests automáticos de las herramientas con `pytest`, ejecutados en cada Pull Request con GitHub Actions.
- Usar Claude como LLM en lugar de Gemini y comparar.
