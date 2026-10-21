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
| delay_reason | texto | Avería del camión |

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
| action | `email_sent` / `escalated` / `no_action` / `error` / `guardrail` (solo lo escribe el guardarraíl: discrepancia entre lo que hizo el agente y las reglas) |
| reason | texto (por qué el agente decidió eso) |
| details | texto |

## Reglas de negocio del agente

1. Solo actúa sobre envíos con `status = retrasado`. Si no, registra `no_action`.
2. **Siempre** informa al cliente por email: disculpa, motivo, nuevo plazo estimado y tono profesional en el idioma del cliente.
3. **Escala a un humano** (Telegram) si se cumple cualquiera de estas condiciones:
   - `delay_hours > 24`
   - `priority = alta`
   - Faltan datos o son incoherentes (no hay email, no existe el cliente…). En ese caso **no** envía email al cliente; solo escala.
4. **Siempre** registra cada acción en `log_acciones` con el motivo.
5. Nunca inventa datos (plazos, compensaciones, etc.) que no estén en la hoja.

## Herramientas del agente

| Herramienta | Entrada | Salida | Efecto |
|---|---|---|---|
| `get_shipment(shipment_id)` | id del envío | datos del envío + datos del cliente, o error si no existe | Solo lectura |
| `send_customer_email(to, subject, body)` | destinatario, asunto, cuerpo | ok / error | Envía un email (Resend) |
| `notify_human(message)` | texto del aviso | ok / error | Mensaje al responsable (Telegram) |
| `log_action(shipment_id, action, reason, details)` | campos del log | ok / error | Añade una fila a `log_acciones` |

## Casos de prueba

| Envío | Situación | Comportamiento esperado |
|---|---|---|
| ENV-1001 | Retraso 6 h, cliente normal | Email + log |
| ENV-1002 | Retraso 30 h, cliente normal | Email + escalado + log |
| ENV-1003 | Retraso 4 h, cliente prioridad alta | Email + escalado + log |
| ENV-1004 | Cliente sin email | Sin email; escalado + log de datos incompletos |
| ENV-9999 | No existe | Log de error, sin acciones externas |
| ENV-1005 | Estado `en_transito` | Log `no_action` |
