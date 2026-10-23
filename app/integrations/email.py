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
    if code in (401, 403):
        hint = ("API key missing, wrong or without permission; without our own domain "
                "Resend only sends to the account's email (check EMAIL_TEST_RECIPIENT)")
    elif code == 422:
        hint = "Resend rejected the email data (check EMAIL_FROM and the recipient)"
    elif code == 429:
        hint = "too many emails, Resend rate limit"
    elif code >= 500:
        hint = "Resend is failing on its side"
    else:
        hint = "unexpected answer from Resend"
    return f"Resend HTTP {code}: {hint}. Response: {response.text[:300]}"


def send_email(to: str, subject: str, body: str) -> str:
    """Send one email. Returns Resend's message id. Raises EmailError."""
    api_key, sender, test_recipient = load_resend_config()
    to, subject, body = apply_test_mode(to, subject, body, test_recipient)
    try:
        response = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
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
    message_id = send_email("cliente.ficticio@example.com", "Prueba de Resend",
                            "Hola,\n\nEste es un email de prueba del Agente Logística.\n")
    print(f"Sent. Resend id: {message_id}")
