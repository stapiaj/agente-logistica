"""Phase 2 closing: break things on purpose and see how the system reacts.

Run from the project root:
    python -m scripts.fase2_breaks bad-id        # malformed shipment_id
    python -m scripts.fase2_breaks tool-crash    # email tool raises an exception
    python -m scripts.fase2_breaks vague-tool    # ambiguous notify_human description
    python -m scripts.fase2_breaks vague-reason  # (2b) ambiguous delay_reason: judgment or not?
    python -m scripts.fase2_breaks bad-eta       # (2b) new_eta with an invalid format

Every break is done IN MEMORY: no file of the project is changed.
"""

import os
import sys

# These breaks modify the IN-MEMORY data (SHIPMENTS), so they always run on
# the memory source, whatever DATA_SOURCE says in .env. Must be set before
# importing app (load_dotenv never overrides a variable that already exists).
os.environ["DATA_SOURCE"] = "memory"

from app import agent, tools  # noqa: E402
from app.mock_data import SHIPMENTS  # noqa: E402
from app.agent import handle_shipment  # noqa: E402


def break_bad_id() -> str:
    """Malformed id, as it could arrive from a webhook.

    Since phase 2b the model never writes the id: handle_shipment normalises
    it and the tools carry it inside, so the model can't rewrite it.
    """
    return "env-1001 "


def break_tool_crash() -> str:
    """The email provider is down: the tool raises instead of returning."""

    def broken_email(to: str, subject: str, body: str) -> dict:
        raise ConnectionError("email provider unreachable")

    # The model's send_customer_email calls tools.deliver_email by name at run
    # time, so replacing the implementation breaks the tool.
    tools.deliver_email = broken_email
    return "ENV-1001"


def break_vague_tool() -> str:
    """notify_human gets a vague description (the SDK reads __doc__)."""
    vague = "Sends a message. Use it to notify about the shipment."
    original_make_tools = agent.make_tools

    def make_vague_tools(shipment_id: str) -> dict:
        built = original_make_tools(shipment_id)
        built["notify_human"].__doc__ = vague
        return built

    agent.make_tools = make_vague_tools  # run_agent looks it up at run time
    print(f"Description the model sees for notify_human:\n    {vague}\n")
    return "ENV-1002"


def break_vague_reason() -> str:
    """(2b) A reason that MIGHT be serious: no right answer is written down.

    We look at HOW it decides: judgment (JUDGMENT: + draft, no email) or a
    normal delay (email), and whether its explanation makes sense.
    """
    SHIPMENTS["ENV-1001"]["delay_reason"] = "Incidencia en ruta"
    print("ENV-1001 delay_reason (in memory): 'Incidencia en ruta'\n")
    return "ENV-1001"


def break_bad_eta() -> str:
    """(2b) new_eta not in YYYY-MM-DD: inconsistent data (rule 3c).

    Expected: no email, escalation. If the agent emails anyway or doesn't
    escalate, the guardrail must catch it (rules.py validates the format).
    """
    SHIPMENTS["ENV-1001"]["new_eta"] = "23/10/2026"
    print("ENV-1001 new_eta (in memory): '23/10/2026'\n")
    return "ENV-1001"


BREAKS = {
    "bad-id": break_bad_id,
    "tool-crash": break_tool_crash,
    "vague-tool": break_vague_tool,
    "vague-reason": break_vague_reason,
    "bad-eta": break_bad_eta,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in BREAKS:
        sys.exit(f"Usage: python -m scripts.fase2_breaks <{' | '.join(BREAKS)}>")

    shipment_id = BREAKS[sys.argv[1]]()
    run, guard = handle_shipment(shipment_id)

    print(f"\nModel: {run.model_used} | rounds: {run.iterations} | limit hit: {run.hit_iteration_limit}")
    for i, call in enumerate(run.tool_calls, 1):
        print(f"{i}. {call.name}({call.args}) -> ok={call.result.get('ok')} {call.result.get('error', '')}")
    print(f"Guardrail intervened: {guard.intervened}")
    for item in guard.corrections:
        print(f"  correction: {item}")
    for item in guard.discrepancies:
        print(f"  discrepancy: {item}")


if __name__ == "__main__":
    main()
