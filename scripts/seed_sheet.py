"""Fill the Google Sheet with the same test cases as app/mock_data.py.

DEVELOPMENT TOOL, not part of the product: it ERASES the `envios` and
`clientes` tabs. Use it on the test/demo Sheet, never on a real customer's.

- `envios` and `clientes`: cleared and rewritten (header + rows) from
  app/mock_data.py, so the Sheet can always be rebuilt with known data.
- `log_acciones`: the header is written only if the tab is empty. Existing
  rows are history and are kept, unless you pass --reset-log.

Values are written RAW (as they are): dates stay as text like 2026-10-23.
With USER_ENTERED, Sheets would turn them into real dates and show them in
the locale format (23/10/2026), which the agent would see as an invalid ETA.

Few API calls on purpose (one per action per tab, never one per cell): the
Sheets API has a per-minute quota.

Run from the project root:
    python -m scripts.seed_sheet
    python -m scripts.seed_sheet --reset-log
"""

import argparse
import sys

from app.integrations.sheets import (
    HEADERS,
    TAB_CUSTOMERS,
    TAB_LOG,
    TAB_SHIPMENTS,
    SheetsError,
    get_tabs,
    open_spreadsheet,
)
from app.mock_data import CUSTOMERS, SHIPMENTS


def to_rows(records: dict[str, dict], headers: list[str]) -> list[list]:
    """Header + one row per record, columns in the order of `headers`."""
    rows: list[list] = [headers]
    for key, record in records.items():
        # Guard: mock_data and HEADERS must have exactly the same columns.
        if set(record) != set(headers):
            sys.exit(
                f"[ERROR] {key}: columns do not match the Sheet header.\n"
                f"  extra:   {sorted(set(record) - set(headers))}\n"
                f"  missing: {sorted(set(headers) - set(record))}"
            )
        rows.append([record[col] for col in headers])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Google Sheet.")
    parser.add_argument(
        "--reset-log",
        action="store_true",
        help="also erase log_acciones (history) and leave only its header",
    )
    args = parser.parse_args()

    try:
        spreadsheet = open_spreadsheet()
        tabs = get_tabs(spreadsheet)
    except SheetsError as ex:
        sys.exit(f"[ERROR] {ex}")
    print(f"Connected to: {spreadsheet.title}")

    for tab, records in ((TAB_SHIPMENTS, SHIPMENTS), (TAB_CUSTOMERS, CUSTOMERS)):
        rows = to_rows(records, HEADERS[tab])
        tabs[tab].clear()
        tabs[tab].update(rows, "A1")  # raw=True by default: values as they are
        print(f"  {tab}: header + {len(rows) - 1} rows written")

    log = tabs[TAB_LOG]
    # An empty tab comes back as [[]] (one empty row), not []: keep only
    # rows that have at least one non-empty cell.
    existing = [row for row in log.get_all_values() if any(row)]
    if args.reset_log or not existing:
        log.clear()
        log.update([HEADERS[TAB_LOG]], "A1")
        print(f"  {TAB_LOG}: header written (log is empty)")
    elif existing[0] != HEADERS[TAB_LOG]:
        sys.exit(
            f"[ERROR] {TAB_LOG} has rows but an unexpected header: {existing[0]}\n"
            "  Fix it by hand or run with --reset-log (erases the history)."
        )
    else:
        print(f"  {TAB_LOG}: kept ({len(existing) - 1} existing rows)")

    print("Done.")


if __name__ == "__main__":
    main()
