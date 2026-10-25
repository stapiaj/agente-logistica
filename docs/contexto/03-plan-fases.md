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

## Fase 2b · Endurecimiento del agente

**Objetivo:** antes de conectar sistemas reales, cerrar los fallos vistos en las pruebas de la fase 2: dar margen de criterio al agente ante lo imprevisto y reforzar en código lo que no debe depender del modelo. Se añadió al plan tras la fase 2 (no estaba en el diseño inicial).

- **a) Escalado por criterio (regla 6):** si `delay_reason` describe algo grave que las reglas no cubren (robo, pérdida, daño, accidente), el agente escala con `JUDGMENT:` y el log lo registra (medible).
- **b) `delay_reason` es interno:** el email explica el motivo en lenguaje para el cliente, sin detalles internos y en su idioma.
- **c) Borrador en vez de email** en los escalados por criterio: `notify_human(message, email_draft)`; decide el humano.
- **d) Columna `new_eta`:** con fecha, el email la da; vacía, no se inventa; con formato inválido, dato incoherente → escalar sin email.
- **e) Guardarraíl sin avisos duplicados:** si el agente ya escaló, solo registra; un fallo técnico de una herramienta no cuenta como error del agente.
- **f) `shipment_id` inyectado por el código:** fuera de los parámetros de las herramientas (herramientas creadas por ejecución).

**Conceptos:** workflow frente a agente (el criterio ante lo imprevisto), prevenir frente a detectar, fallar de forma segura frente a degradar con elegancia, falsos positivos y fatiga de alertas, contratos de datos (qué campos ve el cliente).
**Romper a propósito:** un motivo vago ("Incidencia en ruta"); un `new_eta` con formato inválido.
**Preguntas de repaso:** ¿cómo das margen de criterio al agente sin sorpresas? ¿Qué haces si el guardarraíl genera demasiadas alertas? ¿Qué escribe el modelo y qué el código?
**Hecho cuando:** los 7 casos de prueba pasan con el modelo real (incluido ENV-1006, robo: aviso con borrador y sin email) y Sergio explica los cambios a–f.

---

## Fase 3 · Integraciones reales

**Objetivo:** sustituir los datos falsos por sistemas reales, una integración cada vez. Se divide en **3a** (Google Sheets) y **3b** (Resend + Telegram): cada integración tiene su cuenta, sus credenciales y sus errores; separadas, cada PR es revisable y los fallos se localizan mejor.

### Fase 3a · Google Sheets como sistema del cliente

**Objetivo:** que envíos, clientes y registro de acciones vivan en una hoja de Google real, sin cambiar la lógica del agente.

- Google Cloud: proyecto, Google Sheets API y Google Drive API, cuenta de servicio y su clave JSON (fuera de Git).
- Crear la hoja con las pestañas de `docs/contexto/05-modelo-datos.md` y compartirla solo con la cuenta de servicio.
- `scripts/seed_sheet.py`: rellenar la hoja con los mismos casos de `app/mock_data.py` (datos reproducibles).
- `integrations/sheets.py`: mismas funciones y mismo formato de datos que `mock_data` (patrón adaptador); convierte el texto de la hoja a tipos y un valor no convertible llega como dato incoherente a `rules.py`, sin romper el programa.
- `DATA_SOURCE=memory|sheets` en `.env` para elegir la fuente sin tocar código.

**Conceptos:** cuenta de servicio frente a API key, permisos y mínimo privilegio, patrón adaptador, tipos de datos al leer de una hoja, límites de uso de la API de Sheets.
**Romper a propósito:** dejar de compartir la hoja con la cuenta de servicio; un `GOOGLE_SHEET_ID` erróneo; texto en `delay_hours`.
**Preguntas de repaso:** si el cliente usara un ERP en vez de una hoja, ¿qué cambiaría? ¿Qué preguntarías al equipo de IT del cliente?
**Hecho cuando:** con `DATA_SOURCE=sheets` el agente lee de la hoja y escribe el log en ella; con `DATA_SOURCE=memory` todo sigue igual.

### Fase 3b · Resend y Telegram

**Objetivo:** que el email al cliente y el aviso al responsable salgan de verdad, con las protecciones necesarias ahora que una acción ya no se puede deshacer.

1. **Validación de argumentos** antes de ejecutar cada herramienta (`inspect.signature(tool).bind(**args)`): si no encajan, es error del agente, no fallo técnico. El banco de pruebas muestra argumentos y error de cada llamada fallida.
2. **Resend** (`integrations/email.py`): cuenta gratuita y API key. Sin dominio propio solo se puede enviar al email de la cuenta → `EMAIL_TEST_RECIPIENT` (modo pruebas: todo va ahí y el cuerpo indica a quién iba dirigido). `EMAIL_MODE=simulated|resend`.
3. **`send_customer_email` endurecida:** el destinatario lo inyecta el código (como `shipment_id`; el modelo solo redacta asunto y cuerpo) y, antes de enviar, consulta `rules.py`: si las reglas dicen "sin email", se niega (error del agente). Prevenir en vez de detectar, porque el email no se deshace.
4. **Telegram** (`integrations/telegram.py`): bot con @BotFather, `chat_id`, API HTTP, límite de longitud de los mensajes. `NOTIFY_MODE=simulated|telegram`.
5. **`notify_human` endurecida:** borrador del email en todo escalado sin email (criterio, fallo técnico, datos incoherentes) y motivos según `rules.py` añadidos siempre por el código, además de lo que escriba el modelo.
6. `scripts/fase3b_real.py`: prueba sin LLM y 3 casos del agente contra la hoja (ENV-1001, ENV-1002, ENV-1006).

