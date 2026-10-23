"""Phase 3b: REAL email (Resend) and REAL alerts (Telegram), data from the Sheet.

Run from the project root:
    python -m scripts.fase3b_real smoke              # no LLM: real email + real alert + a refusal
    python -m scripts.fase3b_real agent              # agent on ENV-1001, ENV-1002, ENV-1006
    python -m scripts.fase3b_real agent ENV-1002     # or only the cases you choose

This script ALWAYS uses the real channels and the Sheet, whatever .env says,
so you never forget to switch a mode. Test mode still protects: every email
goes to EMAIL_TEST_RECIPIENT, and without it the program stops (fail closed).
Then check your inbox and your Telegram against the table printed at the end.
"""

import os
import sys

# Must be set before importing app (load_dotenv never overrides them).
os.environ["DATA_SOURCE"] = "sheets"
os.environ["EMAIL_MODE"] = "resend"
os.environ["NOTIFY_MODE"] = "telegram"

from app import tools  # noqa: E402
from app.config import load_resend_config  # noqa: E402
from app.integrations import sheets  # noqa: E402

DEFAULT_CASES = ["ENV-1001", "ENV-1002", "ENV-1006"]

# What must reach you for each case: (emails in your inbox, Telegram alerts, note)
EXPECTED_DELIVERIES = {
    "ENV-1001": (1, 0, "email only (6 h, normal customer)"),
    "ENV-1002": (1, 1, "email + alert with 'delay_hours 30 > 24'"),
    "ENV-1006": (0, 1, "NO email; alert 'JUDGMENT:' + email draft, rules 'none: no rule...'"),
}


def smoke() -> None:
    """No LLM: the same tools the agent uses, with the real providers."""
    load_resend_config()  # stops here if test mode is not configured (fail closed)
    tools.reset_outbox()
    results = []

    print("1. send_customer_email for ENV-1001 (rules allow it) -> real email")
    result = tools.make_tools("ENV-1001")["send_customer_email"](
        "Prueba de envío real (fase 3b)",
        "Hola,\n\nEste email lo envía la herramienta del agente, sin LLM.\n",
    )
    print(f"   -> {result}")
    results.append(result.get("ok") is True)

    print("\n2. notify_human for ENV-1002 -> real Telegram alert")
    result = tools.make_tools("ENV-1002")["notify_human"](
        "[SMOKE TEST] Phase 3b check, no LLM. The rules block above is written by code.",
    )
    print(f"   -> {result}")
    results.append(result.get("ok") is True)

    print("\n3. send_customer_email for ENV-1004 (no contact email) -> must be REFUSED")
    emails_before = len(tools.SENT_EMAILS)
    result = tools.make_tools("ENV-1004")["send_customer_email"]("Should not leave", "Body")
    print(f"   -> {result}")
    results.append(bool(result.get("refused_by_rules")) and len(tools.SENT_EMAILS) == emails_before)

    print("\nExpected: 1 email in your inbox ([TEST], original recipient of ENV-1001) "
          "and 1 Telegram message (ENV-1002). Nothing for ENV-1004.")
    print("Result: OK" if all(results) else f"Result: CHECK {results}")


def agent(cases: list[str]) -> None:
    """The agent on real channels; reuses the phase 3a runner (reads the log back)."""
    from scripts import fase3a_sheets  # imported here: same Sheet, log read back

    load_resend_config()  # fail closed before spending any quota
    fase3a_sheets.agent(cases)

    print(f"\n{'=' * 70}\nWHAT MUST HAVE REACHED YOU (check inbox and Telegram)\n{'=' * 70}")
    print(f"{'Shipment':<10} {'Emails':<7} {'Alerts':<7} What to look for")
    for shipment_id in cases:
        emails, alerts, note = EXPECTED_DELIVERIES.get(shipment_id, ("?", "?", "not a phase 3b case"))
        print(f"{shipment_id:<10} {emails!s:<7} {alerts!s:<7} {note}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("smoke", "agent"):
        sys.exit("Usage: python -m scripts.fase3b_real smoke | agent [ENV-…]")
    try:
        if sys.argv[1] == "smoke":
            smoke()
        else:
            agent(sys.argv[2:] or DEFAULT_CASES)
    except sheets.SheetsError as error:
        sys.exit(f"[ERROR] {error}")


if __name__ == "__main__":
    main()
