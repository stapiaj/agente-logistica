"""Customer emails through Resend (phase 3b).

Resend is an HTTP API: one POST with a JSON body and the API key in the
Authorization header. We use httpx directly (no SDK) so the contract is
visible: URL, headers, JSON, status code.

Two safety nets, because a real email can't be undone:
- Test mode: if EMAIL_TEST_RECIPIENT is set, every email goes there, the
  subject starts with [TEST] and the body says who it was meant for.
- No automatic retries: after a timeout we don't know if the email left.
  Retrying could email the customer twice, so we raise and a human checks.
  Only retry what is safe to repeat (idempotent).
- Idempotency key (phase 4): with the Idempotency-Key header, Resend keeps
  the key for 24 h. Same key + same email -> not sent again (it returns the
  original id). Same key + different email -> 409, nothing sent. We derive
  the key from the webhook event_id: one notice, at most one email.

Errors: any failure raises EmailError with a readable message. The agent
loop turns it into a "technical" error (not the agent's fault) and the
guardrail makes sure a human knows the customer was not emailed.
"""

import httpx

from app.config import load_resend_config

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10


class EmailError(Exception):
    """The email could not be sent (or we can't be sure it was)."""


def apply_test_mode(to: str, subject: str, body: str, test_recipient: str) -> tuple[str, str, str]:
    """Redirect the email to the test inbox, saying who it was meant for."""
    if not test_recipient:
        return to, subject, body
    banner = f"[TEST MODE] Original recipient: {to}\n{'-' * 40}\n\n"
    return test_recipient, f"[TEST] {subject}", banner + body


def _explain(response: httpx.Response) -> str:
    """Turn an HTTP error from Resend into a message a person can act on."""
    code = response.status_code
    if code == 401:
        hint = "wrong or missing RESEND_API_KEY"
    elif code == 403:
        hint = ("not allowed: the key has no sending permission, or the recipient is not "
                "the account's email (without our own domain; check EMAIL_TEST_RECIPIENT)")
    elif code == 409:
        hint = ("idempotency key already used: this notice already sent an email with "
                "different content (or the first one is still in progress); nothing was sent")
    elif code == 422:
        hint = "Resend rejected the email data (check EMAIL_FROM and the recipient)"
    elif code == 429:
        hint = "too many emails, Resend rate limit"
    elif code >= 500:
        hint = "Resend is failing on its side"
    else:
        hint = "unexpected answer from Resend"
    return f"Resend HTTP {code}: {hint}. Response: {response.text[:300]}"


def send_email(to: str, subject: str, body: str, idempotency_key: str = "") -> str:
    """Send one email. Returns Resend's message id. Raises EmailError.

    idempotency_key: "" = no header (manual tests and scripts).
    """
    api_key, sender, test_recipient = load_resend_config()
    to, subject, body = apply_test_mode(to, subject, body, test_recipient)
    headers = {"Authorization": f"Bearer {api_key}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        response = httpx.post(
            RESEND_URL,
            headers=headers,
            json={"from": sender, "to": [to], "subject": subject, "text": body},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as error:
        raise EmailError("Resend did not answer in time: the email MAY have been sent, "
                         "not retried to avoid a duplicate") from error
    except httpx.HTTPError as error:  # no connection, DNS...
        raise EmailError(f"could not reach Resend: {type(error).__name__}: {error}") from error
    if response.status_code >= 400:
        raise EmailError(_explain(response))
    return response.json().get("id", "")


if __name__ == "__main__":
    # Manual test, no LLM: python -m app.integrations.email
    # With a key (phase 4): python -m app.integrations.email <key>
    #   run it twice with the same key -> same id, only ONE email arrives.
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else ""
    message_id = send_email("cliente.ficticio@example.com", "Prueba de Resend",
                            "Hola,\n\nEste es un email de prueba del Agente Logística.\n", key)
    print(f"Sent. Resend id: {message_id}" + (f" (idempotency key {key})" if key else ""))
