"""Phase 5: the backup alert channel (email to the supervisor if Telegram fails).

Two modes, run from the project root:

    python -m scripts.fase5_checks checks
        WITHOUT the LLM, nothing really sent. Telegram and Resend are replaced
        by fakes that we can make fail on purpose. Checks: Telegram OK -> no
        email; Telegram fails -> the same alert by email + informative log row;
        both fail -> "technical" error; no ALERT_EMAIL_TO -> as before phase 5;
        the bot token never leaks; the guardrail still sees a missing log and
        still retries (and leaves "error") when both channels fail.

    python -m scripts.fase5_checks live
        ONE real test alert with your .env modes (NOTIFY_MODE, EMAIL_MODE,
        ALERT_EMAIL_TO), no LLM quota. Data in memory, so nothing is written
        to the real Sheet. To see the backup channel, break Telegram ONLY in
        that terminal:  $env:TELEGRAM_CHAT_ID="123"   (then close the terminal)
"""

import os
import sys

MODE = sys.argv[1] if len(sys.argv) > 1 else "checks"
if MODE not in ("checks", "live"):
    sys.exit("Usage: python -m scripts.fase5_checks [checks | live]")

# Must be set before importing app (load_dotenv never overrides them).
os.environ["DATA_SOURCE"] = "memory"  # both modes: never the real Sheet
if MODE == "checks":
    # Fake but valid-looking values: even if a fake were missing, nothing
    # real could go out (a fake key gets 401 at most).
    os.environ.update({
        "NOTIFY_MODE": "telegram",
        "EMAIL_MODE": "resend",
        "TELEGRAM_BOT_TOKEN": "123456:FAKE-TOKEN-for-checks",
        "TELEGRAM_CHAT_ID": "1",
        "RESEND_API_KEY": "re_fake_key_for_checks",
        "EMAIL_FROM": "onboarding@resend.dev",
        "EMAIL_TEST_RECIPIENT": "yo@test.com",
        "ALERT_EMAIL_TO": "jefe@test.com",
    })

import httpx  # noqa: E402

from app import tools  # noqa: E402
from app.agent import AgentRun, ToolCall, apply_guardrail, execute_tool  # noqa: E402
from app.integrations import email as email_provider  # noqa: E402
from app.integrations import telegram  # noqa: E402

