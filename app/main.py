"""HTTP server for the logistics agent (phase 4).

Run locally with:  uvicorn app.main:app --reload
Interactive docs:  http://127.0.0.1:8000/docs
"""

import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.config import load_webhook_secret

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


@app.post("/webhook/shipment-delayed", dependencies=[Depends(verify_secret)])
def shipment_delayed(event: ShipmentDelayedEvent) -> dict:
    """Entry point for 'this shipment is delayed' notices.

    T3: only reached with the right secret and a valid body; echoes it.
    Background agent + 202 (T4) and idempotency (T5) come next.
    """
    return {"received": event.model_dump()}
