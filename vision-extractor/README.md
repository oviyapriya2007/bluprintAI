# vision-extractor

**BlueprintAI — Person 4 module: Vision AI Extraction**

Takes a processed engineering drawing image and turns it into structured
BOM + callout + bounding-box + confidence data, following the shared
BlueprintAI data contract.

```
Engineering Drawing
  -> Document Processing        (Person 3)
  -> Vision AI Extraction       (this module)
  -> Spatial Reconciliation     (Person 5)
  -> Interactive Workspace / BOM / Export   (Person 1 & 2)
```

This module's job stops at:

```
processed image -> Gemini vision model -> validated structured JSON
```

It does **not** do PDF conversion, OpenCV preprocessing, deterministic
Bubble-Number <-> Item-Number reconciliation, UI, or export — those belong
to other team members.

## Architecture

```
vision_extractor/
├── config.py         Settings loaded from environment / .env
├── models.py          Pydantic models for the shared data contract
├── prompts.py          BOM + callout + metadata prompts sent to Gemini
├── gemini_client.py    Thin isolated wrapper around the Gemini SDK
├── extractor.py        VisionExtractor — the public orchestration service
├── validator.py         Raw JSON -> validated models, with graceful degradation
├── confidence.py        Confidence clamping / low-confidence detection
├── mock_data.py         Deterministic mock ExtractionResult (no API needed)
├── utils.py              Image loading + 0-1000 coordinate normalization
├── exceptions.py         VisionExtractionError / GeminiAPIError / InvalidExtractionError
└── cli.py                 `python -m vision_extractor.cli` entry point
```

Pipeline inside `VisionExtractor.extract_from_image()`:

```
image -> Gemini (BOM prompt)      -> raw JSON -> validate -> BOMItem[]
image -> Gemini (callout prompt)  -> raw JSON -> validate -> Callout[]
                                                   |
                                     exact item_number == bubble_number match
                                                   v
                                            ExtractedComponent[]
```

Only BOM items and callouts that share an *exact* item/bubble number are
merged into `components` here — this is a convenience, not a reconciliation
engine. Person 5's module owns real (fuzzy/spatial) reconciliation.

## Installation

```bash
cd vision-extractor
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
copy .env.example .env
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | (none) | Your Gemini API key. Leave blank to force mock mode. |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model name — never hardcoded elsewhere. |
| `USE_MOCK` | auto | `true`/`false`. If unset, defaults to mock mode when no API key is present. |
| `LOW_CONFIDENCE_THRESHOLD` | `0.70` | Below this, items get a warning (never silently dropped). |

## Mock mode (no API key required)

By default, if `GEMINI_API_KEY` is not set, the module automatically runs in
mock mode — this is the primary way the rest of the team should develop
against this module before a Gemini key is available.

```bash
python -m vision_extractor.cli --mock
```

or in code:

```python
from vision_extractor import VisionExtractor

extractor = VisionExtractor()   # USE_MOCK inferred from environment
result = extractor.extract_from_image("drawing.png")
print(extractor.using_mock)     # True if no Gemini client was used
```

Mock data always contains 5 realistic components (including one deliberately
low-confidence item, #4, to exercise the warning path) and matches the
shared contract exactly.

## Gemini setup (real extraction)

1. Get a Gemini API key.
2. In `.env`:
   ```
   GEMINI_API_KEY=your_key_here
   GEMINI_MODEL=gemini-3.6-flash
   USE_MOCK=false
   ```
3. `pip install google-genai` (already in `requirements.txt`).
4. Run:
   ```bash
   python -m vision_extractor.cli --image examples/sample_input/sample_drawing.png
   ```

If the Gemini client fails to initialize (bad key, package missing, network
down), `VisionExtractor` automatically falls back to mock mode rather than
crashing — check the logs for a warning when this happens.

## Usage

```python
from vision_extractor import VisionExtractor

extractor = VisionExtractor()
result = extractor.extract_from_image("examples/sample_input/sample_drawing.png")

