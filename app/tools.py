"""The agent's 4 tools, working against in-memory data (phase 2).

Contract from docs/contexto/05-modelo-datos.md. Two key ideas:
- The DOCSTRING of each tool is what the model reads to decide when to use it.
  The model never sees the code, only the name, the parameters and this text.
- Tools never raise on bad input: they return {"ok": False, "error": ...} so
  the model can read the problem and react, instead of the program crashing.

Nothing is really sent in this phase: emails, alerts and log rows are stored
in the "outbox" lists below and printed. The guardrail reads them afterwards.
"""

from datetime import datetime, timezone

from app.mock_data import CUSTOMERS, SHIPMENTS

VALID_ACTIONS = {"email_sent", "escalated", "no_action", "error"}

# Outbox: everything the agent did during one run.
SENT_EMAILS: list[dict] = []
HUMAN_NOTIFICATIONS: list[dict] = []
ACTION_LOG: list[dict] = []


def reset_outbox() -> None:
    """Empty the outbox between test cases."""
    SENT_EMAILS.clear()
    HUMAN_NOTIFICATIONS.clear()
    ACTION_LOG.clear()


def get_shipment(shipment_id: str) -> dict:
    """Look up a shipment and its customer. Read only, no side effects.

    Always call this FIRST, before any other tool, to get the facts.
    Returns the shipment (status, delay_hours, delay_reason, expected_date,
    route, carrier) and its customer (name, contact_email, priority, language).
    If the shipment does not exist it returns ok=false with an error.
    If the customer does not exist, customer is null.
    """
    shipment = SHIPMENTS.get(shipment_id)
    if shipment is None:
        return {"ok": False, "error": f"shipment {shipment_id} not found"}
    customer = CUSTOMERS.get(shipment["customer_id"])
    # Return copies so the model's data can't modify our "database".
    return {
        "ok": True,
        "shipment": dict(shipment),
        "customer": dict(customer) if customer else None,
    }


def send_customer_email(to: str, subject: str, body: str) -> dict:
    """Send an email to the customer about their delayed shipment.

    Use it only for shipments with status "retrasado" whose customer has a
    contact_email. Do NOT use it if the email is missing or the customer does
    not exist: escalate instead. `to` must be the customer's contact_email.
    Write subject and body in the customer's language, greeting the customer
    by name, with line breaks between paragraphs.
    """
    if not to or "@" not in to:
        return {"ok": False, "error": f"invalid recipient: {to!r}"}
    if not subject or not body:
        return {"ok": False, "error": "subject and body are required"}
    email = {"to": to, "subject": subject, "body": body}
    SENT_EMAILS.append(email)
    print(f"\n[EMAIL -> {to}]\nSubject: {subject}\n{body}\n")
    return {"ok": True, "status": "sent (simulated)"}


def notify_human(message: str) -> dict:
    """Alert the human supervisor so they take over the case.

    Use it when ANY escalation rule applies: delay_hours > 24, customer
    priority "alta", or missing/inconsistent data. The message must include
    the shipment_id and a clear reason for escalating.
    """
    if not message or not message.strip():
        return {"ok": False, "error": "message is required"}
    HUMAN_NOTIFICATIONS.append({"message": message})
    print(f"[HUMAN ALERT] {message}")
    return {"ok": True, "status": "notified (simulated)"}


def log_action(shipment_id: str, action: str, reason: str, details: str) -> dict:
    """Record an action in the audit log. Call it once per action you take.

    action must be one of: "email_sent", "escalated", "no_action", "error".
    reason explains WHY you decided it; details adds any useful context.
    Use "no_action" when the shipment is not delayed and "error" when the
    shipment does not exist.
    """
    if action not in VALID_ACTIONS:
        return {
            "ok": False,
            "error": f"invalid action {action!r}, use one of {sorted(VALID_ACTIONS)}",
        }
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shipment_id": shipment_id,
        "action": action,
        "reason": reason,
        "details": details,
    }
    ACTION_LOG.append(row)
    print(f"[LOG] {shipment_id} | {action} | {reason}")
    return {"ok": True}


# Name -> function: the agent loop uses it to run the tool the model asks for.
TOOLS = {
    "get_shipment": get_shipment,
    "send_customer_email": send_customer_email,
    "notify_human": notify_human,
    "log_action": log_action,
}
