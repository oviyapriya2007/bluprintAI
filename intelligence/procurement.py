"""Mock procurement enrichment.

Hackathon scope: no real supplier API. ``DEFAULT_PROCUREMENT_CATALOG``
is a small, deterministic, hand-written dataset keyed by part number, with
suppliers based in Tamil Nadu, India (falling back to elsewhere in India
if a Tamil Nadu supplier isn't appropriate for a given part -- none of the
current entries need that fallback). All prices are mock estimates in INR.
Every figure this module produces is an *estimate* -- callers must not
present it as a real quotation (see ``ESTIMATE_NOTE``).
"""

from __future__ import annotations

from typing import Optional

from .models import Component

ESTIMATE_NOTE = (
    "Mock/estimated procurement data for demonstration purposes only. "
    "Not a real quotation."
)

# Deterministic mock catalog. Part numbers not listed here simply have
# no pricing data available -- that's a normal, non-fatal outcome.
# Supplier names carry their city so the supplier's Tamil Nadu location is
# visible directly in the existing single "supplier_source" field, with no
# contract/schema change. Prices are mock INR estimates.
DEFAULT_PROCUREMENT_CATALOG: dict[str, dict] = {
    "FB-M8-001": {
        "estimated_unit_cost_usd": 35.00,
        "supplier_source": "Chennai Fastener Works",
        "stock_status": "In Stock",
    },
    "WSH-M8-002": {
        "estimated_unit_cost_usd": 6.00,
        "supplier_source": "Coimbatore Precision Components",
        "stock_status": "In Stock",
    },
    "BRK-STD-100": {
        "estimated_unit_cost_usd": 950.00,
        "supplier_source": "Salem Metal Fabricators",
        "stock_status": "In Stock",
    },
    "BRG-6202-Z": {
        "estimated_unit_cost_usd": 240.00,
        "supplier_source": "Tiruchirappalli Bearing Traders",
        "stock_status": "Low Stock",
    },
    "GSK-RUB-045": {
        "estimated_unit_cost_usd": 85.00,
        "supplier_source": "Erode Rubber & Seals Co.",
        "stock_status": "In Stock",
    },
    "SHF-ST-303": {
        "estimated_unit_cost_usd": 640.00,
        "supplier_source": "Hosur Precision Engineering",
        "stock_status": "Backordered",
    },
    # Parts referenced by vision-extractor's mock extraction data
    # (vision-extractor/vision_extractor/mock_data.py), so the full
    # document-processor -> vision-extractor -> intelligence demo has
    # realistic procurement coverage out of the box.
    "PL-6061-014": {
        "estimated_unit_cost_usd": 1650.00,
        "supplier_source": "Coimbatore Metal Fabricators",
        "stock_status": "In Stock",
    },
    "SHCS-M6-025": {
        "estimated_unit_cost_usd": 11.00,
        "supplier_source": "Tiruppur Fastener Industries",
        "stock_status": "In Stock",
    },
    "WSH-M8-STD": {
        "estimated_unit_cost_usd": 5.00,
        "supplier_source": "Madurai Engineering Supplies",
        "stock_status": "In Stock",
    },
    # Parts from the "Bearing Housing Assembly" sample drawing used to
    # develop/verify the backend/ hybrid pipeline (document-processor's
    # own vision-extractor/examples fixture and ad hoc test uploads).
    "HB-M8-001": {
        "estimated_unit_cost_usd": 8.00,
        "supplier_source": "Chennai Fastener Works",
        "stock_status": "In Stock",
    },
    "WS-M8-001": {
        "estimated_unit_cost_usd": 3.00,
        "supplier_source": "Coimbatore Precision Components",
        "stock_status": "In Stock",
    },
    "BH-001": {
        "estimated_unit_cost_usd": 420.00,
        "supplier_source": "Salem Metal Fabricators",
        "stock_status": "In Stock",
    },
    "BR-6204": {
        "estimated_unit_cost_usd": 260.00,
        "supplier_source": "Tiruchirappalli Bearing Traders",
        "stock_status": "In Stock",
    },
    "SH-001": {
        "estimated_unit_cost_usd": 150.00,
        "supplier_source": "Hosur Precision Engineering",
        "stock_status": "In Stock",
    },
    "EC-001": {
        "estimated_unit_cost_usd": 180.00,
        "supplier_source": "Salem Metal Fabricators",
        "stock_status": "Low Stock",
    },
    "NT-M8-001": {
        "estimated_unit_cost_usd": 4.00,
        "supplier_source": "Chennai Fastener Works",
        "stock_status": "In Stock",
    },
}


def _empty_procurement_record(note: str) -> dict:
    return {
        "estimated_unit_cost_usd": None,
        "estimated_total_cost_usd": None,
        "supplier_source": None,
        "stock_status": "unknown",
        "estimated": True,
        "mock_data": True,
        "note": note,
    }


def _enrich_component(component: Component, catalog: dict[str, dict]) -> dict:
    """Compute procurement_data for a single component. Never raises --
    any missing/invalid input just produces a partial record with an
    explanatory note, so one bad row can't take down the whole batch."""
    if not component.part_number:
        return _empty_procurement_record("No part number available for pricing lookup.")

    catalog_entry = catalog.get(component.part_number)
    if not catalog_entry:
        return _empty_procurement_record(
            f"No supplier pricing found for part number '{component.part_number}'."
        )

    unit_cost = catalog_entry.get("estimated_unit_cost_usd")
    if not isinstance(unit_cost, (int, float)) or isinstance(unit_cost, bool) or unit_cost < 0:
        return _empty_procurement_record(
            f"Catalog entry for '{component.part_number}' has no valid unit cost."
        )

    quantity = component.quantity
    total_cost: Optional[float]
    note = ESTIMATE_NOTE
    if quantity is None or not isinstance(quantity, int) or quantity <= 0:
        total_cost = None
        note = f"{ESTIMATE_NOTE} Total cost omitted: quantity is missing or invalid."
    else:
        total_cost = round(unit_cost * quantity, 2)

    return {
        "estimated_unit_cost_usd": round(float(unit_cost), 2),
        "estimated_total_cost_usd": total_cost,
        "supplier_source": catalog_entry.get("supplier_source"),
        "stock_status": catalog_entry.get("stock_status", "unknown"),
        "estimated": True,
        "mock_data": True,
        "note": note,
    }


def calculate_procurement(
    components: list[Component], catalog: Optional[dict[str, dict]] = None
) -> dict:
    """Attach ``procurement_data`` to every component (in place) and
    return a workspace-level cost summary.

    ``catalog`` overrides/extends ``DEFAULT_PROCUREMENT_CATALOG`` by
    part number; pass a partial dict to add or override just a few
    parts without losing the defaults.
    """
    merged_catalog = dict(DEFAULT_PROCUREMENT_CATALOG)
    if catalog:
        merged_catalog.update(catalog)

    total_cost = 0.0
    items_with_price = 0
    items_without_price = 0

    for component in components:
        procurement_data = _enrich_component(component, merged_catalog)
        component.procurement_data = procurement_data
        if procurement_data.get("estimated_unit_cost_usd") is not None:
            items_with_price += 1
        else:
            items_without_price += 1
        if procurement_data.get("estimated_total_cost_usd") is not None:
            total_cost += procurement_data["estimated_total_cost_usd"]

    return {
        "currency": "INR",
        "estimated_total_cost_usd": round(total_cost, 2),
        "items_with_price": items_with_price,
        "items_without_price": items_without_price,
        "estimated": True,
        "mock_data": True,
        "note": ESTIMATE_NOTE,
    }
