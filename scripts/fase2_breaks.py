"""Phase 2 closing: break things on purpose and see how the system reacts.

Run from the project root:
    python -m scripts.fase2_breaks bad-id        # malformed shipment_id
    python -m scripts.fase2_breaks tool-crash    # email tool raises an exception
    python -m scripts.fase2_breaks vague-tool    # ambiguous notify_human description

Every break is done IN MEMORY: no file of the project is changed.
"""

import sys

from app import agent, tools
from app.agent import handle_shipment


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


BREAKS = {
    "bad-id": break_bad_id,
    "tool-crash": break_tool_crash,
    "vague-tool": break_vague_tool,
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
