"""End-to-end demo of the intelligence module.

Run from the ``bluprintai`` project root with::

    .venv\\Scripts\\python.exe -m intelligence.demo

Demonstrates the full pipeline:

    BOM + Callouts -> reconciliation -> validation -> procurement -> Excel/CSV

and writes its output (workbook, CSV, and the raw workspace JSON) to
``intelligence/demo_output/`` so it can be inspected directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import build_workspace, export_to_csv, export_to_excel
from .sample_data import SAMPLE_BOM, SAMPLE_CALLOUTS

OUTPUT_DIR = Path(__file__).parent / "demo_output"


def _print_section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def main() -> None:
    workspace = build_workspace(bom_data=SAMPLE_BOM, callout_data=SAMPLE_CALLOUTS)

    _print_section("Reconciliation + validation summary")
    for key, value in workspace["validation"]["summary"].items():
        print(f"  {key}: {value}")

    _print_section("Procurement summary")
    for key, value in workspace["procurement_summary"].items():
        print(f"  {key}: {value}")

    _print_section("Per-component status")
    item_number_by_id = {c["id"]: c["item_number"] for c in workspace["components"]}
    bubble_number_by_id = {c["id"]: c["bubble_number"] for c in workspace["components"]}
    for record in workspace["validation"]["issues"]:
        cid = record["component_id"]
        print(
            f"  {cid} (item={item_number_by_id[cid]!r}, "
            f"bubble={bubble_number_by_id[cid]!r}) -> {record['status']}"
        )
        for issue in record["issues"]:
            print(f"      [{issue['severity']}] {issue['type']}: {issue['message']}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    workspace_json_path = OUTPUT_DIR / "sample_workspace.json"
    workspace_json_path.write_text(json.dumps(workspace, indent=2), encoding="utf-8")

    excel_path = export_to_excel(workspace, str(OUTPUT_DIR / "BlueprintAI_BOM.xlsx"))
    csv_path = export_to_csv(workspace, str(OUTPUT_DIR / "BlueprintAI_BOM.csv"))

    _print_section("Output files")
    print(f"  {workspace_json_path}")
    print(f"  {excel_path}")
    print(f"  {csv_path}")


if __name__ == "__main__":
    main()
