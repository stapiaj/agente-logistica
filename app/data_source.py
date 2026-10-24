"""Choose where the data lives, from DATA_SOURCE in .env (phase 3a).

Both sources are ADAPTERS with the same 3 functions and the same shape of
data: find_shipment(id), find_customer(id), append_log(row), plus
find_event(id) and append_event(row) for the webhook (phase 4). The callers
don't know which one they got, so the agent and rules.py never notice the
change. A new source (an ERP, a database) only needs a module with these
functions and one more line here.
"""

from types import ModuleType

from app.config import load_data_source


def get_data_source() -> ModuleType:
    """Return the module that implements the 3 adapter functions."""
    if load_data_source() == "sheets":
        # Imported only when needed: memory mode works without gspread
        # and without the service account key.
        from app.integrations import sheets

        return sheets
    from app import mock_data

    return mock_data