FAILURES: list[str] = []
TOKEN = "123456:FAKE-TOKEN-for-checks"


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"{'OK  ' if condition else 'FAIL'} {name}" + (f"\n     {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# Fakes: what each channel does in the next check
# ---------------------------------------------------------------------------

TELEGRAM_SENT: list[str] = []
ALERT_EMAILS: list[dict] = []
FAKE = {"telegram_fails": False, "email_fails": False}


def fake_send_message(text: str) -> int:
    if FAKE["telegram_fails"]:
        # A real Telegram error built by our own code, with the token inside
        # the answer: checks that it is hidden everywhere afterwards.
        response = httpx.Response(400, text=f'{{"description":"Bad Request: chat not found"}} {TOKEN}')
        telegram.raise_for_error(response, TOKEN)
    TELEGRAM_SENT.append(text)
    return 1


def fake_send_email(to: str, subject: str, body: str, idempotency_key: str = "") -> str:
    if FAKE["email_fails"]:
        raise email_provider.EmailError("Resend HTTP 403: not allowed (fake failure)")
    ALERT_EMAILS.append({"to": to, "subject": subject, "body": body, "key": idempotency_key})
    return "fake-id-1"


def reset(telegram_fails: bool = False, email_fails: bool = False, alert_to: str = "jefe@test.com") -> None:
    tools.reset_outbox()
    TELEGRAM_SENT.clear()
    ALERT_EMAILS.clear()
    FAKE.update(telegram_fails=telegram_fails, email_fails=email_fails)
    os.environ["ALERT_EMAIL_TO"] = alert_to


def alert(shipment_id: str = "ENV-1002") -> dict:
    """The agent's notify_human, called exactly as the agent loop would."""
    bound = tools.make_tools(shipment_id)
    return execute_tool(bound, "notify_human", {
        "message": "Customer Juan Perez: delay of 30 h, escalating.",
        "email_draft": "Subject: Su envio se retrasa\n\nEstimado Juan..."})


def guardrail_rows(text: str) -> list[dict]:
    return [r for r in tools.ACTION_LOG if r["action"] == tools.GUARDRAIL_ACTION and text in r["reason"]]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_telegram_ok() -> None:
    print("\n--- Telegram works ---")
    reset()
    result = alert()
    check("ok, delivered by Telegram", result.get("ok") is True and "Telegram" in result.get("status", ""),
          result)
    check("no alert email", not ALERT_EMAILS)
    check("counted as delivered (1 alert)", len(tools.HUMAN_NOTIFICATIONS) == 1)
    check("no 'delivered by email' row", not guardrail_rows("alert delivered by email"))


def check_telegram_fails() -> None:
    print("\n--- Telegram fails -> email to the supervisor ---")
    reset(telegram_fails=True)
    result = alert()
    check("agent gets ok (not technical)", result.get("ok") is True and not result.get("technical"),
          result)
    check("status says it went by EMAIL and why", "EMAIL" in result.get("status", "")
          and "chat not found" in result.get("status", ""), result.get("status"))
    check("exactly one alert email", len(ALERT_EMAILS) == 1, ALERT_EMAILS)
    if not ALERT_EMAILS:
        return
    sent = ALERT_EMAILS[0]
    check("to ALERT_EMAIL_TO (the supervisor)", sent["to"] == "jefe@test.com", sent["to"])
    check("subject [ALERT] with the shipment", sent["subject"].startswith("[ALERT]")
          and "ENV-1002" in sent["subject"], sent["subject"])
    body = sent["body"]
    check("body: says Telegram failed and why", "Telegram error" in body and "chat not found" in body)
    check("body: full alert (rules by code, agent message, draft)",
          "Rules (checked by code)" in body and "Juan Perez" in body
          and "EMAIL DRAFT (NOT SENT)" in body and "Su envio se retrasa" in body)
    check("no idempotency key on alerts (a duplicate alert is cheap)", sent["key"] == "")
    everything = body + result.get("status", "") + str(tools.ACTION_LOG)
    check("bot token never shown (email, status, log)", TOKEN not in everything)
    check("NOT counted as a customer email (SENT_EMAILS empty)", not tools.SENT_EMAILS)
    check("counted as delivered (1 alert)", len(tools.HUMAN_NOTIFICATIONS) == 1)
    check("informative 'guardrail' row in the log", len(guardrail_rows("alert delivered by email")) == 1,
          tools.ACTION_LOG)


def check_both_fail() -> None:
    print("\n--- Telegram AND email fail ---")
    reset(telegram_fails=True, email_fails=True)
    result = alert()
    check("technical error (not the agent's fault)", result.get("technical") is True, result)
    error = result.get("error", "")
    check("error names both channels", "both alert channels failed" in error
          and "Telegram" in error and "Email" in error, error)
    check("NOT counted as delivered", not tools.HUMAN_NOTIFICATIONS)
    check("no 'delivered by email' row", not guardrail_rows("alert delivered by email"))


def check_no_backup() -> None:
    print("\n--- No ALERT_EMAIL_TO -> as before phase 5 ---")
    reset(telegram_fails=True, alert_to="")
    result = alert()
    check("technical error, the Telegram one", result.get("technical") is True
          and "chat not found" in result.get("error", ""), result)
    check("no email attempted", not ALERT_EMAILS)


def check_guardrail_missing_log() -> None:
    print("\n--- Guardrail: the informative row does not hide a missing log ---")
    reset(telegram_fails=True)
    alert()  # the agent escalates (delivered by email) but never calls log_action
    report = apply_guardrail("ENV-1002")
    check("guardrail writes the missing log", any("agent did not log" in r["reason"]
          for r in tools.ACTION_LOG), report.corrections)
    check("guardrail does not alert again (the human has the case)", len(ALERT_EMAILS) == 1,
          len(ALERT_EMAILS))


def check_guardrail_both_fail() -> None:
    print("\n--- Guardrail: both channels fail -> retry once, then 'error' row ---")
    reset(telegram_fails=True, email_fails=True)
    args = {"message": "Customer Juan Perez: delay of 30 h, escalating.", "email_draft": "Subject: x\n\ny"}
    result = execute_tool(tools.make_tools("ENV-1002"), "notify_human", args)
    run = AgentRun(shipment_id="ENV-1002", tool_calls=[ToolCall("notify_human", args, result)])
    tools.record_action("ENV-1002", "escalated", "delay > 24 h", "")  # the agent did log
    report = apply_guardrail("ENV-1002", run)
    errors = [r for r in tools.ACTION_LOG if r["action"] == "error"
              and "human alert could NOT be delivered" in r["reason"]]
    check("guardrail retried and left the 'error' row (last resort)", len(errors) == 1,
          report.corrections)
    check("still nothing counted as delivered", not tools.HUMAN_NOTIFICATIONS)


def run_checks() -> None:
    telegram.send_message = fake_send_message
    email_provider.send_email = fake_send_email
    check_telegram_ok()
    check_telegram_fails()
    check_both_fail()
    check_no_backup()
    check_guardrail_missing_log()
    check_guardrail_both_fail()
    print(f"\n{'All checks passed' if not FAILURES else f'{len(FAILURES)} check(s) FAILED: {FAILURES}'}")
    sys.exit(1 if FAILURES else 0)


def run_live() -> None:
    from app.config import load_alert_email, load_email_mode, load_notify_mode

    print(f"NOTIFY_MODE={load_notify_mode()}  EMAIL_MODE={load_email_mode()}  "
          f"ALERT_EMAIL_TO={'set' if load_alert_email() else 'EMPTY (no backup channel)'}")
    tools.reset_outbox()
    try:
        result = tools.deliver_alert("ENV-1002", "[TEST] Phase 5: backup alert channel test.",
                                     author="test, phase 5")
    except Exception as error:  # noqa: BLE001
        print(f"\nAlert NOT delivered by any channel: {type(error).__name__}: {error}")
        sys.exit(1)
    print(f"\nResult: {result['status']}")


if __name__ == "__main__":
    run_live() if MODE == "live" else run_checks()
