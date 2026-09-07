"""Realistic sample BOM / drawing-callout data for local development,
demos, and tests -- no dependency on Person 3/4's real pipeline.

Deliberately covers every case the validation engine needs to exercise:
    item 1, 2         -> clean matches
    item "03" / "3"   -> matched via leading-zero normalization
    bubble "Bubble-2" -> matched via text-prefix normalization
    item 4            -> matched, low combined confidence (0.55)
    item 5            -> matched, part number has no catalog price
    item "6" (x2)     -> duplicate BOM item number
    bubble "7" (x2)   -> one BOM row, two drawing balloons for it (a
                         repeated physical instance, e.g. two identical
                         fasteners) -- both matched, not flagged as a
                         duplicate; see intelligence/reconciliation.py
    item 9            -> BOM item with no drawing callout
    bubble 14         -> drawing callout with no BOM item
    item 10           -> matched, missing quantity
    "Item 3-4"        -> ambiguous identifier (two digit runs), unmatchable
"""

from __future__ import annotations

SAMPLE_BOM: list[dict] = [
    {
        "item_number": "1",
        "part_number": "FB-M8-001",
        "part_name": "Hexagonal Flange Bolt M8",
        "quantity": 6,
        "material_specification": "Grade 8.8 Carbon Steel",
        "confidence_score": 0.97,
    },
    {
        "item_number": "2",
        "part_number": "WSH-M8-002",
        "part_name": "Flat Washer M8",
        "quantity": 12,
        "material_specification": "Zinc-Plated Steel",
        "confidence_score": 0.94,
    },
    {
        "item_number": "03",  # leading zero -> normalizes to "3"
        "part_number": "BRK-STD-100",
        "part_name": "Standard Mounting Bracket",
        "quantity": 2,
        "material_specification": "6061 Aluminum",
        "confidence_score": 0.96,
    },
    {
        "item_number": "4",
        "part_number": "BRG-6202-Z",
        "part_name": "Ball Bearing 6202-Z",
        "quantity": 4,
        "material_specification": "Chrome Steel",
        "confidence_score": 0.55,  # low confidence
    },
    {
        "item_number": "5",
        "part_number": "CUST-PLATE-099",  # not in the mock procurement catalog
        "part_name": "Custom Mounting Plate",
        "quantity": 3,
        "material_specification": None,  # missing material -> info flag
        "confidence_score": 0.89,
    },
    {
        "item_number": "6",
        "part_number": "GSK-RUB-045",
        "part_name": "Rubber Gasket",
        "quantity": 8,
        "material_specification": "Nitrile Rubber",
        "confidence_score": 0.92,
    },
    {
        "item_number": "6",  # duplicate BOM item number
        "part_number": "GSK-RUB-045-ALT",
        "part_name": "Rubber Gasket (Rev B)",
        "quantity": 8,
        "material_specification": "Nitrile Rubber",
        "confidence_score": 0.90,
    },
    {
        "item_number": "7",
        "part_number": "SHF-ST-303",
        "part_name": "Drive Shaft",
        "quantity": 1,
        "material_specification": "Stainless Steel 303",
        "confidence_score": 0.93,
    },
    {
        "item_number": "9",  # no matching callout below -> missing_callout
        "part_number": "SCR-M4-010",
        "part_name": "Socket Head Screw M4x10",
        "quantity": 10,
        "material_specification": "Grade 8.8 Carbon Steel",
        "confidence_score": 0.91,
    },
    {
        "item_number": "10",
        "part_number": "PIN-DWL-020",
        "part_name": "Dowel Pin",
        # quantity intentionally omitted -> missing_field flag
        "material_specification": "Steel",
        "confidence_score": 0.88,
    },
    {
        "item_number": "Item 3-4",  # two digit runs -> ambiguous, unmatchable
        "part_number": "AMB-000",
        "part_name": "Ambiguous Label Part",
        "quantity": 1,
        "material_specification": None,
        # confidence intentionally omitted -> confidence_unavailable flag
    },
]

SAMPLE_CALLOUTS: list[dict] = [
    {
        "bubble_number": "1",
        "location_description": "Upper-left mounting bracket",
        "bounding_box": {"xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458},
        "confidence_score": 0.95,
    },
    {
        "bubble_number": "Bubble-2",  # text-prefixed -> normalizes to "2"
        "location_description": "Adjacent to bolt callout 1",
        "bounding_box": {"xmin": 240, "ymin": 412, "xmax": 285, "ymax": 458},
        "confidence_score": 0.93,
    },
    {
        "bubble_number": "3",
        "location_description": "Center bracket mount",
        "bounding_box": {"xmin": 300, "ymin": 400, "xmax": 350, "ymax": 445},
        "confidence_score": 0.96,
    },
    {
        "bubble_number": "4",
        "location_description": "Lower shaft assembly",
        "bounding_box": {"xmin": 150, "ymin": 520, "xmax": 200, "ymax": 565},
        "confidence_score": 0.90,
    },
    {
        "bubble_number": "5",
        "location_description": "Right side custom mount",
        "bounding_box": {"xmin": 400, "ymin": 300, "xmax": 450, "ymax": 345},
        "confidence_score": 0.91,
    },
    {
        "bubble_number": "6",
        "location_description": "Gasket seal area",
        "bounding_box": {"xmin": 260, "ymin": 300, "xmax": 300, "ymax": 340},
        "confidence_score": 0.92,
    },
    {
        "bubble_number": "7",
        "location_description": "Drive shaft coupling (instance 1)",
        "bounding_box": {"xmin": 500, "ymin": 250, "xmax": 545, "ymax": 295},
        "confidence_score": 0.94,
    },
    {
        "bubble_number": "7",  # second balloon for the same BOM item -- matched, not a duplicate
        "location_description": "Drive shaft coupling (instance 2)",
        "bounding_box": {"xmin": 505, "ymin": 255, "xmax": 550, "ymax": 300},
        "confidence_score": 0.85,
    },
    {
        "bubble_number": "10",
        "location_description": "Dowel pin location",
        "bounding_box": {"xmin": 90, "ymin": 180, "xmax": 130, "ymax": 220},
        "confidence_score": 0.90,
    },
    {
        "bubble_number": "14",  # no matching BOM item -> missing_bom_item
        "location_description": "Unidentified fastener, bottom edge",
        "bounding_box": {"xmin": 610, "ymin": 600, "xmax": 650, "ymax": 640},
        "confidence_score": 0.80,
    },
]

# Optional demonstration of overriding/extending the built-in mock
# procurement catalog (see procurement.DEFAULT_PROCUREMENT_CATALOG).
# Not applied by default -- pass it explicitly to build_workspace(...,
# procurement_data=SAMPLE_PROCUREMENT_OVERRIDES) if you want item 5
# ("CUST-PLATE-099") to have a price instead of demonstrating the
# no-price case.
SAMPLE_PROCUREMENT_OVERRIDES: dict[str, dict] = {
    "CUST-PLATE-099": {
        "estimated_unit_cost_usd": 5.60,
        "supplier_source": "MetalWorks Fabrication",
        "stock_status": "Made to Order",
    },
}
