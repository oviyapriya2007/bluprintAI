# BlueprintAI shared data contract

This documents the JSON shapes that flow between modules, as agreed in
the team's architecture. It reflects what the `intelligence/` module
(Person 5) actually consumes and produces. Field names below
(`item_number`, `bubble_number`, `bounding_box` with `xmin`/`ymin`/
`xmax`/`ymax`, `confidence_score`) are load-bearing and must not be
renamed by any module.

## Input: BOM data (from Person 4's Vision AI extraction)

```json
[
  {
    "item_number": "3",
    "part_number": "FB-M8-001",
    "part_name": "Hexagonal Flange Bolt M8",
    "quantity": 6,
    "material_specification": "Grade 8.8 Carbon Steel",
    "confidence_score": 0.97
  }
]
```

Only `item_number` is required for reconciliation to run; every other
field is optional and missing values are handled gracefully (flagged,
not crashed on).

## Input: Drawing callout data (from Person 4's Vision AI extraction)

```json
[
  {
    "bubble_number": "3",
    "location_description": "Upper-left mounting bracket",
    "bounding_box": { "xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458 },
    "confidence_score": 0.95
  }
]
```

`bounding_box` coordinates are in the project's single normalized
coordinate system. The intelligence module passes them through
unchanged -- it never converts to screen/browser coordinates. That
conversion is the Drawing UI's (Person 1's) responsibility.

## Output: unified component record

Produced by `intelligence.build_workspace(...)["components"]`. This is
additive on top of the originally agreed shape -- `description`,
`revision`, and `procurement_data` were added, nothing was renamed or
removed.

```json
{
  "id": "cmp_003",
  "item_number": "3",
  "bubble_number": "3",
  "part_number": "FB-M8-001",
  "part_name": "Hexagonal Flange Bolt M8",
  "description": "",
  "quantity": 6,
  "material_specification": "Grade 8.8 Carbon Steel",
  "revision": "",
  "location_description": "Upper-left mounting bracket",
  "bounding_box": { "xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458 },
  "confidence_score": 0.97,
  "procurement_data": {
    "estimated_unit_cost_usd": 0.45,
    "estimated_total_cost_usd": 2.7,
    "supplier_source": "Industrial Supply Corp",
    "stock_status": "In Stock",
    "estimated": true,
    "mock_data": true,
    "note": "Mock/estimated procurement data for demonstration purposes only. Not a real quotation."
  }
}
```

For a component that could not be linked (missing callout, missing BOM
item, or an ambiguous identifier), the fields from the missing side are
simply `null`/empty -- the record is never dropped.

## Output: validation record (per component)

```json
{ "component_id": "cmp_003", "issues": [], "status": "linked" }
```

`status` is one of: `linked`, `review_required`, `missing_callout`,
`missing_bom_item`, `invalid`. Each entry in `issues` is
`{"type", "severity", "message"}` with `severity` one of `info`,
`warning`, `error`.

## Output: full workspace (`build_workspace(...)` return value)

```json
{
  "components": [ ... ],
  "validation": { "summary": { ... }, "issues": [ ... ] },
  "procurement_summary": { ... },
  "metadata": { ... }
}
```

This whole structure is plain JSON (dicts/lists/strings/numbers/null)
-- safe to `json.dumps` directly and safe for Streamlit/pandas to
consume without any custom deserialization.

See `intelligence/README.md` for how the module is implemented and
`intelligence/sample_data.py` for a realistic worked example covering
every validation case.
