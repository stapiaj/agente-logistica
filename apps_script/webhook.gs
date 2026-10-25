/**
 * Agente Logistica - sends a "shipment delayed" notice to our server.
 *
 * Lives in the Google Sheet (Extensions > Apps Script). When someone sets the
 * `status` of a row in `envios` to "retrasado", it POSTs this to the server:
 *
 *   POST {WEBHOOK_URL}
 *   X-Webhook-Secret: {WEBHOOK_SECRET}
 *   {"shipment_id": "ENV-1001", "event_id": "evt-ENV-1001-<uuid>"}
 *
 * It runs on Google's servers, so it needs the public server URL (from there,
 * 127.0.0.1 is Google's own machine, not your computer).
 *
 * ONE-TIME SETUP:
 * 1. Paste this file into the Sheet's Apps Script project.
 * 2. Project Settings > Script properties > add:
 *      WEBHOOK_URL    = https://<your-service>.onrender.com/webhook/shipment-delayed
 *      WEBHOOK_SECRET = the same value as WEBHOOK_SECRET on the server
 *    Script properties are Apps Script's ".env": the secret never goes in the code.
 * 3. Run installTrigger() once from the editor and accept the permissions.
 * 4. Run initNotifiedState() once (see "MEMORY" below).
 * 5. Run sendTestNotice() to check the connection; see Executions.
 *
 * WHY AN INSTALLABLE TRIGGER: the simple onEdit(e) trigger is not allowed to
 * call external URLs. An installable trigger runs with the permissions of the
 * person who installed it, so it can. That is also why the handler is NOT
 * called onEdit: that name would ALSO run as a simple trigger (and fail).
 *
 * ONE NOTICE PER DELAY: every time a shipment BECOMES "retrasado" is a new
 * fact with a new event_id (a second delay of the same shipment must reach
 * the customer). Retries of the SAME notice reuse its event_id, so the server
 * ignores them (idempotency).
 *
 * MEMORY (why the script keeps its own state): Google only tells us the old
 * value of a cell (e.oldValue) when ONE cell is typed by hand. When you paste,
 * even over a single cell, e.oldValue is undefined: Google does not keep a
 * copy of what was there. Comparing with e.oldValue made pasting "retrasado"
 * over "retrasado" look like a new delay, and the customer got a duplicate
 * email. So the script remembers by itself which shipments it has already
 * notified as delayed, in the Document properties (a key-value store inside
 * the Sheet that only the script touches):
 *   - status "retrasado" and no mark   -> notify and keep the mark
 *   - status "retrasado" and a mark    -> nothing (already notified)
 *   - any other status, or empty       -> remove the mark (a later delay
 *                                         is a new one and will be notified)
 * Typing and pasting follow the same rule. The key is the shipment_id, not the
 * row number, so sorting the Sheet does not break it.
 *
 * Edits through the API (scripts/seed_sheet.py, the agent) do NOT fire the
 * trigger, so the memory cannot see them. After running the seed, run
 * initNotifiedState() again so the memory matches the Sheet.
 */

const TAB_SHIPMENTS = 'envios';
const DELAYED = 'retrasado';
const MAX_ATTEMPTS = 3;         // first try + 2 retries
const RETRY_WAIT_MS = 5000;     // 5 s, then 10 s (Render may be waking up)
const NOTIFIED_PREFIX = 'notified:';
const LOCK_WAIT_MS = 10000;

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
  const cols = findColumns(sheet);
  if (!cols) return;

  // Was the status column part of the edit? (the edit can be a pasted block)
  const firstCol = e.range.getColumn();
  const lastCol = firstCol + e.range.getNumColumns() - 1;
  if (cols.status < firstCol || cols.status > lastCol) return;

  const firstRow = Math.max(e.range.getRow(), 2);  // row 1 is the header
  const lastRow = e.range.getRow() + e.range.getNumRows() - 1;
  if (lastRow < firstRow) return;
  const rows = readRows(sheet, cols, firstRow, lastRow);

  // Decide and mark first (inside the lock), send after (outside it).
  const toSend = claimDelayed(rows);
  toSend.forEach(shipmentId => {
    const accepted = sendNotice(shipmentId);
    // Option A: the mark only stays if the server took the notice. If not,
    // remove it, so setting "retrasado" again retries instead of staying silent.
    if (!accepted) {
      PropertiesService.getDocumentProperties().deleteProperty(NOTIFIED_PREFIX + shipmentId);
      console.warn(`${shipmentId}: notice not accepted, mark removed (edit again to retry).`);
    }
  });
}

/**
 * Applies the MEMORY rule to the edited rows and returns the shipments to
 * notify. Their mark is set HERE, before sending, so a second edit a moment
 * later already sees it. The lock stops two edits at almost the same time
 * from both deciding to notify. Sending happens outside the lock because the
 * retries can take longer than the lock wait.
 */
