"""The agent's 4 tools, working against in-memory data (phase 2).

Contract from docs/contexto/05-modelo-datos.md. Three key ideas:
- The DOCSTRING of each tool is what the model reads to decide when to use it.
  The model never sees the code, only the name, the parameters and this text.
- Tools never raise on bad input: they return {"ok": False, "error": ...} so
  the model can read the problem and react, instead of the program crashing.
- The model never writes the shipment_id. Each run handles ONE shipment, so
  make_tools(shipment_id) builds tools that already carry it inside. The model
  cannot change a value it does not write.

Two layers in this file:
- Implementations (lookup_shipment, deliver_email, deliver_alert,
  record_action): plain code that receives shipment_id explicitly. The
  guardrail uses them directly.
- Tools for the model (make_tools): thin wrappers bound to one shipment.

Nothing is really sent in this phase: emails, alerts and log rows are stored
in the "outbox" lists below and printed. The guardrail reads them afterwards.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from app.mock_data import CUSTOMERS, SHIPMENTS

# Actions the AGENT may log (what happened to the shipment).
VALID_ACTIONS = {"email_sent", "escalated", "no_action", "error"}
# Action reserved for the guardrail (an observation about the agent).
# Not offered to the model: the agent must not be able to flag itself.
GUARDRAIL_ACTION = "guardrail"

# Outbox: everything the agent did during one run.
SENT_EMAILS: list[dict] = []
HUMAN_NOTIFICATIONS: list[dict] = []
ACTION_LOG: list[dict] = []


def reset_outbox() -> None:
    """Empty the outbox between test cases."""
    SENT_EMAILS.clear()
    HUMAN_NOTIFICATIONS.clear()
    ACTION_LOG.clear()


# ---------------------------------------------------------------------------
# Implementations: used by the tools below AND by the guardrail.
# ---------------------------------------------------------------------------


def lookup_shipment(shipment_id: str) -> dict:
    """Shipment + customer, or ok=False if the shipment does not exist."""
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


def deliver_email(to: str, subject: str, body: str) -> dict:
    """Send (simulate) one email. Validates the input, never raises on it."""
    if not to or "@" not in to:
        return {"ok": False, "error": f"invalid recipient: {to!r}"}
    if not subject or not body:
        return {"ok": False, "error": "subject and body are required"}
    email = {"to": to, "subject": subject, "body": body}
    SENT_EMAILS.append(email)
    print(f"\n[EMAIL -> {to}]\nSubject: {subject}\n{body}\n")
    return {"ok": True, "status": "sent (simulated)"}


def deliver_alert(shipment_id: str, message: str) -> dict:
    """Alert the human. The shipment_id is attached by code, not by the model."""
    if not message or not message.strip():
        return {"ok": False, "error": "message is required"}
    HUMAN_NOTIFICATIONS.append({"shipment_id": shipment_id, "message": message})
    print(f"[HUMAN ALERT] {shipment_id} | {message}")
    return {"ok": True, "status": "notified (simulated)"}


def record_action(shipment_id: str, action: str, reason: str, details: str) -> dict:
    """Write one audit row with a controlled vocabulary for `action`."""
    if action not in VALID_ACTIONS:
        return {
            "ok": False,
            "error": f"invalid action {action!r}, use one of {sorted(VALID_ACTIONS)}",
        }
    _append_log(shipment_id, action, reason, details)
    return {"ok": True}


def record_guardrail(shipment_id: str, reason: str, details: str = "") -> None:
    """Log a guardrail discrepancy. Code only: the model has no tool for it."""
    _append_log(shipment_id, GUARDRAIL_ACTION, reason, details)


def _append_log(shipment_id: str, action: str, reason: str, details: str) -> None:
    """Write one row to the audit log (shared by the agent and the guardrail)."""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shipment_id": shipment_id,
        "action": action,
        "reason": reason,
        "details": details,
    }
    ACTION_LOG.append(row)
    print(f"[LOG] {shipment_id} | {action} | {reason}")


# ---------------------------------------------------------------------------
# Tools for the model, bound to ONE shipment.
# ---------------------------------------------------------------------------


def make_tools(shipment_id: str) -> dict[str, Callable[..., dict]]:
    """Build the 4 tools for one run, with shipment_id already inside.

    Each inner function "remembers" the shipment_id it was created with
    (a closure). A new run creates new tools, so two shipments handled at
    the same time (phase 4, FastAPI) can never mix their ids.
    """

    def get_shipment() -> dict:
        """Look up the shipment of this event and its customer. Read only.

        Always call this FIRST, before any other tool, to get the facts.
        Returns the shipment (status, delay_hours, delay_reason, expected_date,
        route, carrier) and its customer (name, contact_email, priority, language).
        If the shipment does not exist it returns ok=false with an error.
        If the customer does not exist, customer is null.
        """
        return lookup_shipment(shipment_id)

    def send_customer_email(to: str, subject: str, body: str) -> dict:
        """Send an email to the customer about their delayed shipment.

        Use it only for shipments with status "retrasado" whose customer has a
        contact_email. Do NOT use it if the email is missing or the customer does
        not exist: escalate instead. `to` must be the customer's contact_email.
        Write subject and body in the customer's language, greeting the customer
        by name, with line breaks between paragraphs.
        """
        return deliver_email(to, subject, body)

    def notify_human(message: str) -> dict:
        """Alert the human supervisor so they take over the case.

        Use it when ANY escalation rule applies: delay_hours > 24, customer
        priority "alta", or missing/inconsistent data. The message must include
        the customer name and a clear reason for escalating. The shipment_id is
        attached automatically.
        """
        return deliver_alert(shipment_id, message)

    def log_action(action: str, reason: str, details: str) -> dict:
        """Record an action in the audit log. Call it once per action you take.

        action must be one of: "email_sent", "escalated", "no_action", "error".
        reason explains WHY you decided it; details adds any useful context.
        Use "no_action" when the shipment is not delayed and "error" when the
        shipment does not exist. The shipment_id is attached automatically.
        """
        return record_action(shipment_id, action, reason, details)

    # Name -> function: the agent loop runs the tool the model asks for by name.
    return {
        tool.__name__: tool
        for tool in (get_shipment, send_customer_email, notify_human, log_action)
    }
