"""Deterministic mock extraction data.

Used whenever USE_MOCK is enabled, GEMINI_API_KEY is missing, or the Gemini
API call fails. Lets the rest of the team (and CI) develop/test against this
module without needing network access or an API key. The data below follows
the shared contract exactly and includes a deliberately low-confidence item
(#4) so downstream consumers can exercise the low-confidence warning path.
"""

from __future__ import annotations

from .models import (
    BOMItem,
    BoundingBox,
    Callout,
    ExtractedComponent,
    ExtractionResult,
    LeaderEndpoint,
)

MOCK_DRAWING_NUMBER = "ASM-001"
MOCK_REVISION = "B"

_MOCK_ROWS = [
    {
        "item_number": "1",
        "bubble_number": "1",
        "part_number": "PL-6061-014",
        "part_name": "Base Mounting Plate",
        "description": "Machined aluminum base plate",
        "quantity": 1,
        "material_specification": "Aluminum 6061-T6",
        "confidence_score": 0.95,
        "bbox": (120, 150, 210, 230),
        "leader_endpoint": (240, 280),
        "leader_line_status": "clear",
        "location_description": "leader terminates on base plate edge",
    },
    {
        "item_number": "2",
        "bubble_number": "2",
        "part_number": "SHCS-M6-025",
        "part_name": "Socket Head Cap Screw M6x25",
        "description": "Fastener, base to bracket",
        "quantity": 8,
        "material_specification": "Grade 12.9 Alloy Steel",
        "confidence_score": 0.92,
        "bbox": (340, 160, 400, 210),
        "leader_endpoint": (420, 250),
        "leader_line_status": "clear",
        "location_description": "leader terminates on fastener head",
    },
    {
        "item_number": "3",
        "bubble_number": "3",
        "part_number": "FB-M8-001",
        "part_name": "Hexagonal Flange Bolt M8",
        "description": "Flange bolt, bracket to frame",
        "quantity": 6,
        "material_specification": "Grade 8.8 Carbon Steel",
        "confidence_score": 0.97,
        "bbox": (185, 412, 230, 458),
        "leader_endpoint": (310, 520),
        "leader_line_status": "clear",
        "location_description": "leader terminates on upper-left bracket edge",
    },
    {
        "item_number": "4",
        "bubble_number": "4",
        "part_number": "BRK-2210",
        "part_name": "Support Bracket",
        "description": "Welded steel support bracket, partially obscured in view",
        "quantity": 2,
        "material_specification": "Steel A36",
        "confidence_score": 0.58,
        "bbox": (520, 300, 610, 380),
        "leader_endpoint": None,
        "leader_line_status": "unclear",
        "location_description": None,
    },
    {
        "item_number": "5",
        "bubble_number": "5",
        "part_number": "WSH-M8-STD",
        "part_name": "Flat Washer M8",
        "description": "Standard flat washer",
        "quantity": 6,
        "material_specification": "Stainless Steel 304",
        "confidence_score": 0.9,
        "bbox": (650, 420, 690, 460),
        "leader_endpoint": (710, 500),
        "leader_line_status": "clear",
        "location_description": "leader terminates near washer seat",
    },
]


def build_mock_extraction_result() -> ExtractionResult:
    """Construct a fresh, deterministic ExtractionResult matching the shared contract."""
    bom_items = [
        BOMItem(
            item_number=row["item_number"],
            part_number=row["part_number"],
            part_name=row["part_name"],
            description=row["description"],
            quantity=row["quantity"],
            material_specification=row["material_specification"],
            revision=None,
            confidence_score=row["confidence_score"],
        )
        for row in _MOCK_ROWS
    ]

    callouts = [
        Callout(
            bubble_number=row["bubble_number"],
            location_description=row["location_description"],
            bubble_bbox=BoundingBox(
                xmin=row["bbox"][0],
                ymin=row["bbox"][1],
                xmax=row["bbox"][2],
                ymax=row["bbox"][3],
            ),
            confidence_score=row["confidence_score"],
            leader_endpoint=(
                LeaderEndpoint(x=row["leader_endpoint"][0], y=row["leader_endpoint"][1])
                if row["leader_endpoint"] is not None
                else None
            ),
            leader_line_status=row["leader_line_status"],
        )
        for row in _MOCK_ROWS
    ]

    components = [
        ExtractedComponent(
            id=f"cmp_{row['item_number'].zfill(3)}",
            item_number=row["item_number"],
            bubble_number=row["bubble_number"],
            part_number=row["part_number"],
            # Strict rule: component name is the transcribed BOM description only.
            part_name=row["description"],
            quantity=row["quantity"],
            material_specification=row["material_specification"],
            confidence_score=row["confidence_score"],
            bounding_box=BoundingBox(
                xmin=row["bbox"][0],
                ymin=row["bbox"][1],
                xmax=row["bbox"][2],
                ymax=row["bbox"][3],
            ),
        )
        for row in _MOCK_ROWS
    ]

    warnings = [
        f"Low confidence extraction for item {row['item_number']} (confidence={row['confidence_score']:.2f})"
        for row in _MOCK_ROWS
        if row["confidence_score"] < 0.70
    ]
    warnings.append("Result generated from mock data (USE_MOCK=true; explicit development mode)")

    return ExtractionResult(
        drawing_number=MOCK_DRAWING_NUMBER,
        revision=MOCK_REVISION,
        bom_items=bom_items,
        callouts=callouts,
        components=components,
        extraction_warnings=warnings,
        extraction_source="mock",
    )