function claimDelayed(rows) {
  const lock = LockService.getDocumentLock();
  if (!lock.tryLock(LOCK_WAIT_MS)) {
    console.error('Could not get the lock: nothing sent. Edit the cell again.');
    return [];
  }
  try {
    const props = PropertiesService.getDocumentProperties();
    const toSend = [];
    rows.forEach(({ shipmentId, status }) => {
      if (!shipmentId) return;
      const key = NOTIFIED_PREFIX + shipmentId;
      if (status !== DELAYED) {
        props.deleteProperty(key);
        return;
      }
      if (props.getProperty(key)) return;  // already notified: nothing to do
      props.setProperty(key, new Date().toISOString());
      toSend.push(shipmentId);
    });
    return toSend;
  } finally {
    lock.releaseLock();
  }
}

/** Builds ONE notice and sends it, retrying with the SAME event_id.
 *  Returns true if the server accepted it (202) or already had it (200). */
function sendNotice(shipmentId) {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty('WEBHOOK_URL');
  const secret = props.getProperty('WEBHOOK_SECRET');
  if (!url || !secret) {
    console.error('Missing WEBHOOK_URL or WEBHOOK_SECRET in Script properties: nothing sent.');
    return false;
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
      return true;
    }
    if (code === 401 || code === 422) {
      // Our mistake (wrong secret, bad body): retrying won't fix it.
      console.error(`${shipmentId} ${eventId}: ${code}, not retried. ${body}`);
      return false;
    }
    // 503 (server can't check duplicates), other 5xx or no answer: may pass.
    console.warn(`${shipmentId} ${eventId}: attempt ${attempt} got ${code}. ${body}`);
    if (attempt < MAX_ATTEMPTS) Utilities.sleep(RETRY_WAIT_MS * attempt);
  }
  console.error(`${shipmentId} ${eventId}: gave up after ${MAX_ATTEMPTS} attempts.`);
  return false;
}

/**
 * Run by hand ONCE after installing (and again after scripts/seed_sheet.py):
 * rebuilds the memory from the Sheet as it is now. Shipments already
 * "retrasado" count as notified, so the first paste over them sends nothing.
 * It sends no notices.
 */
function initNotifiedState() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(TAB_SHIPMENTS);
  const cols = findColumns(sheet);
  if (!cols) return;
  const props = PropertiesService.getDocumentProperties();
  Object.keys(props.getProperties())
    .filter(key => key.startsWith(NOTIFIED_PREFIX))
    .forEach(key => props.deleteProperty(key));

  const lastRow = sheet.getLastRow();
  const rows = lastRow < 2 ? [] : readRows(sheet, cols, 2, lastRow);
  const now = new Date().toISOString();
  const marked = rows
    .filter(({ shipmentId, status }) => shipmentId && status === DELAYED)
    .map(({ shipmentId }) => shipmentId);
  marked.forEach(id => props.setProperty(NOTIFIED_PREFIX + id, now));
  console.log(`Memory rebuilt: ${marked.length} delayed shipment(s) marked as notified: ${marked.join(', ')}`);
}

/** Run by hand to see the memory: which shipments are marked as notified. */
function logNotifiedState() {
  const props = PropertiesService.getDocumentProperties().getProperties();
  const marks = Object.keys(props)
    .filter(key => key.startsWith(NOTIFIED_PREFIX))
    .sort()
    .map(key => `${key.slice(NOTIFIED_PREFIX.length)} (since ${props[key]})`);
  console.log(marks.length ? `Notified: ${marks.join(', ')}` : 'No shipment marked as notified.');
}

/** Run by hand to test the connection without editing the Sheet.
 *  It does not touch the memory. */
function sendTestNotice() {
  sendNotice('ENV-1001');
}

/** Finds the columns by their header name (row 1), never by position:
 *  moving a column in the Sheet must not break the script. 1-based. */
function findColumns(sheet) {
  const header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]
    .map(cell => String(cell).trim());
  const status = header.indexOf('status') + 1;   // 0 = not found
  const id = header.indexOf('shipment_id') + 1;
  if (!status || !id) {
    console.error(`Missing "status" or "shipment_id" header in ${TAB_SHIPMENTS}.`);
    return null;
  }
  return { status, id };
}

/** Reads shipment_id and status of rows firstRow..lastRow (one call per column). */
function readRows(sheet, cols, firstRow, lastRow) {
  const n = lastRow - firstRow + 1;
  const ids = sheet.getRange(firstRow, cols.id, n, 1).getValues();
  const statuses = sheet.getRange(firstRow, cols.status, n, 1).getValues();
  return ids.map((row, i) => ({
    shipmentId: String(row[0]).trim(),
    status: normalize(statuses[i][0]),
  }));
}

function normalize(value) {
  return String(value === undefined || value === null ? '' : value).trim().toLowerCase();
}
