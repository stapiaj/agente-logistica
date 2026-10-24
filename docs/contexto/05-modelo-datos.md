# Modelo de datos, reglas y herramientas

## Google Sheet: pestañas

### `envios`

| Columna | Tipo | Ejemplo |
|---|---|---|
| shipment_id | texto | ENV-1001 |
| customer_id | texto | CLI-01 |
| origin | texto | Madrid |
| destination | texto | Valencia |
| carrier | texto | TransIberia |
| expected_date | fecha (AAAA-MM-DD) | 2026-10-20 |
| status | `en_transito` / `retrasado` / `entregado` | retrasado |
| delay_hours | número | 30 |
| delay_reason | texto **interno** (no se copia al cliente) | Avería del camión |
| new_eta | fecha (AAAA-MM-DD) o vacía si aún no se sabe | 2026-10-23 |

### `clientes`

| Columna | Tipo | Ejemplo |
|---|---|---|
| customer_id | texto | CLI-01 |
| name | texto | Frutas Levante SL |
| contact_email | texto | (email de Sergio para pruebas) |
| priority | `alta` / `normal` | alta |
| language | `es` / `en` | es |

### `log_acciones`

| Columna | Tipo |
|---|---|
| timestamp | fecha y hora ISO |
| shipment_id | texto |
| action | `email_sent` / `escalated` / `no_action` / `error` / `guardrail` (solo lo escribe el guardarraíl: discrepancia entre lo que hizo el agente y las reglas, escalado por criterio aceptado o fallo técnico de una herramienta) |
| reason | texto (por qué el agente decidió eso) |
| details | texto |

### `eventos` (fase 4)

Avisos del webhook ya recibidos (idempotencia). La escribe solo la API; `scripts/seed_sheet.py` la crea si falta y la conserva salvo `--reset-events`. Va aparte de `log_acciones`: avisos recibidos ≠ lo que hizo el agente.

| Columna | Tipo |
|---|---|
| received_at | fecha y hora ISO (UTC) |
| event_id | texto (`evt-<shipment_id>-<uuid>` desde la hoja) |
| shipment_id | texto |

## Contrato del webhook (fase 4)

`POST /webhook/shipment-delayed` (y `GET /health` → `200 {"status": "ok"}`)

- **Cabecera:** `X-Webhook-Secret: <WEBHOOK_SECRET>`
- **Cuerpo (JSON):** `{"shipment_id": "ENV-1001", "event_id": "evt-ENV-1001-…"}`. Ambos texto obligatorio, sin espacios sobrantes, no vacío; `event_id` como máximo 200 caracteres (de él sale la clave de Resend, ≤ 256). Campos extra: se ignoran.

| Respuesta | Cuándo | ¿Se ejecuta el agente? | El script de la hoja |
|---|---|---|---|
| `202 {"status": "accepted", …}` | Aviso nuevo (apuntado en `eventos`) | Sí, en segundo plano | Fin |
| `200 {"status": "already_processed", …}` | `event_id` ya recibido | No | Fin |
| `401` | Falta el secreto o no coincide | No | No reintenta |
| `422` | Cuerpo que no encaja (o JSON mal formado) | No | No reintenta |
| `503` | No se puede comprobar si está repetido (hoja caída) | No (falla cerrado) | Reintenta con el mismo `event_id` |

El servidor no comprueba si el envío existe: eso lo hace el agente (ENV-9999 → `202` y log `error`).

## Reglas de negocio del agente

1. Solo actúa sobre envíos con `status = retrasado`. Si no, registra `no_action`.
2. **Siempre** informa al cliente por email: disculpa, motivo, nuevo plazo estimado y tono profesional en el idioma del cliente.
   - **Motivo:** `delay_reason` es una nota interna. El email explica la causa con palabras generales para el cliente, traducida a su idioma y sin detalles internos (denuncias, nombres de personas, centros o almacenes, procesos).
   - **Nuevo plazo:** si `new_eta` tiene fecha, el email la da; si está vacía, dice que se le informará en cuanto se sepa, sin inventar una fecha.
3. **Escala a un humano** (Telegram) si se cumple cualquiera de estas condiciones:
   - `delay_hours > 24`
   - `priority = alta`
   - Faltan datos o son incoherentes (no hay email, no existe el cliente, `new_eta` con formato inválido…). En ese caso **no** envía email al cliente: escala con el borrador del email en `email_draft`.
   - El aviso lleva siempre, añadidos por el código, los motivos según `rules.py` (bloque "Rules (checked by code)"), separados del mensaje del modelo: el humano no depende solo de la interpretación del modelo.
