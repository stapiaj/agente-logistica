"""Phase 3b: checks WITHOUT the LLM (no quota used, nothing really sent).

Run from the project root:
    python -m scripts.fase3b_checks

Each check calls our code directly, the same way the agent loop would,
and prints OK or FAIL.
"""

import os
import sys

# Must be set before importing app (load_dotenv never overrides it):
# these checks use the in-memory data, never the real Sheet.
os.environ["DATA_SOURCE"] = "memory"
os.environ["EMAIL_MODE"] = "simulated"  # never a real email from these checks
os.environ["NOTIFY_MODE"] = "simulated"  # never a real Telegram message either

from app import tools  # noqa: E402
from app.agent import execute_tool  # noqa: E402
from app.config import load_resend_config  # noqa: E402
from app.integrations.email import apply_test_mode  # noqa: E402
from app.integrations import telegram  # noqa: E402
import httpx  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"{'OK  ' if condition else 'FAIL'} {name}" + (f"\n     {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


def check_tool_arguments() -> None:
    """Decision 3: arguments are validated BEFORE running the tool."""
    print("\n--- Tool arguments (decision 3) ---")
    tools.reset_outbox()
    bound = tools.make_tools("ENV-1001")

    # 1. Invented parameter (the old shipment_id): agent error, not technical.
    result = execute_tool(bound, "send_customer_email", {
        "shipment_id": "ENV-1001", "subject": "s", "body": "b"})
    check("invented parameter -> agent_error, not technical",
          result.get("agent_error") and not result.get("technical"), result["error"])
    check("invented parameter -> the tool did NOT run (no email)", not tools.SENT_EMAILS)

    # 2. Missing required parameter.
    result = execute_tool(bound, "log_action", {"action": "email_sent"})
    check("missing parameter -> agent_error", bool(result.get("agent_error")), result["error"])

    # 3. Unknown tool.
    result = execute_tool(bound, "delete_shipment", {})
    check("unknown tool -> agent_error", bool(result.get("agent_error")), result["error"])

    # 4. A TypeError INSIDE a tool is still technical (bug or provider crash).
    def crashing_tool() -> dict:
        raise TypeError("something broke inside the tool")

    result = execute_tool({"crashing_tool": crashing_tool}, "crashing_tool", {})
    check("exception inside the tool -> technical",
          result.get("technical") and not result.get("agent_error"), result["error"])

    # 5. A correct call still works.
    result = execute_tool(bound, "get_shipment", {})
    check("valid call -> ok", result.get("ok") is True)


def check_email_test_mode() -> None:
    """T3: in test mode every email is redirected and says who it was for."""
    print("\n--- Email test mode (T3) ---")
    to, subject, body = apply_test_mode("cliente@example.com", "Retraso", "Hola", "yo@test.com")
    check("redirected to the test inbox", to == "yo@test.com", to)
    check("subject marked [TEST]", subject.startswith("[TEST]"), subject)
    check("body starts with the original recipient",
          body.startswith("[TEST MODE] Original recipient: cliente@example.com"))
    check("without test recipient nothing changes",
          apply_test_mode("c@x.com", "S", "B", "") == ("c@x.com", "S", "B"))

    # Fail closed: no EMAIL_TEST_RECIPIENT and no explicit switch -> stop.
    # Fake values in os.environ (load_dotenv never overrides them); the real
    # ones are restored afterwards. Nothing is sent: we only load the config.
    names = ("RESEND_API_KEY", "EMAIL_FROM", "EMAIL_TEST_RECIPIENT", "EMAIL_ALLOW_REAL_RECIPIENTS")
    saved = {name: os.environ.get(name) for name in names}
    os.environ.update({"RESEND_API_KEY": "fake", "EMAIL_FROM": "a@b.com",
                       "EMAIL_TEST_RECIPIENT": "", "EMAIL_ALLOW_REAL_RECIPIENTS": ""})
    try:
        try:
            load_resend_config()
            stopped = False
        except SystemExit as stop:
            stopped, reason = True, stop.code
        check("no test recipient -> stops (fail closed)", stopped, reason if stopped else "")
        os.environ["EMAIL_ALLOW_REAL_RECIPIENTS"] = "true"
        check("explicit switch -> allowed", load_resend_config()[2] == "")
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def send(shipment_id: str) -> dict:
    """The model's call: only subject and body."""
    return execute_tool(tools.make_tools(shipment_id), "send_customer_email",
                        {"subject": "Retraso de su envío", "body": "Hola,\n\nTexto."})


def check_email_guard() -> None:
    """T4 (decisions 1 and 4): recipient from the data, rules checked BEFORE sending."""
    print("\n--- send_customer_email guard (T4) ---")
    tools.reset_outbox()
    result = send("ENV-1001")
    expected_to = tools.lookup_shipment("ENV-1001")["customer"]["contact_email"]
    check("ENV-1001 (6 h, normal) -> sent", result.get("ok") is True, result)
    check("recipient injected by code = customer's contact_email",
          bool(tools.SENT_EMAILS) and tools.SENT_EMAILS[0]["to"] == expected_to,
          tools.SENT_EMAILS[0]["to"] if tools.SENT_EMAILS else "no email")

    for shipment_id, case in (("ENV-1004", "customer without email"),
                              ("ENV-1005", "not delayed"),
                              ("ENV-9999", "does not exist")):
        tools.reset_outbox()
        result = send(shipment_id)
        check(f"{shipment_id} ({case}) -> refused, agent error, nothing sent",
              result.get("refused_by_rules") and not result.get("technical")
              and not tools.SENT_EMAILS, result.get("error"))

    # Rule 6: after a JUDGMENT alert the email goes to the human, not the customer.
    tools.reset_outbox()
    tools.deliver_alert("ENV-1006", "JUDGMENT: goods stolen")
    result = send("ENV-1006")
    check("after a JUDGMENT alert -> refused, nothing sent",
          result.get("refused_by_rules") and not tools.SENT_EMAILS, result.get("error"))


def check_telegram_helpers() -> None:
    """T5: long alerts are split (not cut) and the token never shows in errors."""
    print("\n--- Telegram helpers (T5) ---")
    short = "short alert"
    check("short alert -> one message, unchanged", telegram.split_message(short) == [short])

    long_text = "\n".join(f"line {i}: " + "x" * 80 for i in range(120))  # ~10.800 chars
    parts = telegram.split_message(long_text)
    check("long alert -> several parts, each <= 4096",
          len(parts) > 1 and all(len(p) <= telegram.MAX_LENGTH for p in parts),
          [len(p) for p in parts])
    check("parts numbered (1/n)...(n/n)",
          parts[0].startswith(f"(1/{len(parts)})") and parts[-1].startswith(f"({len(parts)}/"))
    check("nothing lost when splitting",
          all(f"line {i}:" in "".join(parts) for i in range(120)))

    token = "123456:FAKE-token"
    request = httpx.Request("POST", f"https://api.telegram.org/bot{token}/sendMessage")
    response = httpx.Response(401, text=f"Unauthorized for bot{token}", request=request)
    try:
        telegram.raise_for_error(response, token)
        message = ""
    except telegram.TelegramError as error:
        message = str(error)
    check("401 -> readable error", "wrong TELEGRAM_BOT_TOKEN" in message, message)
    check("token never shown in the error", token not in message)


def main() -> None:
    check_tool_arguments()
    check_email_test_mode()
    check_email_guard()
    check_telegram_helpers()
    print(f"\n{'All checks passed' if not FAILURES else f'{len(FAILURES)} check(s) FAILED'}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
