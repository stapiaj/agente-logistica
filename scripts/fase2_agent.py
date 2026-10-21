"""Phase 2: run the 6 test cases through the agent + guardrail.

Run from the project root:
    python -m scripts.fase2_agent                      (all 6 cases)
    python -m scripts.fase2_agent ENV-1003 ENV-1004    (only these, saves quota)

The EXPECTED table is copied by hand from docs/contexto/05-modelo-datos.md
on purpose (not computed with rules.py): this way the script also checks
that rules.py agrees with the documented behaviour.
"""

import sys
import time

from google import genai

from app import tools
from app.agent import handle_shipment
from app.config import load_config

# Free tier limits requests per minute: wait between cases to avoid a 429.
PAUSE_SECONDS = 5

# shipment_id -> (email to customer?, human escalated?, log actions that must appear)
EXPECTED = {
    "ENV-1001": (True, False, {"email_sent"}),  # 6 h, normal customer
    "ENV-1002": (True, True, {"email_sent", "escalated"}),  # 30 h > 24
    "ENV-1003": (True, True, {"email_sent", "escalated"}),  # priority alta
    "ENV-1004": (False, True, {"escalated"}),  # customer without email
    "ENV-9999": (False, False, {"error"}),  # shipment does not exist
    "ENV-1005": (False, False, {"no_action"}),  # in transit, not delayed
}


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def main() -> None:
    # Optional: pass shipment ids to run only those cases.
    selected = sys.argv[1:] or list(EXPECTED)
    unknown = [sid for sid in selected if sid not in EXPECTED]
    if unknown:
        sys.exit(f"Unknown test case(s): {unknown}. Valid: {list(EXPECTED)}")

    api_key, model = load_config()
    client = genai.Client(api_key=api_key)  # one client for all cases
    summary = []

    for index, shipment_id in enumerate(selected):
        if index > 0:
            time.sleep(PAUSE_SECONDS)
        print(f"\n{'=' * 70}\n{shipment_id}\n{'=' * 70}")

        try:
            run, guard = handle_shipment(shipment_id, client=client, model=model)
        except Exception as error:  # e.g. 503 on both models: report and go on
            print(f"ERROR: {type(error).__name__}: {error}")
            summary.append((shipment_id, "-", "-", "-", "ERROR"))
            continue

        # What really happened (after the guardrail), read from the outbox.
        emailed = bool(tools.SENT_EMAILS)
        escalated = bool(tools.HUMAN_NOTIFICATIONS)
        logged = {row["action"] for row in tools.ACTION_LOG}

        exp_email, exp_escalate, exp_logs = EXPECTED[shipment_id]
        matches = emailed == exp_email and escalated == exp_escalate and exp_logs <= logged
        if not matches:
            verdict = "CHECK"
        elif guard.intervened:
            verdict = "OK (guardrail)"
        else:
            verdict = "OK"

        print(f"\nModel: {run.model_used} | rounds: {run.iterations} "
              f"| limit hit: {run.hit_iteration_limit}")
        print("Tools used: " + " -> ".join(call.name for call in run.tool_calls))
        print(f"Guardrail intervened: {guard.intervened}")
        for item in guard.corrections:
            print(f"  correction: {item}")
        for item in guard.discrepancies:
            print(f"  discrepancy: {item}")
        print(f"Email: {yes_no(emailed)} (expected {yes_no(exp_email)}) | "
              f"Escalated: {yes_no(escalated)} (expected {yes_no(exp_escalate)}) | "
              f"Log: {sorted(logged)} (must include {sorted(exp_logs)})")
        print(f"Result: {verdict}")
        summary.append((shipment_id, yes_no(emailed), yes_no(escalated),
                        "yes" if guard.intervened else "no", verdict))

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    print(f"{'Shipment':<10} {'Email':<6} {'Escal.':<7} {'Guardrail':<10} Result")
    for row in summary:
        print(f"{row[0]:<10} {row[1]:<6} {row[2]:<7} {row[3]:<10} {row[4]}")


if __name__ == "__main__":
    main()
