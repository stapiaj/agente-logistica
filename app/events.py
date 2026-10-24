"""Idempotency of the webhook: never process the same notice twice (phase 4, T5).

A notice can arrive more than once: the sender retries when the answer gets
lost or is slow (Render waking up), or someone sets "retrasado" twice. Every
notice carries an event_id; we remember the ones already received.

Two layers:
- Memory (_seen): instant. With the lock, it stops two identical notices
  arriving at the same time (both would read the Sheet before either wrote).
- The data source (DATA_SOURCE): the Sheet tab `eventos`, which survives
  restarts. With DATA_SOURCE=memory it is just a list (local tests).

The event is recorded WHEN IT IS RECEIVED, before the agent runs: if the
agent fails halfway, a retry does NOT run it again (at most once). A
duplicate email to a customer is worse than a case left for a human (the
failure is printed and logged). If we cannot check (Sheet down), we FAIL
CLOSED: the caller answers 503 and the agent does not run.
"""

import threading
from datetime import datetime, timezone

from app.data_source import get_data_source

_seen: set[str] = set()
_lock = threading.Lock()


class EventStoreError(Exception):
    """We cannot check or record events right now (e.g. the Sheet is down)."""


def register_event(event_id: str, shipment_id: str) -> bool:
    """True = new event, recorded now (run the agent). False = already received."""
    event_id = event_id.strip()
    with _lock:
        if event_id in _seen:
            return False
        try:
            source = get_data_source()
            if source.find_event(event_id):
                _seen.add(event_id)  # seen before a restart: remember it again
                return False
            source.append_event({
                "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "event_id": event_id,
                "shipment_id": shipment_id,
            })
        except (Exception, SystemExit) as ex:  # SystemExit: config errors call sys.exit()
            raise EventStoreError(f"{type(ex).__name__}: {ex}") from ex
        _seen.add(event_id)
        return True
