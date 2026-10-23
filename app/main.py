"""HTTP server for the logistics agent (phase 4).

Run locally with:  uvicorn app.main:app --reload
Interactive docs:  http://127.0.0.1:8000/docs
"""

import secrets
import threading
import traceback
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent import describe_failed_calls, handle_shipment
from app.config import load_webhook_secret
from app.events import EventStoreError, register_event

# Read once at startup. If it is missing, the server refuses to start.
WEBHOOK_SECRET = load_webhook_secret()

app = FastAPI(
    title="Agente Logistica",
    description="Receives 'shipment delayed' webhooks and runs the agent.",
    version="0.4.0",
)


class ShipmentDelayedEvent(BaseModel):
    """Body of a 'shipment delayed' notice.

    Both fields are required, non-empty text (spaces are trimmed first).
    Extra fields are ignored, so the sender can add data later without
    breaking us. Wrong shape -> FastAPI answers 422 on its own.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    shipment_id: str = Field(min_length=1, examples=["ENV-1001"])
    event_id: str = Field(min_length=1, examples=["evt-2026-10-23-0001"])


def verify_secret(
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Dependency: runs BEFORE the endpoint. No secret or wrong one -> 401.

    The header X-Webhook-Secret arrives here as x_webhook_secret (FastAPI
    converts the name). compare_digest takes the same time whether the
    first or the last character is wrong, so timing reveals nothing.
    """
    if x_webhook_secret is None or not secrets.compare_digest(
        x_webhook_secret.encode(), WEBHOOK_SECRET.encode()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid webhook secret",
        )


@app.get("/health")
def health() -> dict:
    """Liveness check: answers if the server is up. Render will use it in phase 5."""
    return {"status": "ok"}


# One agent at a time. The agent keeps what it did in shared lists (the
# "outbox" in app/tools.py) and empties them at the start of each run: two
# agents at once would mix their outboxes and the guardrail would check the
# wrong data. Notices still get their 202 at once; only the agents queue up.
AGENT_LOCK = threading.Lock()


def run_agent_job(shipment_id: str, event_id: str) -> None:
    """Background job: runs AFTER the 202 has been sent.

    Nobody is waiting for this result (it goes to the sheet, email and
    Telegram), so any failure is caught and printed here: it must never
    take the server down. SystemExit too: config errors call sys.exit().
    """
    with AGENT_LOCK:
        print(f"[agent] start {shipment_id} (event {event_id})", flush=True)
        try:
            run, report = handle_shipment(shipment_id)
        except (Exception, SystemExit):
            print(f"[agent] FAILED {shipment_id} (event {event_id}):", flush=True)
            traceback.print_exc()
            return
        tools_used = ", ".join(call.name for call in run.tool_calls) or "none"
        print(f"[agent] done {shipment_id} (event {event_id}): "
              f"{run.iterations} rounds, model {run.model_used}, tools: {tools_used}", flush=True)
        for line in describe_failed_calls(run):
            print(f"[agent]   {line}", flush=True)
        if report.intervened:
            for item in report.corrections:
                print(f"[agent]   guardrail correction: {item}", flush=True)
            for item in report.discrepancies:
                print(f"[agent]   guardrail discrepancy: {item}", flush=True)


@app.post(
    "/webhook/shipment-delayed",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_secret)],
)
def shipment_delayed(
    event: ShipmentDelayedEvent, background_tasks: BackgroundTasks, response: Response
) -> dict:
    """Entry point for 'this shipment is delayed' notices.

    Only reached with the right secret (401 otherwise) and a valid body
    (422 otherwise). Then, by event_id:
    - already received -> 200 "already_processed", the agent does NOT run;
    - new -> recorded, 202 at once ("received, I'll handle it") and the
      agent runs in the background (the sender must not wait);
    - cannot check (Sheet down) -> 503 "retry later", the agent does NOT
      run (fail closed: better late than a duplicate email).
    """
    try:
        is_new = register_event(event.event_id, event.shipment_id)
    except EventStoreError as ex:
        print(f"[webhook] cannot check event {event.event_id}: {ex}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cannot check for duplicate events right now, retry later",
        ) from ex
    if not is_new:
        print(f"[webhook] duplicate event {event.event_id} ({event.shipment_id}): ignored", flush=True)
        response.status_code = status.HTTP_200_OK
        return {"status": "already_processed", "shipment_id": event.shipment_id, "event_id": event.event_id}
    background_tasks.add_task(run_agent_job, event.shipment_id, event.event_id)
    return {"status": "accepted", "shipment_id": event.shipment_id, "event_id": event.event_id}
