"""HTTP server for the logistics agent (phase 4).

Run locally with:  uvicorn app.main:app --reload
Interactive docs:  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

app = FastAPI(
    title="Agente Logistica",
    description="Receives 'shipment delayed' webhooks and runs the agent.",
    version="0.4.0",
)


@app.get("/health")
def health() -> dict:
    """Liveness check: answers if the server is up. Render will use it in phase 5."""
    return {"status": "ok"}


@app.post("/webhook/shipment-delayed")
def shipment_delayed(payload: dict) -> dict:
    """Entry point for 'this shipment is delayed' notices.

    T2 placeholder: accepts any JSON object and echoes it back.
    Authentication (T3), validation (T3), background agent (T4)
    and idempotency (T5) come next.
    """
    return {"received": payload}
