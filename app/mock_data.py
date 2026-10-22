"""In-memory fake data (phase 2), also the "memory" data source (phase 3a).

These two dicts play the role of the `envios` and `clientes` tabs of the
future Google Sheet. Field names match the Sheet columns exactly
(docs/contexto/05-modelo-datos.md), so in phase 3 only the data source
changes, not the tools or the agent.

Each test case triggers at most ONE escalation condition, so if the agent
fails we know exactly which rule it skipped.
"""

# Tab `envios`: key = shipment_id
SHIPMENTS: dict[str, dict] = {
    # Case 1: short delay, normal customer -> email + log
    "ENV-1001": {
        "shipment_id": "ENV-1001",
        "customer_id": "CLI-01",
        "origin": "Madrid",
        "destination": "Valencia",
        "carrier": "TransIberia",
        "expected_date": "2026-10-22",
        "status": "retrasado",
        "delay_hours": 6,
        "delay_reason": "Avería del camión",
        "new_eta": "2026-10-23",
    },
    # Case 2: delay > 24 h, normal customer -> email + escalation + log
    "ENV-1002": {
        "shipment_id": "ENV-1002",
        "customer_id": "CLI-02",
        "origin": "Madrid",
        "destination": "Bilbao",
        "carrier": "TransIberia",
        "expected_date": "2026-10-20",
        "status": "retrasado",
        "delay_hours": 30,
        "delay_reason": "Retención en el centro de distribución de Zaragoza",
        "new_eta": "",  # unknown -> email says we will inform as soon as we know
    },
    # Case 3: short delay, HIGH priority customer (English) -> email + escalation + log
    "ENV-1003": {
        "shipment_id": "ENV-1003",
        "customer_id": "CLI-03",
        "origin": "Barcelona",
        "destination": "Sevilla",
        "carrier": "RutaSur Express",
        "expected_date": "2026-10-21",
        "status": "retrasado",
        "delay_hours": 4,
        "delay_reason": "Congestión en el puerto de Barcelona",
        "new_eta": "2026-10-22",
    },
    # Case 4: customer WITHOUT email -> no email, escalation + log (incomplete data)
    "ENV-1004": {
        "shipment_id": "ENV-1004",
        "customer_id": "CLI-04",
        "origin": "Zaragoza",
        "destination": "A Coruña",
        "carrier": "NorteCarga",
        "expected_date": "2026-10-21",
        "status": "retrasado",
        "delay_hours": 10,
        "delay_reason": "Cierre temporal de la autovía A-6 por nieve",
        "new_eta": "",
    },
    # Case 5: ENV-9999 is intentionally NOT here -> "not found" error
    # Case 6: in transit, not delayed -> log no_action
    "ENV-1005": {
        "shipment_id": "ENV-1005",
        "customer_id": "CLI-01",
        "origin": "Valencia",
        "destination": "Madrid",
        "carrier": "TransIberia",
        "expected_date": "2026-10-23",
        "status": "en_transito",
        "delay_hours": 0,
        "delay_reason": "",
        "new_eta": "",
    },
    # Case 7 (phase 2b): short delay, normal customer, but the goods were STOLEN.
    # No rule in rules.py covers it -> escalation by judgment (rule 6), no email,
    # draft for the human. The reason carries internal details on purpose.
    "ENV-1006": {
        "shipment_id": "ENV-1006",
        "customer_id": "CLI-01",
        "origin": "Madrid",
        "destination": "Toledo",
        "carrier": "TransIberia",
        "expected_date": "2026-10-23",
        "status": "retrasado",
        "delay_hours": 6,
        "delay_reason": (
            "Camión robado con la mercancía; denuncia presentada en la Guardia Civil "
            "de Alcalá de Henares. Se desconoce si se recuperará la carga."
        ),
        "new_eta": "",
    },
}

# Tab `clientes`: key = customer_id
CUSTOMERS: dict[str, dict] = {
    "CLI-01": {
        "customer_id": "CLI-01",
        "name": "Frutas Levante SL",
        "contact_email": "pedidos@frutaslevante.example.com",
        "priority": "normal",
        "language": "es",
    },
    "CLI-02": {
        "customer_id": "CLI-02",
        "name": "Distribuciones Norte SL",
        "contact_email": "logistica@distribucionesnorte.example.com",
        "priority": "normal",
        "language": "es",
    },
    "CLI-03": {
        "customer_id": "CLI-03",
        "name": "Iberian Pharma Ltd",
        "contact_email": "supply@iberianpharma.example.com",
        "priority": "alta",
        "language": "en",
    },
    "CLI-04": {
        "customer_id": "CLI-04",
        "name": "Conservas Atlántico SA",
        "contact_email": "",  # missing on purpose (case 4)
        "priority": "normal",
        "language": "es",
    },
}


# ---------------------------------------------------------------------------
# Adapter (phase 3a): the same 3 functions as app/integrations/sheets.py,
# so the tools can use either source without knowing which one it is.
# ---------------------------------------------------------------------------


def find_shipment(shipment_id: str) -> dict | None:
    """One shipment as a dict (a copy, so callers can't modify our data)."""
    shipment = SHIPMENTS.get(shipment_id)
    return dict(shipment) if shipment else None


def find_customer(customer_id: str) -> dict | None:
    """One customer as a dict (a copy), or None."""
    customer = CUSTOMERS.get(customer_id)
    return dict(customer) if customer else None


def append_log(row: dict) -> None:
    """Nothing to persist: in memory, the outbox (tools.ACTION_LOG) is the log."""
