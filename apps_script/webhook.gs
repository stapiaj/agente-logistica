/**
 * Agente Logistica - sends a "shipment delayed" notice to our server (phase 4, T7).
 *
 * Lives in the Google Sheet (Extensions > Apps Script). When someone sets the
 * `status` of a row in `envios` to "retrasado", it POSTs this to the server:
 *
 *   POST {WEBHOOK_URL}
 *   X-Webhook-Secret: {WEBHOOK_SECRET}
 *   {"shipment_id": "ENV-1001", "event_id": "evt-ENV-1001-<uuid>"}
 *
 * It CANNOT be tested before phase 5: it runs on Google's servers, and from
 * there 127.0.0.1 is Google's own machine, not your computer. It needs the
 * public Render URL.
 *
 * ONE-TIME SETUP (phase 5):
 * 1. Paste this file into the Sheet's Apps Script project.
 * 2. Project Settings > Script properties > add:
 *      WEBHOOK_URL    = https://<your-service>.onrender.com/webhook/shipment-delayed
 *      WEBHOOK_SECRET = the same value as WEBHOOK_SECRET in the server's .env
 *    Script properties are Apps Script's ".env": the secret never goes in the code.
 * 3. Run installTrigger() once from the editor and accept the permissions.
 * 4. Run sendTestNotice() to check the connection; see View > Executions.
 *
 * WHY AN INSTALLABLE TRIGGER: the simple onEdit(e) trigger is not allowed to
 * call external URLs. An installable trigger runs with the permissions of the
 * person who installed it, so it can. That is also why the handler is NOT
 * called onEdit: that name would ALSO run as a simple trigger (and fail).
 *
 * ONE EVENT PER CHANGE (decision T7, option a): every time a cell BECOMES
 * "retrasado" is a new fact with a new event_id (a second delay of the same
 * shipment must reach the customer). Retries of the SAME notice reuse its
 * event_id, so the server ignores them (idempotency, T5).
 *
 * Only edits made by a person in the Sheet fire the trigger. Edits through the
 * API (scripts/seed_sheet.py, the agent) do not.
 */

const TAB_SHIPMENTS = 'envios';
const DELAYED = 'retrasado';
const MAX_ATTEMPTS = 3;         // first try + 2 retries
const RETRY_WAIT_MS = 5000;     // 5 s, then 10 s (Render may be waking up)

/** Run ONCE by hand: creates the installable trigger (never twice). */
function installTrigger() {
  const exists = ScriptApp.getProjectTriggers()
    .some(t => t.getHandlerFunction() === 'onShipmentEdit');
  if (exists) {
    console.log('Trigger already installed, nothing to do.');
    return;
  }
  ScriptApp.newTrigger('onShipmentEdit')
    .forSpreadsheet(SpreadsheetApp.getActive())
    .onEdit()
    .create();
  console.log('Trigger installed: onShipmentEdit runs on every edit.');
}

/** Installable onEdit handler. `e` describes the edit Google just saw. */
function onShipmentEdit(e) {
  const sheet = e.range.getSheet();
  if (sheet.getName() !== TAB_SHIPMENTS) return;

  // Find the columns by their header name (row 1), never by position:
  // moving a column in the Sheet must not break the script.
  const header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]
    .map(cell => String(cell).trim());
  const statusCol = header.indexOf('status') + 1;   // 1-based, 0 = not found
  const idCol = header.indexOf('shipment_id') + 1;
  if (!statusCol || !idCol) {
    console.error(`Missing "status" or "shipment_id" header in ${TAB_SHIPMENTS}.`);
    return;
  }

  // Was the status column part of the edit? (the edit can be a pasted block)
  const first = e.range.getColumn();
  const last = first + e.range.getNumColumns() - 1;
  if (statusCol < first || statusCol > last) return;

  const singleCell = e.range.getNumRows() === 1 && e.range.getNumColumns() === 1;
  for (let i = 0; i < e.range.getNumRows(); i++) {
    const row = e.range.getRow() + i;
    if (row === 1) continue;  // the header itself
    const status = normalize(sheet.getRange(row, statusCol).getValue());
    if (status !== DELAYED) continue;
    // Single cell: only a CHANGE to "retrasado" counts (retyping it does not).
    // Pasted blocks don't tell us the old value: each delayed row is sent.
    if (singleCell && normalize(e.oldValue) === DELAYED) continue;
    const shipmentId = String(sheet.getRange(row, idCol).getValue()).trim();
    if (!shipmentId) continue;
    sendNotice(shipmentId);
  }
}

/** Builds ONE notice and sends it, retrying with the SAME event_id. */
function sendNotice(shipmentId) {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty('WEBHOOK_URL');
  const secret = props.getProperty('WEBHOOK_SECRET');
  if (!url || !secret) {
    console.error('Missing WEBHOOK_URL or WEBHOOK_SECRET in Script properties: nothing sent.');
    return;
  }

  // Created ONCE per notice, before any attempt: retries carry the same id.
  const eventId = `evt-${shipmentId}-${Utilities.getUuid()}`;
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'X-Webhook-Secret': secret },
    payload: JSON.stringify({ shipment_id: shipmentId, event_id: eventId }),
    muteHttpExceptions: true,  // give us the status code instead of throwing
  };

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    let code;
    let body = '';
    try {
      const response = UrlFetchApp.fetch(url, options);
      code = response.getResponseCode();
      body = response.getContentText().slice(0, 300);
    } catch (err) {
      code = 0;  // no answer at all (timeout, DNS...)
      body = String(err);
    }

    if (code === 202 || code === 200) {
      // 202 = accepted, the agent runs. 200 = already processed (a retry
      // whose first attempt did arrive): also fine, nothing else to do.
      console.log(`${shipmentId} ${eventId}: ${code} ${body}`);
      return;
    }
    if (code === 401 || code === 422) {
      // Our mistake (wrong secret, bad body): retrying won't fix it.
      console.error(`${shipmentId} ${eventId}: ${code}, not retried. ${body}`);
      return;
    }
    // 503 (server can't check duplicates), other 5xx or no answer: may pass.
    console.warn(`${shipmentId} ${eventId}: attempt ${attempt} got ${code}. ${body}`);
    if (attempt < MAX_ATTEMPTS) Utilities.sleep(RETRY_WAIT_MS * attempt);
  }
  console.error(`${shipmentId} ${eventId}: gave up after ${MAX_ATTEMPTS} attempts.`);
}

/** Run by hand (phase 5) to test the connection without editing the Sheet. */
function sendTestNotice() {
  sendNotice('ENV-1001');
}

function normalize(value) {
  return String(value === undefined || value === null ? '' : value).trim().toLowerCase();
}
