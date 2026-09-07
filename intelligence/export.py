"""Excel and CSV export for a workspace dict (the output of
``pipeline.build_workspace``).

Uses openpyxl directly (not pandas.ExcelWriter) so we have full control
over styling, freeze panes, and number formats for a polished demo.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
CURRENCY_FORMAT = "₹#,##0.00"  # Indian Rupee (INR)
PERCENT_FORMAT = "0%"

BOM_COLUMNS = [
    ("Item Number", "item_number", None, 14),
    ("Part Number", "part_number", None, 16),
    ("Part Name", "part_name", None, 28),
    ("Description", "description", None, 24),
    ("Quantity", "quantity", None, 10),
    ("Material", "material_specification", None, 24),
    ("Revision", "revision", None, 10),
    ("Drawing Location", "location_description", None, 26),
    ("Confidence", "confidence_score", PERCENT_FORMAT, 12),
    ("Unit Cost (₹)", "estimated_unit_cost_usd", CURRENCY_FORMAT, 16),
    ("Estimated Total (₹)", "estimated_total_cost_usd", CURRENCY_FORMAT, 16),
    ("Supplier", "supplier_source", None, 22),
    ("Stock Status", "stock_status", None, 14),
]

PROCUREMENT_COLUMNS = [
    ("Item Number", 14),
    ("Part Name", 28),
    ("Quantity", 10),
    ("Unit Cost (₹)", 16),
    ("Estimated Total (₹)", 18),
    ("Supplier", 22),
    ("Availability", 16),
]

ISSUES_COLUMNS = [
    ("Component ID", 14),
    ("Item Number", 14),
    ("Issue Type", 20),
    ("Severity", 12),
    ("Message", 50),
    ("Status", 18),
]


def _write_header(ws: Worksheet, headers: list[str], widths: list[int]) -> None:
    for col_index, (title, width) in enumerate(zip(headers, widths), start=1):
        cell = ws.cell(row=1, column=col_index, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(col_index)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _flat_component(component: dict) -> dict:
    procurement = component.get("procurement_data") or {}
    return {
        "item_number": component.get("item_number"),
        "part_number": component.get("part_number"),
        "part_name": component.get("part_name"),
        "description": component.get("description"),
        "quantity": component.get("quantity"),
        "material_specification": component.get("material_specification"),
        "revision": component.get("revision"),
        "location_description": component.get("location_description"),
        "confidence_score": component.get("confidence_score"),
        "estimated_unit_cost_usd": procurement.get("estimated_unit_cost_usd"),
        "estimated_total_cost_usd": procurement.get("estimated_total_cost_usd"),
        "supplier_source": procurement.get("supplier_source"),
        "stock_status": procurement.get("stock_status"),
    }


def _build_bom_sheet(ws: Worksheet, components: list[dict]) -> None:
    headers = [c[0] for c in BOM_COLUMNS]
    widths = [c[3] for c in BOM_COLUMNS]
    _write_header(ws, headers, widths)

    for row_index, component in enumerate(components, start=2):
        flat = _flat_component(component)
        for col_index, (_, field, number_format, _) in enumerate(BOM_COLUMNS, start=1):
            value = flat.get(field)
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if number_format and value is not None:
                cell.number_format = number_format


def _build_procurement_sheet(ws: Worksheet, components: list[dict]) -> None:
    headers = [c[0] for c in PROCUREMENT_COLUMNS]
    widths = [c[1] for c in PROCUREMENT_COLUMNS]
    _write_header(ws, headers, widths)

    row_index = 2
    for component in components:
        procurement = component.get("procurement_data") or {}
        if not procurement:
            continue
        ws.cell(row=row_index, column=1, value=component.get("item_number"))
        ws.cell(row=row_index, column=2, value=component.get("part_name"))
        ws.cell(row=row_index, column=3, value=component.get("quantity"))
        unit_cell = ws.cell(
            row=row_index, column=4, value=procurement.get("estimated_unit_cost_usd")
        )
        total_cell = ws.cell(
            row=row_index, column=5, value=procurement.get("estimated_total_cost_usd")
        )
        if procurement.get("estimated_unit_cost_usd") is not None:
            unit_cell.number_format = CURRENCY_FORMAT
        if procurement.get("estimated_total_cost_usd") is not None:
            total_cell.number_format = CURRENCY_FORMAT
        ws.cell(row=row_index, column=6, value=procurement.get("supplier_source"))
        ws.cell(row=row_index, column=7, value=procurement.get("stock_status"))
        row_index += 1


def _build_issues_sheet(ws: Worksheet, components: list[dict], validation: dict) -> None:
    headers = [c[0] for c in ISSUES_COLUMNS]
    widths = [c[1] for c in ISSUES_COLUMNS]
    _write_header(ws, headers, widths)

    item_number_by_id = {c.get("id"): c.get("item_number") for c in components}

    row_index = 2
    for record in validation.get("issues", []):
        component_id = record.get("component_id")
        status = record.get("status")
        issues = record.get("issues") or []
        if not issues:
            ws.cell(row=row_index, column=1, value=component_id)
            ws.cell(row=row_index, column=2, value=item_number_by_id.get(component_id))
            ws.cell(row=row_index, column=3, value="")
            ws.cell(row=row_index, column=4, value="")
            ws.cell(row=row_index, column=5, value="No issues.")
            ws.cell(row=row_index, column=6, value=status)
            row_index += 1
            continue
        for issue in issues:
            ws.cell(row=row_index, column=1, value=component_id)
            ws.cell(row=row_index, column=2, value=item_number_by_id.get(component_id))
            ws.cell(row=row_index, column=3, value=issue.get("type"))
            ws.cell(row=row_index, column=4, value=issue.get("severity"))
            ws.cell(row=row_index, column=5, value=issue.get("message"))
            ws.cell(row=row_index, column=6, value=status)
            row_index += 1


def export_to_excel(workspace: dict, output_path: str = "BlueprintAI_BOM.xlsx") -> str:
    """Write ``workspace`` (as returned by ``build_workspace``) to a
    3-sheet Excel workbook. Returns the path written to."""
    components = workspace.get("components", [])
    validation = workspace.get("validation", {"summary": {}, "issues": []})

    workbook = Workbook()

    bom_sheet = workbook.active
    bom_sheet.title = "BOM"
    _build_bom_sheet(bom_sheet, components)

    procurement_sheet = workbook.create_sheet("Procurement Estimate")
    _build_procurement_sheet(procurement_sheet, components)

    issues_sheet = workbook.create_sheet("AI Validation Issues")
    _build_issues_sheet(issues_sheet, components, validation)

    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    workbook.save(output_path)
    return output_path


def export_to_csv(workspace: dict, output_path: str = "BlueprintAI_BOM.csv") -> str:
    """Write the flattened BOM view of ``workspace`` to a single CSV
    file (one row per component, no nested JSON in cells). Returns the
    path written to."""
    components = workspace.get("components", [])
    headers = [c[0] for c in BOM_COLUMNS]
    fields = [c[1] for c in BOM_COLUMNS]

    rows = [_flat_component(component) for component in components]
    frame = pd.DataFrame(rows, columns=fields)
    frame.columns = headers
    # Pandas upcasts an int column with any None to float64 (e.g. "6"
    # becomes "6.0"); nullable Int64 keeps whole quantities readable.
    frame["Quantity"] = frame["Quantity"].astype("Int64")

    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    frame.to_csv(output_path, index=False)
    return output_path
