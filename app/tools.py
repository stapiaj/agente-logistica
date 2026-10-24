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

Emails go out simulated or for real (EMAIL_MODE, phase 3b). Either way,
what really happened is stored in the "outbox" lists below and printed:
the guardrail reads them afterwards.
"""

from collections.abc import Callable
from datetime import datetime, timezone

from app.config import load_email_mode, load_notify_mode
from app.data_source import get_data_source
from app.rules import evaluate

# Actions the AGENT may log (what happened to the shipment).
VALID_ACTIONS = {"email_sent", "escalated", "no_action", "error"}
# Action reserved for the guardrail (an observation about the agent).
# Not offered to the model: the agent must not be able to flag itself.
GUARDRAIL_ACTION = "guardrail"
# A human alert starting with this is an escalation by judgment (rule 6).
JUDGMENT_PREFIX = "JUDGMENT:"

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
    """Shipment + customer, or ok=False if the shipment does not exist.

    Reads from the source chosen in .env (DATA_SOURCE): memory or the Sheet.
    The adapters already return copies, with the same shape of data.
    If the source can't be reached (e.g. the Sheet is not shared) this
    RAISES: inside the agent loop, execute_tool turns it into a "technical"
    error for the model; the guardrail catches it on its own.
    """
    source = get_data_source()
    shipment = source.find_shipment(shipment_id)
    if shipment is None:
        return {"ok": False, "error": f"shipment {shipment_id} not found"}
    customer = source.find_customer(shipment["customer_id"])
    return {"ok": True, "shipment": shipment, "customer": customer}


def email_idempotency_key(event_id: str) -> str:
    """One webhook notice -> at most one email. "" (no key) without a notice."""
    return f"shipment-delayed/{event_id}" if event_id else ""


def deliver_email(to: str, subject: str, body: str, idempotency_key: str = "") -> dict:
    """Send one email, simulated or real (EMAIL_MODE in .env).

    Bad input -> ok=False (never raises on it). If the real provider fails it
    RAISES: execute_tool turns that into a "technical" error. The email only
    goes to SENT_EMAILS once it was really accepted.
    idempotency_key (phase 4): sent to Resend so the same key never sends
    the email twice; "" when there is no webhook notice (scripts).
    """
    if not to or "@" not in to:
        return {"ok": False, "error": f"invalid recipient: {to!r}"}
    if not subject or not body:
        return {"ok": False, "error": "subject and body are required"}
    if load_email_mode() == "resend":
        # Imported only when needed: simulated mode works without Resend.
        from app.integrations import email as email_provider

        message_id = email_provider.send_email(to, subject, body, idempotency_key)
        status = f"sent via Resend (id {message_id})"
    else:
        status = "sent (simulated)"
    if idempotency_key:
        status += f", idempotency key {idempotency_key}"
    SENT_EMAILS.append({"to": to, "subject": subject, "body": body})
    print(f"\n[EMAIL -> {to}] {status}\nSubject: {subject}\n{body}\n")
    return {"ok": True, "status": status}


def deliver_alert(shipment_id: str, message: str, email_draft: str = "",
                  author: str = "agent") -> dict:
    """Alert the human. The shipment_id is attached by code, not by the model.

    email_draft: an email the agent did NOT send, for the human to review
    (human-in-the-loop on judgment escalations).
    """
    if not message or not message.strip():
        return {"ok": False, "error": "message is required"}
    text = format_alert(shipment_id, message, email_draft, rule_lines(shipment_id), author)
    if load_notify_mode() == "telegram":
        # Imported only when needed. If Telegram fails this RAISES ->
        # "technical" in the loop; the guardrail protects its own call.
        from app.integrations import telegram

        parts = telegram.send_message(text)
        status = f"sent via Telegram ({parts} message(s))"
    else:
        status = "notified (simulated)"
    # Only counts as delivered once the channel accepted it.
    HUMAN_NOTIFICATIONS.append(
        {"shipment_id": shipment_id, "message": message, "email_draft": email_draft or ""}
    )
    print(f"\n[HUMAN ALERT] {status}\n{text}\n")
    return {"ok": True, "status": status}


def rule_lines(shipment_id: str) -> list[str]:
    """Why the rules escalate this shipment, computed by CODE (rules.py).

    Added to every alert so the human never depends only on the model's
    explanation (in phase 3a it wrote "delay_hours seis > 24", a misleading
    reason). Never raises: if the data can't be read, the alert still goes
    out and says so. An alert is never blocked for lack of decoration.
    """
    try:
        facts = lookup_shipment(shipment_id)
    except Exception as error:
        return [f"rules could not be checked: {type(error).__name__}: {error}"]
    if not facts.get("ok"):
        return [f"none: {facts.get('error', 'shipment not found')}"]
    expected = evaluate(facts.get("shipment"), facts.get("customer"))
    if expected.reasons:
        return expected.reasons
    if not expected.action_required:
        return ["none: the shipment is not delayed"]
    return ["none: no rule requires escalation (judgment or technical failure, "
            "see the message)"]


def format_alert(shipment_id: str, message: str, email_draft: str = "",
                 rules: list[str] | None = None, author: str = "agent") -> str:
    """The text the human reads (plain text: same in Telegram and on screen).

    Separate blocks so the human sees WHO wrote what: facts checked by code,
    then the message written by the agent (or the guardrail), then the draft.
    """
    text = f"[ESCALATION] Shipment {shipment_id}"
    if rules:
        text += "\n\nRules (checked by code):\n" + "\n".join(f"- {line}" for line in rules)
    text += f"\n\nMessage ({author}):\n{message.strip()}"
    if email_draft and email_draft.strip():
        text += f"\n\n--- EMAIL DRAFT (NOT SENT) ---\n{email_draft.strip()}"
    return text


def is_judgment(message: str) -> bool:
    """True if a human alert is an escalation by judgment (rule 6)."""
    return message.strip().upper().startswith(JUDGMENT_PREFIX)


def record_action(shipment_id: str, action: str, reason: str, details: str) -> dict:
    """Write one audit row with a controlled vocabulary for `action`."""
    if action not in VALID_ACTIONS:
        return {
            "ok": False,
            "error": f"invalid action {action!r}, use one of {sorted(VALID_ACTIONS)}",
        }
    saved, error = _append_log(shipment_id, action, reason, details)
    if not saved:  # the source failed (e.g. Sheet unreachable): not the agent's fault
        return {"ok": False, "error": f"log row not saved: {error}", "technical": True}
    return {"ok": True}


def record_guardrail(shipment_id: str, reason: str, details: str = "") -> None:
    """Log a guardrail discrepancy. Code only: the model has no tool for it."""
    _append_log(shipment_id, GUARDRAIL_ACTION, reason, details)


def _append_log(shipment_id: str, action: str, reason: str, details: str) -> tuple[bool, str]:
    """Write one row to the audit log (shared by the agent and the guardrail).

    The row is persisted in the data source first (in memory: nothing to do;
    in Sheets: one row in log_acciones). It only counts as logged (ACTION_LOG)
    if the source accepted it: a log that says "saved" when it isn't is worse
    than no log. Never raises: returns (saved, error message).
    """
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shipment_id": shipment_id,
        "action": action,
        "reason": reason,
        "details": details,
    }
    try:
        get_data_source().append_log(row)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        print(f"[LOG NOT SAVED] {shipment_id} | {action} | {message}")
        return False, message
    ACTION_LOG.append(row)
    print(f"[LOG] {shipment_id} | {action} | {reason}")
    return True, ""


# ---------------------------------------------------------------------------
# Tools for the model, bound to ONE shipment.
# ---------------------------------------------------------------------------


def make_tools(shipment_id: str, event_id: str = "") -> dict[str, Callable[..., dict]]:
    """Build the 4 tools for one run, with shipment_id already inside.

    Each inner function "remembers" the shipment_id it was created with
    (a closure). A new run creates new tools, so two shipments handled at
    the same time (phase 4, FastAPI) can never mix their ids.
    event_id (phase 4) travels the same way, to build the email
    idempotency key: the model never sees it or writes it.
    """
    email_key = email_idempotency_key(event_id)

    def get_shipment() -> dict:
        """Look up the shipment of this event and its customer. Read only.

        Always call this FIRST, before any other tool, to get the facts.
        Returns the shipment (status, delay_hours, delay_reason, expected_date,
        new_eta, route, carrier) and its customer (name, contact_email, priority, language).
        If the shipment does not exist it returns ok=false with an error.
        If the customer does not exist, customer is null.
        new_eta is the new estimated delivery date (YYYY-MM-DD) or "" if unknown.
        delay_reason is an internal note for staff: never copy it to the customer.
        """
        return lookup_shipment(shipment_id)

    def send_customer_email(subject: str, body: str) -> dict:
        """Send an email to the customer about their delayed shipment.

        The recipient is the customer's contact_email, added automatically:
        you only write subject and body.
        Use it only for shipments with status "retrasado" whose customer has a
        contact_email and whose data is consistent. Otherwise it is refused:
        escalate instead, with the email as notify_human's email_draft.
        Write subject and body in the customer's language, greeting the customer
        by name, with line breaks between paragraphs. Explain the delay cause in
        general words, never the internal delay_reason text.
        Do NOT use it when you escalate by judgment (rule 6): put the email in
        notify_human's email_draft instead, so a human reviews it first.
        """
        # PREVENT instead of detect: a real email can't be undone, so code
        # checks BEFORE sending (the guardrail afterwards could only report it).
        # 1. Fresh facts, not what the model remembers. If the source is down
        #    this raises -> "technical" and nothing is sent (fail closed).
        facts = lookup_shipment(shipment_id)
        expected = evaluate(facts.get("shipment"), facts.get("customer"))
        # 2. The rules say no email -> refuse. It's the agent's mistake.
        if not expected.send_email:
            why = "; ".join(expected.reasons) or "shipment not found or not delayed"
            hint = ("escalate with notify_human and put the email in email_draft"
                    if expected.escalate else "do not email; just log the action")
            return {"ok": False, "agent_error": True, "refused_by_rules": True,
                    "error": f"refused: the rules say this customer must NOT be emailed "
                             f"({why}). Nothing was sent: {hint}."}
        # 3. Rule 6: rules.py can't see judgment. If the agent already escalated
        #    by judgment, the email belongs to the human (email_draft).
        if any(is_judgment(n["message"]) for n in HUMAN_NOTIFICATIONS
               if n["shipment_id"] == shipment_id):
            return {"ok": False, "agent_error": True, "refused_by_rules": True,
                    "error": "refused: you already escalated by judgment (rule 6). Nothing "
                             "was sent: the email goes as email_draft for a human to review."}
        # 4. The recipient comes from the data, never from the model.
        return deliver_email(facts["customer"]["contact_email"], subject, body, email_key)

    def notify_human(message: str, email_draft: str = "") -> dict:
        """Alert the human supervisor so they take over the case.

        Use it when ANY escalation rule applies: delay_hours > 24, customer
        priority "alta", or missing/inconsistent data. The message must include
        the customer name and a clear reason for escalating. The shipment_id
        and the rules that apply (checked by code) are attached automatically.

        Judgment escalation: if delay_reason describes something serious the
        rules do not cover (theft, loss or damage of the goods, an accident, no
        way to estimate delivery), start the message with "JUDGMENT:" and say
        why, and do NOT email the customer.

        email_draft: whenever you escalate and the customer was NOT emailed
        (judgment, missing or inconsistent data, the email failed or was
        refused), put the email you would have sent here, as
        "Subject: <subject>", a blank line, then the body, so the human has it
        ready. Leave it empty only if the customer was already emailed.
        """
        return deliver_alert(shipment_id, message, email_draft)

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