4. **Siempre** registra cada acción en `log_acciones` con el motivo.
5. Nunca inventa datos (plazos, compensaciones, etc.) que no estén en la hoja.
6. **Escalado por criterio.** Si `delay_reason` describe algo grave que las reglas no cubren (robo, pérdida o daño de la mercancía, accidente, imposibilidad de estimar la entrega), escala igualmente, aunque también aplique otra regla. El aviso empieza por `JUDGMENT:` y explica por qué. **No** envía el email: lo incluye como borrador (`email_draft`, empezando por `Subject:`) en el aviso, y el humano decide. El guardarraíl lo acepta como escalado legítimo y lo registra (`guardrail`) para poder medirlo; las situaciones que se repitan pasarán a `rules.py`.
7. **Borrador en todo escalado sin email** (criterio, datos incoherentes, cliente sin email, email fallido o rechazado): el aviso incluye en `email_draft` el email que se habría enviado, para que el humano reciba el trabajo medio hecho.

### Guardarraíl (en código, tras cada ejecución)

Compara lo que hizo el agente (y lo que intentó) con lo que dice `rules.py`:

- **Faltó un escalado:** escala el código (corrección, `escalated` con motivo `guardrail correction: …`).
- **Escaló sin regla, no envió email debiendo, o lo envió sin deber:** registra la discrepancia (`guardrail`).
- **Nunca dos avisos:** si el agente ya escaló, el guardarraíl solo registra.
- **Fallo técnico de una herramienta** (p. ej. el proveedor de email caído): es motivo legítimo de escalado, no cuenta como discrepancia; se registra como informativo. Si el agente no escaló, escala el código.
- **Escalado por criterio (`JUDGMENT:`):** aceptado y registrado siempre; discrepancia si además envió el email.
- **Escalado sin email y sin borrador:** discrepancia registrada (nunca se bloquea un aviso).
- **Errores del agente** (argumentos inválidos, email rechazado por las reglas): registrados (`guardrail`) para medirlos.
- **Si el aviso del agente falla** (Telegram caído): el guardarraíl lo reintenta una vez con su mensaje y borrador; si también falla, fila `error` en el log.
- **Sin log:** lo escribe el código.

## Herramientas del agente

Cada ejecución trata **un solo envío**. El código crea las herramientas con el `shipment_id` ya dentro (`make_tools(shipment_id, event_id)` en `app/tools.py`): **el modelo nunca escribe el id**, así que no puede cambiarlo. La entrada se normaliza antes (`strip().upper()`). El `event_id` del aviso (fase 4) viaja igual, solo para la clave de idempotencia del email; sin aviso (scripts) va vacío y no hay clave.

| Herramienta | Entrada | Salida | Efecto |
|---|---|---|---|
| `get_shipment()` | ninguna (el id lo pone el código) | datos del envío + datos del cliente, o error si no existe | Solo lectura |
| `send_customer_email(subject, body)` | asunto y cuerpo (el destinatario, `contact_email`, lo pone el código) | ok / error | Antes de enviar consulta `rules.py` y se niega si no toca email (o si ya se escaló por criterio); si toca, envía (Resend o simulado, según `EMAIL_MODE`), con `Idempotency-Key: shipment-delayed/<event_id>` si viene de un aviso |
| `notify_human(message, email_draft="")` | texto del aviso; borrador del email no enviado (obligatorio en todo escalado sin email) | ok / error | Mensaje al responsable (Telegram o simulado, según `NOTIFY_MODE`); el código añade el `shipment_id` y los motivos según `rules.py` |
| `log_action(action, reason, details)` | campos del log (el id lo pone el código) | ok / error | Añade una fila a `log_acciones` |

Si una herramienta lanza una excepción, el error vuelve al modelo marcado como `technical` (fallo del sistema, no del agente). Si los argumentos no encajan con la firma, la herramienta no existe o `send_customer_email` se niega por las reglas, vuelve como `agent_error` (error del agente) y la herramienta no llega a actuar.

## Casos de prueba

| Envío | Situación | Comportamiento esperado |
|---|---|---|
| ENV-1001 | Retraso 6 h, cliente normal | Email + log |
| ENV-1002 | Retraso 30 h, cliente normal | Email + escalado + log |
| ENV-1003 | Retraso 4 h, cliente prioridad alta | Email + escalado + log |
| ENV-1004 | Cliente sin email | Sin email; escalado con borrador + log de datos incompletos |
| ENV-9999 | No existe | Log de error, sin acciones externas |
| ENV-1005 | Estado `en_transito` | Log `no_action` |
| ENV-1006 | Retraso 6 h, cliente normal, camión robado (motivo con detalles internos) | Escalado por criterio (`JUDGMENT:`), **sin email**, borrador en el aviso sin detalles internos; log `escalated` + `guardrail` (criterio aceptado) |
