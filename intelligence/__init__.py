"""BlueprintAI intelligence module (Person 5).

Reconciles Vision-AI BOM extraction with drawing callouts, validates the
result, attaches mock procurement estimates, and exports Excel/CSV.
Works standalone on plain dicts/lists -- no dependency on Streamlit, the
document processor, or the vision extractor.

Typical usage::

    from intelligence import build_workspace, export_to_excel, export_to_csv

    workspace = build_workspace(bom_data=bom, callout_data=callouts)
    export_to_excel(workspace, "BlueprintAI_BOM.xlsx")
    export_to_csv(workspace, "BlueprintAI_BOM.csv")
"""

from .export import export_to_csv, export_to_excel
from .pipeline import build_workspace
from .procurement import DEFAULT_PROCUREMENT_CATALOG, calculate_procurement
from .reconciliation import ReconciliationResult, reconcile_bom_and_callouts
from .validation import DEFAULT_CONFIDENCE_THRESHOLD, validate_workspace

__all__ = [
    "build_workspace",
    "reconcile_bom_and_callouts",
    "ReconciliationResult",
    "validate_workspace",
    "calculate_procurement",
    "export_to_excel",
    "export_to_csv",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_PROCUREMENT_CATALOG",
]

__version__ = "1.0.0"
