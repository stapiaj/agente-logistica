"""Load settings from .env (moved here from scripts/fase1_llm.py)."""

import os
import sys

from dotenv import load_dotenv


def load_config() -> tuple[str, str]:
    """Read the API key and model name from .env. Stop if any is missing."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not api_key or not model:
        sys.exit("Missing GEMINI_API_KEY or GEMINI_MODEL in .env")
    return api_key, model


def load_fallback_models() -> list[str]:
    """Optional backup models, in order (comma separated in .env).

    Used only if the main model fails with a 5xx (overloaded) or a 429 (quota).
    """
    load_dotenv()
    raw = os.getenv("GEMINI_FALLBACK_MODEL", "")
    return [name.strip() for name in raw.split(",") if name.strip()]


def load_sheets_config() -> tuple[str, str]:
    """Read the Google Sheet ID and the service account key file from .env.

    The key file is the robot's credential (a secret, never in Git); the ID
    only says which spreadsheet to open (useless without permission).
    """
    load_dotenv()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not sheet_id or not key_file:
        sys.exit("Missing GOOGLE_SHEET_ID or GOOGLE_SERVICE_ACCOUNT_FILE in .env")
    return sheet_id, key_file


VALID_DATA_SOURCES = ("memory", "sheets")


def load_data_source() -> str:
    """Where shipments, customers and the log live: "memory" or "sheets".

    Empty -> "memory" (quick tests, no API quota). Anything else stops the
    program: a typo like "shets" must not silently fall back to memory.
    """
    load_dotenv()
    source = os.getenv("DATA_SOURCE", "").strip().lower() or "memory"
    if source not in VALID_DATA_SOURCES:
        sys.exit(f"Invalid DATA_SOURCE={source!r} in .env, use one of {VALID_DATA_SOURCES}")
    return source


VALID_EMAIL_MODES = ("simulated", "resend")


def load_email_mode() -> str:
    """How customer emails go out: "simulated" (printed only) or "resend" (real).

    Empty -> "simulated": a real email is never sent by accident. Anything
    else stops the program (same idea as DATA_SOURCE).
    """
    load_dotenv()
    mode = os.getenv("EMAIL_MODE", "").strip().lower() or "simulated"
    if mode not in VALID_EMAIL_MODES:
        sys.exit(f"Invalid EMAIL_MODE={mode!r} in .env, use one of {VALID_EMAIL_MODES}")
    return mode


def load_resend_config() -> tuple[str, str, str]:
    """Resend API key, sender address and the test recipient.

    EMAIL_TEST_RECIPIENT (test mode): EVERY email goes there instead of to
    the customer. FAIL CLOSED: if it is empty we stop, we don't fall back to
    the real customer. A missing line in .env must never end in a real email
    (it happened in T3: the test email went out to the "customer" and only
    Resend's own sandbox stopped it). Emailing real customers needs a
    deliberate switch, EMAIL_ALLOW_REAL_RECIPIENTS=true, never set in this
    project. Returns test_recipient = "" only when that switch is on.
    """
    load_dotenv()
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("EMAIL_FROM", "").strip()
    test_recipient = os.getenv("EMAIL_TEST_RECIPIENT", "").strip()
    allow_real = os.getenv("EMAIL_ALLOW_REAL_RECIPIENTS", "").strip().lower() == "true"
    if not api_key or not sender:
        sys.exit("Missing RESEND_API_KEY or EMAIL_FROM in .env (needed with EMAIL_MODE=resend)")
    if not test_recipient and not allow_real:
        sys.exit("Missing EMAIL_TEST_RECIPIENT in .env: nothing is sent (fail closed). "
                 "Real customers are only emailed with EMAIL_ALLOW_REAL_RECIPIENTS=true")
    return api_key, sender, test_recipient


VALID_NOTIFY_MODES = ("simulated", "telegram")


def load_notify_mode() -> str:
    """How human alerts go out: "simulated" (printed only) or "telegram" (real).

    Empty -> "simulated". Anything else stops the program (like EMAIL_MODE).
    """
    load_dotenv()
    mode = os.getenv("NOTIFY_MODE", "").strip().lower() or "simulated"
    if mode not in VALID_NOTIFY_MODES:
        sys.exit(f"Invalid NOTIFY_MODE={mode!r} in .env, use one of {VALID_NOTIFY_MODES}")
    return mode


def load_telegram_config(need_chat_id: bool = True) -> tuple[str, str]:
    """Bot token (a secret: whoever has it controls the bot) and the chat id.

    need_chat_id=False only to FIND the chat id (it isn't known yet).
    """
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        sys.exit("Missing TELEGRAM_BOT_TOKEN in .env (needed with NOTIFY_MODE=telegram)")
    if need_chat_id and not chat_id:
        sys.exit("Missing TELEGRAM_CHAT_ID in .env: run python -m app.integrations.telegram --find-chat-id")
    return token, chat_id


def load_alert_email() -> str:
    """Supervisor's email for the BACKUP alert channel (phase 5).

    If Telegram can't deliver an alert, it goes by email to this address
    (with Resend, through send_email: test mode and fail closed still apply).
    Empty -> no backup channel: a failed alert behaves as before phase 5
    (the guardrail retries once and, as a last resort, an "error" log row).
    """
    load_dotenv()
    return os.getenv("ALERT_EMAIL_TO", "").strip()


def startup_report() -> str:
    """Check the configuration the server needs and describe it, WITHOUT secrets.

    Called once when the server starts (phase 5). In Render there is no
    terminal to look at: if something essential is missing, the server
    stops here with a clear message in the logs (the deploy fails and
    Render keeps the previous version running), instead of failing later
    with the first notice from the Sheet. Each load_* stops the program
    (sys.exit) if its settings are missing or invalid.
    Returns one line for the logs: modes and "set"/"found", never values.
    """
    load_config()  # Gemini key and model
    source = load_data_source()
    parts = [f"DATA_SOURCE={source}"]
    if source == "sheets":
        _, key_file = load_sheets_config()
        if not os.path.isfile(key_file):
            sys.exit(f"Service account key file not found: {key_file!r}. "
                     "In Render: add it as a Secret File and point "
                     "GOOGLE_SERVICE_ACCOUNT_FILE to /etc/secrets/<name>")
        parts.append("key_file=found")
    email_mode = load_email_mode()
    if email_mode == "resend":
        load_resend_config()
    parts.append(f"EMAIL_MODE={email_mode}")
    notify_mode = load_notify_mode()
    if notify_mode == "telegram":
        load_telegram_config()
    parts.append(f"NOTIFY_MODE={notify_mode}")
    alert_email = load_alert_email()
    parts.append(f"ALERT_EMAIL_TO={'set' if alert_email else 'EMPTY'}")
    line = "[startup] " + " ".join(parts)
    if notify_mode == "telegram" and not alert_email:
        line += "\n[startup] WARNING: no backup alert channel (ALERT_EMAIL_TO is empty)"
    return line


MIN_WEBHOOK_SECRET_LENGTH = 32


def load_webhook_secret() -> str:
    """Shared secret that every webhook call must send in X-Webhook-Secret.

    FAIL CLOSED: empty or too short -> the server does not start. A webhook
    without a lock must not exist, not even by accident (whoever can call it
    can make the agent email customers). Generate one with:
    python -c "import secrets; print(secrets.token_urlsafe(32))"
    """
    load_dotenv()
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if len(secret) < MIN_WEBHOOK_SECRET_LENGTH:
        sys.exit(f"Missing or too short WEBHOOK_SECRET in .env (min {MIN_WEBHOOK_SECRET_LENGTH} chars). "
                 'Generate one: python -c "import secrets; print(secrets.token_urlsafe(32))"')
    return secret
