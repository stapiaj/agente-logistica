"""Phase 4: simulate the Google Sheet sending webhook notices to our server.

Two modes, run from the project root:

    python -m scripts.fase4_webhook checks
        WITHOUT the LLM, WITHOUT uvicorn, nothing really sent. FastAPI's
        TestClient calls the app inside this same program, and the agent is
        replaced by a fake that only counts how many times it was started.
        Checks the door: secret (401), body (422), new (202), repeated (200),
        event store down (503), and the Resend idempotency key.

    python -m scripts.fase4_webhook live ENV-1001
        Against YOUR running server (uvicorn app.main:app --reload), with the
        real agent and whatever modes your .env has (DATA_SOURCE, EMAIL_MODE,
        NOTIFY_MODE). Sends one notice with a fresh event_id (expects 202),
        then the SAME one again (expects 200, the agent does not run twice).
        The agent's work shows in the uvicorn terminal, not here: with 202
        the sender never gets the agent's result. That is the point.
        Options: --url http://127.0.0.1:8000   --no-repeat
"""

import argparse
import os
import sys
import uuid
import warnings

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: object = "") -> None:
    print(f"{'OK  ' if condition else 'FAIL'} {name}" + (f"\n     {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# checks: in-process, no LLM
# ---------------------------------------------------------------------------

TEST_SECRET = "test-secret-for-checks-only-0123456789abcdef"


def run_checks() -> None:
    # Must be set BEFORE importing app (load_dotenv never overrides them).
    os.environ["DATA_SOURCE"] = "memory"     # never the real Sheet
    os.environ["EMAIL_MODE"] = "simulated"   # never a real email
    os.environ["NOTIFY_MODE"] = "simulated"  # never a real Telegram message
    os.environ["WEBHOOK_SECRET"] = TEST_SECRET  # not your real one

    # Starlette's TestClient warns when it uses httpx (it prefers httpx2).
    warnings.filterwarnings("ignore", message=".*httpx.*")
    from fastapi.testclient import TestClient

    from app import events, main, tools

    started: list[tuple[str, str]] = []

    def fake_agent_job(shipment_id: str, event_id: str) -> None:
        started.append((shipment_id, event_id))

    # The endpoint looks run_agent_job up by name when it runs: replacing it
    # here swaps the real agent (Gemini) for the counter above.
    main.run_agent_job = fake_agent_job
    client = TestClient(main.app)
    url = "/webhook/shipment-delayed"
    good = {"X-Webhook-Secret": TEST_SECRET}
    run_id = uuid.uuid4().hex[:8]  # fresh event_ids every run

    def body(shipment: str = "ENV-1001", event: str | None = None) -> dict:
        return {"shipment_id": shipment, "event_id": event or f"evt-{run_id}-{len(started)}"}

    print("\n== Health ==")
    r = client.get("/health")
    check("GET /health -> 200 ok", r.status_code == 200 and r.json() == {"status": "ok"}, r.text)

    print("\n== Lock: secret (401) ==")
    r = client.post(url, json=body())
    check("no secret -> 401", r.status_code == 401, r.text)
    r = client.post(url, json=body(), headers={"X-Webhook-Secret": "abc"})
    check("wrong secret -> 401", r.status_code == 401, r.text)
    r = client.post(url, json={"shipment_id": "ENV-1001"})
    check("no secret + incomplete body -> 401 (lock before body)", r.status_code == 401, r.text)
    check("agent never started so far", started == [], started)

    print("\n== Mould: body (422) ==")
    r = client.post(url, content="hola", headers={**good, "Content-Type": "application/json"})
    check("malformed JSON -> 422", r.status_code == 422, r.text[:200])
    r = client.post(url, json={"shipment_id": "ENV-1001"}, headers=good)
    check("missing event_id -> 422", r.status_code == 422, r.text[:200])
    r = client.post(url, json={"shipment_id": "   ", "event_id": "evt-x"}, headers=good)
    check("blank shipment_id -> 422", r.status_code == 422, r.text[:200])
    r = client.post(url, json={"shipment_id": "ENV-1001", "event_id": "e" * 201}, headers=good)
    check("event_id longer than 200 -> 422", r.status_code == 422, r.text[:200])
    check("agent never started so far", started == [], started)

    print("\n== New and repeated notice (202 / 200) ==")
    first = body(event=f"evt-{run_id}-dup")
    r = client.post(url, json=first, headers=good)
    check("new notice -> 202 accepted",
          r.status_code == 202 and r.json().get("status") == "accepted", r.text)
    check("agent started once", started == [("ENV-1001", first["event_id"])], started)
    r = client.post(url, json=first, headers=good)
    check("same notice again -> 200 already_processed",
          r.status_code == 200 and r.json().get("status") == "already_processed", r.text)
    check("agent still started only once", len(started) == 1, started)
    r = client.post(url, json={**first, "event_id": f"  {first['event_id']}  "}, headers=good)
    check("same event_id with spaces -> 200 (trimmed)", r.status_code == 200, r.text)
    r = client.post(url, json=body(event=f"evt-{run_id}-second-delay"), headers=good)
    check("same shipment, NEW event_id -> 202 (a second delay is a new fact)",
          r.status_code == 202 and len(started) == 2, r.text)

    print("\n== Shipment that does not exist ==")
    r = client.post(url, json=body("ENV-9999", f"evt-{run_id}-missing"), headers=good)
    check("ENV-9999 -> 202 (the server does not judge; the agent logs 'error')",
          r.status_code == 202 and started[-1][0] == "ENV-9999", r.text)

    print("\n== Event store down (503) ==")

    class BrokenSource:
        def find_event(self, event_id):
            raise ConnectionError("Sheet unreachable (simulated)")

        def append_event(self, row):
            raise ConnectionError("Sheet unreachable (simulated)")

    original = events.get_data_source
    events.get_data_source = lambda: BrokenSource()
    try:
        before = len(started)
        r = client.post(url, json=body(event=f"evt-{run_id}-store-down"), headers=good)
        check("store down -> 503 retry later", r.status_code == 503, r.text)
        check("agent NOT started (fail closed)", len(started) == before, started)
    finally:
        events.get_data_source = original
    r = client.post(url, json=body(event=f"evt-{run_id}-store-down"), headers=good)
    check("same notice after the store is back -> 202 (it was never recorded)",
          r.status_code == 202, r.text)

    print("\n== Resend idempotency key ==")
    check("evt-1 -> shipment-delayed/evt-1",
          tools.email_idempotency_key("evt-1") == "shipment-delayed/evt-1")
    check("no notice -> no key", tools.email_idempotency_key("") == "")
    check("longest event_id still fits Resend (<= 256)",
          len(tools.email_idempotency_key("e" * 200)) <= 256)
    tools.reset_outbox()
    result = tools.make_tools("ENV-1001", "evt-key-check")["send_customer_email"](
        "Asunto de prueba", "Cuerpo de prueba")
    check("simulated email carries the key in its status",
          result.get("ok") and "shipment-delayed/evt-key-check" in result.get("status", ""), result)


# ---------------------------------------------------------------------------
# live: against the running uvicorn, real agent
# ---------------------------------------------------------------------------


def run_live(shipment_id: str, base_url: str, repeat: bool) -> None:
    import httpx

    from app.config import load_webhook_secret

    secret = load_webhook_secret()  # from YOUR .env, never printed
    try:
        health = httpx.get(f"{base_url}/health", timeout=5)
    except httpx.HTTPError as error:
        sys.exit(f"[ERROR] cannot reach {base_url} ({type(error).__name__}). "
                 "Is uvicorn running? uvicorn app.main:app --reload")
    check("server alive (GET /health -> 200)", health.status_code == 200, health.text)

    payload = {"shipment_id": shipment_id, "event_id": f"evt-live-{shipment_id}-{uuid.uuid4().hex[:8]}"}
    url = f"{base_url}/webhook/shipment-delayed"
    headers = {"X-Webhook-Secret": secret}
    print(f"\nSending notice {payload}")
    r = httpx.post(url, json=payload, headers=headers, timeout=30)
    check("new notice -> 202 accepted", r.status_code == 202, f"{r.status_code} {r.text}")
    if repeat:
        print("Sending the SAME notice again (a retry)")
        r = httpx.post(url, json=payload, headers=headers, timeout=30)
        check("same notice -> 200 already_processed", r.status_code == 200, f"{r.status_code} {r.text}")
    print("\nNow look at the uvicorn terminal: [agent] start ... [agent] done.")
    print("The agent works AFTER the 202; this script never sees its result.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate webhook notices (phase 4).")
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("checks", help="no LLM, no server, nothing sent")
    live = sub.add_parser("live", help="against your running uvicorn, real agent")
    live.add_argument("shipment_id", nargs="?", default="ENV-1001")
    live.add_argument("--url", default="http://127.0.0.1:8000")
    live.add_argument("--no-repeat", action="store_true", help="send the notice only once")
    args = parser.parse_args()

    if args.mode == "checks":
        run_checks()
    else:
        run_live(args.shipment_id.strip(), args.url.rstrip("/"), not args.no_repeat)

    print(f"\n{'ALL OK' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
    sys.exit(1 if FAILURES else 0)


if __name__ == "__main__":
    main()
