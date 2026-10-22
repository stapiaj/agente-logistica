"""Google Sheets as the customer's system (phase 3a).

This module is the ADAPTER between the agent and the Sheet. It knows:
- HEADERS: the columns of each tab, in the order of
  docs/contexto/05-modelo-datos.md. This is the ONLY place in the code where
  the column names live (the seed script and the adapter both use it).
- How to connect: authenticate as the service account (the "robot") with its
  JSON key and open the spreadsheet by its ID.

Then the ADAPTER (T5): find_shipment, find_customer and append_log, with
the same names and the same shape of data as app/mock_data.py. The Sheet
returns TEXT; this module converts it (delay_hours -> number) so the agent
and rules.py receive exactly what they received from memory.

Errors: anything that stops us from reaching the Sheet is raised as
SheetsError with a message that explains the likely cause, so callers can
show it or turn it into data instead of crashing with a raw traceback.
"""

import math

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound

from app.config import load_sheets_config

# Least privilege also applies to the TOKEN: we only ask for access to
# spreadsheets, not to the whole Drive of the service account.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TAB_SHIPMENTS = "envios"
TAB_CUSTOMERS = "clientes"
TAB_LOG = "log_acciones"

HEADERS: dict[str, list[str]] = {
    TAB_SHIPMENTS: [
        "shipment_id",
        "customer_id",
        "origin",
        "destination",
        "carrier",
        "expected_date",
        "status",
        "delay_hours",
        "delay_reason",
        "new_eta",
    ],
    TAB_CUSTOMERS: [
        "customer_id",
        "name",
        "contact_email",
        "priority",
        "language",
    ],
    TAB_LOG: [
        "timestamp",
        "shipment_id",
        "action",
        "reason",
        "details",
    ],
}


class SheetsError(Exception):
    """The Sheet cannot be reached or does not have the expected shape."""


def open_spreadsheet() -> gspread.Spreadsheet:
    """Authenticate as the service account and open the Sheet from .env."""
    sheet_id, key_file = load_sheets_config()
    try:
        client = gspread.service_account(filename=key_file, scopes=SCOPES)
    except FileNotFoundError as ex:
        raise SheetsError(
            f"service account key file not found: {key_file!r} "
            "(check GOOGLE_SERVICE_ACCOUNT_FILE in .env)"
        ) from ex
    try:
        return client.open_by_key(sheet_id)
    except SpreadsheetNotFound as ex:
        raise SheetsError(
            "spreadsheet not found (404): check GOOGLE_SHEET_ID in .env"
        ) from ex
    except PermissionError as ex:
        raise SheetsError(
            "permission denied (403): share the spreadsheet with the service "
            "account email as Editor"
        ) from ex


def get_tabs(spreadsheet: gspread.Spreadsheet) -> dict[str, gspread.Worksheet]:
    """Return the 3 tabs by name. One API call for all of them."""
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}
    missing = [name for name in HEADERS if name not in tabs]
    if missing:
        raise SheetsError(
            f"missing tabs in the spreadsheet: {missing} "
            f"(found: {list(tabs)}); names must match exactly"
        )
    return {name: tabs[name] for name in HEADERS}


# ---------------------------------------------------------------------------
# Adapter (T5): same 3 functions and same shape of data as app/mock_data.py.
# The agent never knows which one it is talking to.
# ---------------------------------------------------------------------------

_tabs_cache: dict[str, gspread.Worksheet] = {}


def _tabs() -> dict[str, gspread.Worksheet]:
    """Open the Sheet ONCE per process and reuse it (saves API quota)."""
    if not _tabs_cache:
        _tabs_cache.update(get_tabs(open_spreadsheet()))
    return _tabs_cache


def _api_error(action: str, ex: APIError) -> SheetsError:
    """Turn a raw Google error into a SheetsError with the HTTP status."""
    status = ex.response.status_code
    hint = " (quota exceeded: wait a minute)" if status == 429 else ""
    return SheetsError(f"Sheets API error {status} while {action}{hint}")


def to_number(value):
    """Sheet text -> int or float. If it can't be converted, return it AS IS.

    The adapter TRANSLATES, it does not decide: a value like "treinta" or ""
    reaches rules.py unchanged, and rules.py flags it as inconsistent data
    (escalate, no email). The program never crashes on a bad cell.
    """
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        pass
    try:
        number = float(text.replace(",", "."))  # "4,5" (Spanish) or "4.5"
    except ValueError:
        return value
    return number if math.isfinite(number) else value  # "nan", "inf" are not hours


def _read_records(tab: str) -> list[dict]:
    """All rows of a tab as dicts (1 API call). Every value is TEXT here."""
    try:
        values = _tabs()[tab].get_all_values()
    except APIError as ex:
        raise _api_error(f"reading {tab}", ex) from ex
    rows = [row for row in values if any(row)]  # an empty tab comes as [[]]
    if not rows:
        return []
    headers = HEADERS[tab]
    found = [cell.strip() for cell in rows[0]][: len(headers)]
    if found != headers:
        raise SheetsError(f"unexpected header in {tab}: {found} (expected {headers})")
    records = []
    for row in rows[1:]:
        row = row + [""] * (len(headers) - len(row))  # short rows -> empty cells
        records.append({col: row[i].strip() for i, col in enumerate(headers)})
    return records


def _same_id(a: str, b: str) -> bool:
    """Ids typed by humans may have spaces or lowercase: compare normalized."""
    return a.strip().upper() == b.strip().upper()


def find_shipment(shipment_id: str) -> dict | None:
    """One row of `envios` as a dict (same shape as mock_data), or None."""
    for record in _read_records(TAB_SHIPMENTS):
        if _same_id(record["shipment_id"], shipment_id):
            record["delay_hours"] = to_number(record["delay_hours"])
            # Dates stay as text: rules.is_valid_eta checks them. A date typed
            # by hand may come back as 23/10/2026 -> invalid -> escalate.
            return record
    return None


def find_customer(customer_id: str) -> dict | None:
    """One row of `clientes` as a dict (same shape as mock_data), or None."""
    for record in _read_records(TAB_CUSTOMERS):
        if _same_id(record["customer_id"], customer_id):
            return record
    return None


def read_log() -> list[dict]:
    """All rows of `log_acciones` (to check what really reached the Sheet)."""
    return _read_records(TAB_LOG)


def append_log(row: dict) -> None:
    """Add one row at the end of `log_acciones` (1 API call), written RAW."""
    values = [str(row.get(col, "")) for col in HEADERS[TAB_LOG]]
    try:
        _tabs()[TAB_LOG].append_row(values)
    except APIError as ex:
        raise _api_error(f"writing to {TAB_LOG}", ex) from ex
