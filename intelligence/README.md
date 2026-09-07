# intelligence/ -- Person 5's module

Reconciles BOM data with drawing callouts, validates the result, attaches
mock procurement estimates, and exports Excel/CSV. Pure Python + pandas +
openpyxl -- no Streamlit, no Gemini/vision API, no network calls. Works
standalone on plain dicts/lists.

## Setup

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r intelligence/requirements.txt
```

(A `.venv` already exists in this project root with both dependencies
installed.)

## Run the demo

```bash
.venv\Scripts\python.exe -m intelligence.demo
```

Prints the reconciliation/validation/procurement summary to the console
and writes `BlueprintAI_BOM.xlsx`, `BlueprintAI_BOM.csv`, and
`sample_workspace.json` to `intelligence/demo_output/`.

## Run the tests

```bash
.venv\Scripts\python.exe -m unittest discover -s intelligence/tests -t . -v
```

37 tests, no network access, no external services required.

## Public API

```python
from intelligence import build_workspace, export_to_excel, export_to_csv

workspace = build_workspace(bom_data=bom, callout_data=callouts)
export_to_excel(workspace, "BlueprintAI_BOM.xlsx")
export_to_csv(workspace, "BlueprintAI_BOM.csv")
```

`build_workspace` also accepts `procurement_data` (a dict of part-number
-> catalog entry overrides/extensions on top of the built-in mock
catalog) and `confidence_threshold` (default `0.75`, see
`validation.DEFAULT_CONFIDENCE_THRESHOLD`).

Lower-level functions (`reconcile_bom_and_callouts`, `validate_workspace`,
`calculate_procurement`) are also exported from `intelligence/__init__.py`
if the UI layer ever needs to run a step in isolation.

## Module layout

| File | Responsibility |
| --- | --- |
| `models.py` | `Component`, `ValidationIssue`, `ComponentValidation` dataclasses |
| `normalization.py` | Deterministic identifier normalization (`"Item 3"` -> `"3"`) |
| `reconciliation.py` | Matches BOM rows to callouts, builds unified components |
| `validation.py` | Per-component issues/status + workspace-level summary |
| `procurement.py` | Mock catalog lookup + cost calculation |
| `export.py` | Excel (3-sheet, styled) and CSV export |
| `pipeline.py` | `build_workspace` -- wires everything together |
| `sample_data.py` | Realistic sample BOM/callouts covering every case |
| `demo.py` | Runnable end-to-end demonstration |
| `tests/` | 37 unittest cases across all of the above |

## Design decisions on ambiguous parts of the spec

The spec left a few things open to implementation choice. Documenting
them here so they're easy to challenge/change during integration:

- **Identifier normalization** matches only when a string contains
  *exactly one* run of digits (`"Bubble-3"`, `"Item 3"`, `"03"` all
  normalize to `"3"`). Anything with zero or multiple digit runs
  (`"3-4"`, `"N/A"`) is treated as ambiguous and flagged
  `ambiguous_identifier` rather than guessed at.
- **Unmatched BOM rows and unmatched callouts still become components.**
  A BOM item with no callout produces a component with `bubble_number:
  null` and `link_status "bom_only"` (surfaced as validation status
  `missing_callout`), and vice versa. Nothing observed on input is
  silently dropped from the output.
- **Duplicate identifiers on either side** are paired with the other
  side by original list order, up to the shorter list's length; any
  extra rows become unmatched components. All rows sharing the
  duplicated identifier are flagged `duplicate_bom_item` /
  `duplicate_callout`, whether or not they ended up paired.
- **Combined confidence** is `min(bom_confidence, callout_confidence)`
  when both exist, the single available value when only one exists, and
  `null` (flagged `confidence_unavailable`) when neither exists.
- **Component status** collapses to one of five values (`linked`,
  `review_required`, `missing_callout`, `missing_bom_item`, `invalid`).
  A component that matched but has *any* warning/info/error issue
  (low confidence, missing field, duplicate flag, etc.) is
  `review_required` rather than `linked` -- callers that only care about
  "is this ready to export as-is" can check for `status == "linked"`.
- **Stable IDs** (`cmp_001`, `cmp_002`, ...) are assigned in a fixed
  order: matched components sorted by numeric key, then BOM-only, then
  callout-only, then ambiguous-BOM, then ambiguous-callout. Given the
  same input, IDs are always the same across runs.

## Integration notes for Persons 1 & 2

- Import with `from intelligence import build_workspace`, pass Person
  4's extraction output as `bom_data` / `callout_data` (plain lists of
  dicts matching `contracts/README.md`), and consume the returned dict
  directly -- it's plain JSON, no custom classes.
- `workspace["components"]` is the flat list to render in a table.
- `workspace["validation"]["issues"]` is parallel to `components` (one
  entry per component, same `id`/`component_id`) if you want to render
  inline review flags.
- Nothing in this module reads from or writes to disk except
  `export_to_excel`/`export_to_csv`, and neither is called unless you
  call them.

## Known limitations

- Procurement data is a small hand-written mock catalog (6 parts) --
  not a real supplier integration. Every procurement figure is labeled
  `"estimated": true, "mock_data": true`.
- Duplicate-identifier pairing (by original list order) is a
  documented convention, not a guess at which physical part is "really"
  which -- a human should resolve genuine duplicates.
- Bounding boxes are structurally validated (must have all four of
  `xmin`/`ymin`/`xmax`/`ymax` as numbers) but not range-checked against
  image dimensions, since this module never sees the image.