**Conceptos:** acciones irreversibles (prevenir frente a detectar), modo pruebas o sandbox, validación de entradas, autenticación por API key y por token, qué hacer cuando un proveedor externo falla, por qué los motivos que lee el humano no deben depender solo del modelo.
**Romper a propósito:** API key de Resend errónea; `chat_id` de Telegram erróneo; el modelo intenta enviar un email cuando las reglas dicen que no.
**Preguntas de repaso:** ¿qué pasa si el proveedor de email cae a mitad de un caso? ¿Por qué comprobar el email antes de enviarlo si ya hay guardarraíl? ¿Cómo evitas avisar dos veces al humano?
**Hecho cuando:** con `EMAIL_MODE=resend` y `NOTIFY_MODE=telegram` llegan el email y el aviso de los 3 casos tal como se espera; con los modos simulados todo sigue funcionando.

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

**Lo que cambió al hacerla (2026-10-24/25):** se añadió el **segundo canal de avisos** (email al responsable si Telegram falla, decisión del chat principal tras la 3b) y una **comprobación de la configuración al arrancar** (línea `[startup]`; sin lo imprescindible el servidor no arranca). Durante la fase, Render despliega la rama `fase-5-deploy`; al fusionar el PR pasa a `main`. Roturas extra del encargo: `WEBHOOK_SECRET` distinto en el script y en Render, y `chat_id` de Telegram erróneo para ver el segundo canal. Hallazgo en producción: pegar "retrasado" sobre "retrasado" en la hoja reenvía el aviso (Google no da el valor anterior al pegar).

---

## Fase 6 · Presentación

**Objetivo:** dejar el proyecto listo para enseñarlo: que funcione sin sorpresas, que cualquiera entienda qué hace y por qué en dos minutos, y que el repo pueda ser público sin secretos ni notas de trabajo.

**Cambio de plan (2026-10-25):** se divide en tres partes. Es la fase más variada, y publicar el repo (reescribir el historial) es una operación delicada que merece su propia sesión.

### Fase 6a · Arreglo final, limpieza de textos y README

- Arreglar el pegado en la hoja: el script guarda el último estado avisado de cada envío y compara con eso, no con `e.oldValue` (que Google no da al pegar). Un segundo retraso real sigue avisando.
- Limpiar los textos que serán públicos (`docs/contexto/`, `docs/estado/lecciones.md`, comentarios y scripts): con el enfoque de proyecto personal y sin datos personales; las preguntas de cada fase son "preguntas de repaso".
- Capturas reales sin datos personales en `assets/` y diagrama de arquitectura.
- `README.md` (inglés) y `README.es.md` (español): qué hace, demo, problema, solución, cómo funciona, decisiones clave, resultados, limitaciones y siguientes pasos, qué aprendí y cómo ejecutarlo.
- Licencia MIT.

**Conceptos:** por qué un pegado no trae el valor anterior y cómo se arregla guardando estado propio; qué hace que un README funcione para alguien de negocio; licencias de código abierto.
**Romper a propósito:** pegar una columna entera de estados y comprobar que no sale ningún aviso.
**Hecho cuando:** el pegado ya no reenvía avisos en producción, todos los archivos que vayan a ser públicos están limpios (enfoque de proyecto personal, sin datos personales), y el README (en los dos idiomas) explica el proyecto con capturas reales sin datos personales.

### Fase 6b · Historial limpio y repo público

- Copia de seguridad del repo antes de tocar nada.
- Reescribir el historial con los textos limpios y sin las notas de trabajo (`bitacora.md`, `progreso.md`, `proximo-encargo.md` salen del repo y de su historial, pero se quedan en la carpeta local).
- Revisar que no haya secretos en ningún commit y que todos usen el email noreply.
- Publicar en un repo nuevo y público, y reconectar Render a él.

**Hecho cuando:** el repo público tiene toda la historia de commits con textos limpios, sin secretos ni notas de trabajo, y producción sigue funcionando desplegada desde él.

### Fase 6c · Vídeos, difusión y método (chat principal)

- Vídeo de demo de 1-2 minutos (y un teaser corto opcional).
- Texto para publicar el proyecto.
- Repaso final: contar el proyecto en 2 minutos y responder las preguntas de repaso de todas las fases.
- Dos documentos para futuros proyectos: la guía de método para proyectos guiados con IA y un checklist de lecciones para construir cualquier proyecto con IA.

---

## Extras opcionales (si sobra tiempo)

- Llamada de voz con un proveedor de voz (normalmente de pago).
- Panel sencillo con métricas del log (envíos gestionados, % escalados).
- Tests automáticos de las herramientas con `pytest`, ejecutados en cada Pull Request con GitHub Actions.
- Usar Claude como LLM en lugar de Gemini y comparar.