result.model_dump()          # -> dict
result.model_dump_json()     # -> JSON string
```

`extract_from_image` accepts a file path (`str`/`Path`) to a PNG/JPEG/JPG, or
an in-memory `PIL.Image.Image`.

## Output JSON structure

```json
{
  "drawing_number": "ASM-001",
  "revision": "B",
  "bom_items": [
    {
      "item_number": "3",
      "part_number": "FB-M8-001",
      "part_name": "Hexagonal Flange Bolt M8",
      "description": "Flange bolt, bracket to frame",
      "quantity": 6,
      "material_specification": "Grade 8.8 Carbon Steel",
      "revision": null,
      "confidence_score": 0.97
    }
  ],
  "callouts": [
    {
      "bubble_number": "3",
      "location_description": "Callout near Hexagonal Flange Bolt M8",
      "bounding_box": { "xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458 },
      "confidence_score": 0.97
    }
  ],
  "components": [
    {
      "id": "cmp_003",
      "item_number": "3",
      "bubble_number": "3",
      "part_number": "FB-M8-001",
      "part_name": "Hexagonal Flange Bolt M8",
      "quantity": 6,
      "material_specification": "Grade 8.8 Carbon Steel",
      "confidence_score": 0.97,
      "bounding_box": { "xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458 }
    }
  ],
  "extraction_warnings": [
    "Low confidence extraction for item 4 (confidence=0.58)"
  ]
}
```

A full sample is at
[`examples/sample_output/sample_output.json`](examples/sample_output/sample_output.json).

### Coordinate system

All `bounding_box` values (`xmin`, `ymin`, `xmax`, `ymax`) are normalized to a
**0–1000 scale on both axes**, with `(0, 0)` at the top-left of the image and
`(1000, 1000)` at the bottom-right — regardless of the source image's actual
pixel dimensions. Never store raw pixel or screen coordinates; the frontend
converts normalized coordinates into screen positions itself.

If Gemini ever returns values clearly outside `[0, 1000]` (i.e. raw pixel
coordinates), they are automatically converted using the image's actual
width/height (`utils.normalize_bbox_pixels`). Values already in range are
trusted as normalized, since the prompts explicitly instruct Gemini to
return normalized coordinates directly.

### Confidence scores

Every `BOMItem`, `Callout`, and `ExtractedComponent` has a
`confidence_score` in `[0, 1]`, clamped defensively even if the model
returns something out of range. Items below `LOW_CONFIDENCE_THRESHOLD`
(default `0.70`) are **never dropped** — they're kept and a warning like
`"Low confidence extraction for item 4 (confidence=0.58)"` is added to
`extraction_warnings` so the UI can flag them for engineer review.

## Testing

```bash
python -m pytest tests/ -v
```

43 unit tests run without any API key or network access, covering: bounding
box validation, coordinate normalization, confidence handling, Pydantic
models, mock extraction, malformed/invalid model output, missing optional
fields, low-confidence warnings, duplicate callout numbers, and end-to-end
mock extraction. One additional integration test
(`tests/test_integration.py`) only runs when `GEMINI_API_KEY` is set in the
environment, and is skipped otherwise.

## CLI

```bash
# Print mock JSON with no image at all
python -m vision_extractor.cli --mock

# Run mock extraction against a real image (dimensions still read/logged)
python -m vision_extractor.cli --image examples/sample_input/sample_drawing.png --mock

# Run real Gemini extraction (requires GEMINI_API_KEY, USE_MOCK=false)
python -m vision_extractor.cli --image examples/sample_input/sample_drawing.png
```

## Integration contract for other team members

Import and call exactly this:

```python
from vision_extractor import VisionExtractor

extractor = VisionExtractor()
result = extractor.extract_from_image(image_path_or_pil_image)

data = result.model_dump()          # plain dict, ready for JSON/DB/etc.
json_str = result.model_dump_json() # JSON string
```

- **Input**: a file path (str/Path) to a PNG/JPEG/JPG, or a `PIL.Image.Image`.
  PDF-to-image conversion is Person 3's responsibility and must happen
  before calling this function.
- **Output**: always a `vision_extractor.models.ExtractionResult` — never
  raises for a single bad image or malformed model response; failures are
  captured in `result.extraction_warnings` instead so a batch run never
  crashes on one bad drawing.
- **Person 5 (Spatial Reconciliation)** should read `result.bom_items` and
  `result.callouts` directly and perform deterministic
  Bubble-Number <-> Item-Number matching there. `result.components` is only
  a best-effort convenience for items that already matched exactly by
  number — don't assume it's complete or authoritative.
- All bounding boxes are normalized 0–1000 on both axes (see above).
- No network access or Gemini key is required to integrate against this
  module during development — run with `USE_MOCK=true` (or simply leave
  `GEMINI_API_KEY` unset).

## Limitations & assumptions

- PDF handling is explicitly out of scope (Person 3's module).
- No AI-based reconciliation is performed; `components` only contains exact
  item/bubble number matches, by design.
- The model cannot guarantee 100% OCR accuracy on very low-resolution or
  extremely crowded drawings — that's exactly why every value carries a
  `confidence_score` and low-confidence items are flagged, not hidden.
- `google-genai` is the SDK targeted; if it is not installed, the module
  still imports and runs fully in mock mode, but real Gemini calls will
  raise a clear `GeminiAPIError` telling you to install it.
