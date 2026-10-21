"""Business rules in code: the single source of truth for what SHOULD happen.

Pure function, no LLM and no side effects: given a shipment and its customer,
it returns the expected outcome. The guardrail compares the agent's actions
against this. Rules: docs/contexto/05-modelo-datos.md.
"""

from dataclasses import dataclass, field

# Thresholds with a name: if the business changes them, change one line.
DELAY_THRESHOLD_HOURS = 24
HIGH_PRIORITY = "alta"
DELAYED_STATUS = "retrasado"


@dataclass
class Expected:
    """What the agent should do for one shipment."""

    action_required: bool  # shipment exists and is delayed
    send_email: bool  # we can and must email the customer
    escalate: bool  # a human must be notified
    reasons: list[str] = field(default_factory=list)  # why it escalates


def evaluate(shipment: dict | None, customer: dict | None) -> Expected:
    """Apply the business rules to one shipment and its customer."""
    # Shipment not found (e.g. ENV-9999): only an error log, no external actions.
    if shipment is None:
        return Expected(action_required=False, send_email=False, escalate=False)

    # Rule 1: only act on delayed shipments (e.g. ENV-1005 -> no_action).
    if shipment.get("status") != DELAYED_STATUS:
        return Expected(action_required=False, send_email=False, escalate=False)

    reasons: list[str] = []

    # Rule 3c: missing or inconsistent data -> escalate and do NOT email.
    data_ok = True
    if customer is None:
        reasons.append(f"customer {shipment.get('customer_id')} not found")
        data_ok = False
    elif not customer.get("contact_email"):
        reasons.append(f"customer {customer['customer_id']} has no contact email")
        data_ok = False

    # Rule 3a: long delay.
    delay = shipment.get("delay_hours")
    if not isinstance(delay, (int, float)) or delay < 0:
        reasons.append(f"invalid delay_hours: {delay!r}")
        data_ok = False
    elif delay > DELAY_THRESHOLD_HOURS:
        reasons.append(f"delay_hours {delay} > {DELAY_THRESHOLD_HOURS}")

    # Rule 3b: high priority customer.
    if customer is not None and customer.get("priority") == HIGH_PRIORITY:
        reasons.append(f"customer priority is '{HIGH_PRIORITY}'")

    return Expected(
        action_required=True,
        send_email=data_ok,  # Rule 2: always email... unless data is incomplete
        escalate=bool(reasons),
        reasons=reasons,
    )
