"""Phase 3a: check the agent against the REAL Google Sheet.

Run from the project root:
    python -m scripts.fase3a_sheets smoke                 # no LLM: read + write one log row
    python -m scripts.fase3a_sheets agent                 # agent on ENV-1001, ENV-1004, ENV-1005
    python -m scripts.fase3a_sheets agent ENV-1002        # or only the cases you choose

This script always uses the Sheet, whatever DATA_SOURCE says in .env.
Every check READS BACK log_acciones from the Sheet: we trust what is in the
Sheet, not what Python says it wrote.
"""

import os
import sys
from datetime import datetime, timezone

# Must be set before importing app (load_dotenv never overrides it).
os.environ["DATA_SOURCE"] = "sheets"

from app import tools  # noqa: E402
from app.integrations import sheets  # noqa: E402

DEFAULT_CASES = ["ENV-1001", "ENV-1004", "ENV-1005"]


def now_iso() -> str:
    """Same format as the log timestamps, so strings compare in time order."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_rows_since(start: str) -> list[dict]:
    """Rows of log_acciones written from `start` on, read from the Sheet."""
    return [row for row in sheets.read_log() if row["timestamp"] >= start]


def smoke() -> None:
    """No LLM: read one shipment and its customer, write one log row."""
    start = now_iso()
    facts = tools.lookup_shipment("ENV-1001")
    if not facts["ok"]:
        sys.exit(f"[ERROR] {facts['error']}")
    shipment, customer = facts["shipment"], facts["customer"]
    print(f"Source: {tools.get_data_source().__name__}")
    print(f"Shipment: {shipment}")
    print(f"Customer: {customer}")
    delay = shipment["delay_hours"]
    print(f"delay_hours = {delay!r} -> type {type(delay).__name__} (must be int)")

    # Same path the agent uses: tools.record_action -> _append_log -> Sheet.
    result = tools.record_action(
        "ENV-1001", "no_action", "phase 3a smoke test (no LLM)",
        "written by scripts/fase3a_sheets.py",
    )
    print(f"record_action -> {result}")

    rows = log_rows_since(start)
    print(f"\nRead back from the Sheet: {len(rows)} new row(s)")
    for row in rows:
        print(f"  {row}")
    print("Result: OK" if result["ok"] and rows else "Result: CHECK")


def agent(cases: list[str]) -> None:
    """Run the phase 2 test bench against the Sheet, then read the log back."""
    from scripts import fase2_agent  # imported here: it loads the Gemini config

    start = now_iso()
    sys.argv = ["fase2_agent", *cases]  # fase2_agent reads the cases from argv
    fase2_agent.main()

    rows = log_rows_since(start)
    print(f"\n{'=' * 70}\nlog_acciones IN THE SHEET (written by this run)\n{'=' * 70}")
    for shipment_id in cases:
        actions = [row["action"] for row in rows if row["shipment_id"] == shipment_id]
        print(f"{shipment_id:<10} {len(actions)} row(s): {actions}")
    if not rows:
        print("No rows found: the log did NOT reach the Sheet. CHECK")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("smoke", "agent"):
        sys.exit("Usage: python -m scripts.fase3a_sheets smoke | agent [ENV-…]")
    try:
        if sys.argv[1] == "smoke":
            smoke()
        else:
            agent(sys.argv[2:] or DEFAULT_CASES)
    except sheets.SheetsError as error:
        sys.exit(f"[ERROR] {error}")


if __name__ == "__main__":
    main()
