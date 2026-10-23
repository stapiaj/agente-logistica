"""Phase 2 (+2b): run the 7 test cases through the agent + guardrail.

Run from the project root:
    python -m scripts.fase2_agent                      (all 7 cases)
    python -m scripts.fase2_agent ENV-1003 ENV-1004    (only these, saves quota)

The EXPECTED table is copied by hand from docs/contexto/05-modelo-datos.md
on purpose (not computed with rules.py): this way the script also checks
that rules.py agrees with the documented behaviour.
"""

import sys
import time

from google import genai

from app import tools
from app.agent import describe_failed_calls, handle_shipment
from app.tools import is_judgment
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
    "ENV-1006": (False, True, {"escalated"}),  # goods stolen: judgment (rule 6)
}

# Cases where the agent must escalate BY JUDGMENT (alert starting with
# "JUDGMENT:" and an email draft). In every other case JUDGMENT must NOT
# appear: that catches the agent using judgment to skip normal emails.
JUDGMENT_CASES = {"ENV-1006"}


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
        judged = any(is_judgment(n["message"]) and n["email_draft"].strip()
                     for n in tools.HUMAN_NOTIFICATIONS)

        exp_email, exp_escalate, exp_logs = EXPECTED[shipment_id]
        exp_judged = shipment_id in JUDGMENT_CASES
        matches = (emailed == exp_email and escalated == exp_escalate
                   and exp_logs <= logged and judged == exp_judged)
        if not matches:
            verdict = "CHECK"
        elif guard.intervened:
            verdict = "OK (guardrail)"
        else:
            verdict = "OK"

        print(f"\nModel: {run.model_used} | rounds: {run.iterations} "
              f"| limit hit: {run.hit_iteration_limit}")
        print("Tools used: " + " -> ".join(call.name for call in run.tool_calls))
        for line in describe_failed_calls(run):  # arguments + error of each failure
            print(line)
        print(f"Guardrail intervened: {guard.intervened}")
        for item in guard.corrections:
            print(f"  correction: {item}")
        for item in guard.discrepancies:
            print(f"  discrepancy: {item}")
        print(f"Email: {yes_no(emailed)} (expected {yes_no(exp_email)}) | "
              f"Escalated: {yes_no(escalated)} (expected {yes_no(exp_escalate)}) | "
              f"Log: {sorted(logged)} (must include {sorted(exp_logs)}) | "
              f"Judgment+draft: {yes_no(judged)} (expected {yes_no(exp_judged)})")
        print(f"Result: {verdict}")
        summary.append((shipment_id, yes_no(emailed), yes_no(escalated),
                        "yes" if guard.intervened else "no", verdict))

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    print(f"{'Shipment':<10} {'Email':<6} {'Escal.':<7} {'Guardrail':<10} Result")
    for row in summary:
        print(f"{row[0]:<10} {row[1]:<6} {row[2]:<7} {row[3]:<10} {row[4]}")


if __name__ == "__main__":
    main()
