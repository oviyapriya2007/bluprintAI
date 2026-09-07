# BlueprintAI — Technical Specification & System Brief

## 1. Project Overview

### System Name

**BlueprintAI**

### Core Purpose

BlueprintAI is an AI-powered engineering drawing intelligence system that converts flat engineering drawings into structured, interactive data.

It ingests engineering drawings such as PDFs, PNGs, and JPEGs, identifies:

* Parts tables / BOM tables
* Item numbers
* Part names
* Quantities
* Material specifications
* Drawing callout bubbles
* Spatial locations of parts
* Revision information
* Other relevant engineering metadata

It then connects the extracted BOM information with the corresponding visual callouts in the drawing.

The result is an interactive engineering workspace where users can move between:

**Drawing → Part → BOM Data**

and

**BOM Data → Exact Drawing Location**

---

## 2. Target Industry

Primary target:

**Manufacturing and Engineering**

Relevant sectors include:

* Automotive component manufacturing
* Precision engineering
* CNC machining
* Machine building
* Industrial equipment manufacturing
* Fabrication
* Aerospace component manufacturing
* Hardware engineering
* Industrial procurement
* Engineering suppliers and job shops

---

## 3. Primary Users

BlueprintAI is mainly useful for teams that receive or work with engineering drawings after they have been created.

### Design / CAD Engineer

Usually creates the original engineering drawing using tools such as:

* AutoCAD
* SolidWorks
* CATIA
* Creo
* Autodesk Inventor

BlueprintAI is not intended to replace CAD software.

It helps downstream teams understand and process the drawing.

### Production Engineer

Uses BlueprintAI to quickly understand:

* Components required
* Quantities
* Materials
* Assembly relationships
* Relevant drawing locations

### Quality / Inspection Engineer

Uses extracted drawing information to identify:

* Components
* Dimensions
* Tolerances
* Material specifications
* Inspection requirements

Future versions can automatically generate inspection checklists.

### Procurement Team

Uses the extracted BOM to determine:

* What needs to be purchased
* Quantity required
* Material/specification
* Approximate price
* Supplier availability

### Costing / Estimation Engineer

Uses drawing data to prepare:

* Quotations
* Material estimates
* Procurement estimates
* Preliminary manufacturing cost estimates

### Engineering Suppliers

A supplier receiving dozens of customer drawings can use BlueprintAI to convert incoming drawings into structured data before preparing quotations or manufacturing plans.

---

# 4. Problem Statement

Engineering drawings contain information differently from normal business documents.

Traditional OCR systems work well when information appears sequentially as text.

Engineering drawings instead contain information spatially.

For example:

**Bubble 3 → Leader Line → Mechanical Bracket**

while the title block may contain:

**Item 3 → Bracket Assembly → Qty 2 → Stainless Steel**

A human engineer must mentally connect these pieces of information.

When drawings contain dozens or hundreds of components, manually identifying:

* Which callout corresponds to which part
* Where the part appears
* What quantity is required
* What material is specified
* Whether the BOM matches the drawing

can become repetitive and time-consuming.

BlueprintAI converts this spatial engineering information into structured data.

---

# 5. Core Value Proposition

BlueprintAI transforms:

**Engineering Drawing**

into:

**Interactive Drawing + Structured BOM + Spatial Mapping + Procurement-Ready Data**

Instead of engineers manually tracing callout bubbles and referring repeatedly to the BOM table, the system automatically establishes the relationship.

Example:

```text
Bubble 3
   ↓
Hexagonal Flange Bolt M8
   ↓
Quantity: 6
   ↓
Material: Grade 8.8 Carbon Steel
   ↓
Drawing Location: Upper-left mounting bracket
```

The engineer can immediately see where the component appears in the drawing.

---

# 6. Core System Architecture

The overall architecture follows four major stages:

```text
Engineering Drawing
        │
        ▼
1. Document Processing
        │
        ▼
2. Vision AI Extraction
        │
        ▼
3. Spatial Reconciliation
        │
        ▼
4. Interactive Engineering Workspace
        │
        ├── BOM
        ├── Drawing Highlighting
        ├── Procurement Information
        └── Excel / CSV Export
```

---

# 7. Stage 1 — Document Ingestion & Image Processing

## Supported Inputs

Initial hackathon version should support:

* PDF
* PNG
* JPEG

Engineering drawings may range from:

* A4
* A3
* A2
* A1
* A0

Large engineering drawings require higher-resolution processing because important information may appear as very small text.

---

## PDF Processing

For PDF drawings:

**pdf2image**

converts each page into a high-resolution image.

Example flow:

```text
Engineering PDF
      ↓
High-resolution PNG
      ↓
Image processing
      ↓
Vision AI
```

If a PDF contains multiple pages, each page can be processed independently.

---

## Region Isolation

BlueprintAI can separate important drawing regions.

Typical regions include:

### Main Drawing Canvas

Contains:

* Components
* Assemblies
* Callout bubbles
* Leader lines
* Dimensions
* Notes

### Title Block / BOM Region

Usually contains:

* Drawing number
* Revision
* Part numbers
* Description
* Quantity
* Material
* Drawing metadata

OpenCV can be used to crop or divide these regions before sending them to the AI model.

This allows the AI to focus separately on:

**tabular information**

and

**visual/spatial information.**

---

# 8. Coordinate Normalization

AI models may return bounding boxes relative to the original image.

However, the drawing may be displayed at different sizes depending on:

* Monitor size
* Browser size
* Zoom level
* Application layout

Therefore BlueprintAI converts all locations into a normalized coordinate system.

Example:

```text
0 → 1000
```

A detected callout might therefore have:

```json
{
  "ymin": 412,
  "xmin": 185,
  "ymax": 458,
  "xmax": 230
}
```

These coordinates remain usable regardless of how the image is resized.

The frontend converts the normalized coordinates back into screen coordinates while rendering the drawing.

---

# 9. Stage 2 — Vision AI Extraction

A multimodal Vision LLM processes the engineering drawing.

For the hackathon implementation:

**Gemini multimodal models**

can be used because they support:

* Image understanding
* OCR-like extraction
* Structured output
* JSON responses

Possible alternatives include:

* OpenAI multimodal models
* Claude multimodal models
* Qwen-VL
* Florence-based vision models

---

# 10. Extraction Task A — BOM / Title Block

The system detects the BOM or component table.

Typical extracted fields include:

```text
Item Number
Part Number
Part Name
Description
Quantity
Material
Revision
Drawing Number
```

Example:

```json
{
  "item_number": "3",
  "part_name": "Hexagonal Flange Bolt M8",
  "quantity": 6,
  "material": "Grade 8.8 Carbon Steel"
}
```

---

# 11. Extraction Task B — Drawing Callouts

The system separately analyzes the drawing canvas.

It identifies:

* Callout bubbles
* Bubble number
* Approximate component location
* Bounding box
* Related leader line where detectable

Example:

```json
{
  "bubble_number": "3",
  "location_description": "Upper-left mounting bracket",
  "bounding_box": {
    "ymin": 412,
    "xmin": 185,
    "ymax": 458,
    "xmax": 230
  }
}
```

---

# 12. Stage 3 — Spatial Reconciliation Engine

At this stage BlueprintAI has two datasets.

### BOM Dataset

```text
3 → Hexagonal Flange Bolt M8 → Qty 6
```

### Drawing Dataset

```text
Bubble 3 → Upper-left mounting bracket
```

The reconciliation engine joins the datasets using the common identifier.

```text
Bubble Number 3
       +
BOM Item Number 3
       ↓
Hexagonal Flange Bolt M8
Qty: 6
Location: Upper-left mounting bracket
```

For the first version, this reconciliation can be deterministic Python logic rather than another AI agent.

Example concept:

```python
for bubble in drawing_bubbles:
    matching_part = find_part_by_item_number(
        bubble["bubble_number"]
    )

    if matching_part:
        combine_part_and_location(
            matching_part,
            bubble
        )
```

Using deterministic matching makes the architecture simpler and more reliable.

---

# 13. Stage 4 — Interactive Engineering Workspace

The main user experience is a synchronized split-screen interface.

```text
┌──────────────────────────┬──────────────────────────┐
│                          │                          │
│   ENGINEERING DRAWING    │       BOM TABLE          │
│                          │                          │
│        Bubble 3          │  3 | M8 Bolt | Qty 6    │
│           ↓              │                          │
│       [Bracket]          │                          │
│                          │                          │
└──────────────────────────┴──────────────────────────┘
```

---

# 14. Bidirectional Spatial Highlighting

This is one of BlueprintAI's key differentiating features.

### BOM → Drawing

User clicks:

**Item 3 — Hexagonal Flange Bolt M8**

The system automatically highlights:

**Bubble 3**

on the engineering drawing.

---

### Drawing → BOM

The user clicks Bubble 3 or its highlighted region.

BlueprintAI automatically selects:

**Item 3**

in the BOM table.

This creates a synchronized relationship between:

**visual engineering information**

and

**structured engineering data.**

---

# 15. Editable BOM Workspace

Extracted AI data should not be treated as automatically correct.

The engineer can review and edit fields including:

* Part name
* Quantity
* Material
* Part number
* Revision
* Description

Human correction is important because engineering information can have production or financial consequences.

---

# 16. Confidence Score

Each AI-extracted component should include a confidence score.

Example:

```text
Item 3

Hexagonal Flange Bolt M8

Confidence: 97%
```

Low-confidence results can automatically be highlighted for human verification.

Example:

```text
Item 12 — Confidence 61%

⚠ Review recommended
```

---

# 17. Drawing-to-BOM Validation

A useful intelligence feature is checking whether information in the drawing and BOM appears consistent.

BlueprintAI can identify situations such as:

### Callout Without BOM Entry

```text
Bubble 14 found

No Item 14 found in BOM

⚠ Possible missing BOM entry
```

### BOM Item Without Drawing Callout

```text
Item 9 exists in BOM

No corresponding Bubble 9 detected

⚠ Drawing verification required
```

### Quantity Mismatch

Where technically possible, the system can compare detected instances against BOM quantities.

Example:

```text
BOM Quantity: 6

Detected visual instances: 4

⚠ Quantity requires verification
```

This should be treated as an engineering review flag rather than an automatic conclusion.

---

# 18. Procurement Enrichment Layer

Once BlueprintAI understands the component list, additional procurement information can be attached.

Example:

| Item | Component      | Qty | Unit Cost | Availability |
| ---- | -------------- | --: | --------: | ------------ |
| 3    | M8 Flange Bolt |   6 |     $0.45 | In Stock     |
| 4    | Bearing 6204   |   2 |     $4.80 | Limited      |

For the hackathon, this can use:

* Mock supplier APIs
* Predefined supplier datasets
* Public sample catalogs

Real-world implementations could later integrate with actual procurement systems and supplier APIs.

---

# 19. Procurement Cost Estimation

BlueprintAI can calculate:

```text
Part Quantity × Estimated Unit Price
```

Example:

```text
M8 Bolt
Qty: 6
Unit Cost: $0.45

Estimated Cost = $2.70
```

The complete BOM can therefore provide:

**Estimated Procurement Cost**

This demonstrates how drawing intelligence can connect directly to business operations.

---

# 20. Structured Export

Users can export the extracted and validated information.

Supported formats:

* Excel `.xlsx`
* CSV

Using:

* Pandas
* OpenPyXL

Example Excel columns:

```text
Item Number
Part Number
Part Name
Quantity
Material
Revision
Drawing Location
Confidence
Estimated Unit Cost
Estimated Total Cost
Supplier
Stock Status
```

---

# 21. Excel Output Example

```text
BlueprintAI_BOM.xlsx

Sheet 1: BOM
Sheet 2: Procurement Estimate
Sheet 3: AI Validation Issues
```

### BOM Sheet

Contains extracted engineering information.

### Procurement Sheet

Contains:

```text
Quantity
Unit Price
Total Cost
Supplier
Availability
```

### Validation Sheet

Contains detected issues such as:

```text
Missing BOM Item
Missing Callout
Low Confidence
Possible Quantity Mismatch
```

---

# 22. Recommended Hackathon Features

The hackathon MVP should focus on five features.

## Feature 1 — Automatic BOM Extraction

Upload an engineering drawing.

BlueprintAI generates the BOM automatically.

---

## Feature 2 — Callout Detection

Identify numbered component bubbles on the engineering drawing.

---

## Feature 3 — Interactive Drawing ↔ BOM Linking

Click a BOM row and highlight the corresponding drawing location.

This should be the main visual demo feature.

---

## Feature 4 — Drawing/BOM Consistency Check

Detect:

* Missing BOM entries
* Missing callouts
* Duplicate callouts
* Low-confidence extraction

---

## Feature 5 — Excel Export

Generate a structured engineering BOM spreadsheet.

---

# 23. Optional Hackathon Enhancement — Drawing Revision Intelligence

If time allows, support two versions of the same engineering drawing.

Example:

```text
Revision A
vs
Revision B
```

BlueprintAI identifies changes such as:

```text
Item 4

Rev A:
M8 Bolt

Rev B:
M10 Bolt

Change detected:
Bolt specification modified
```

Possible output:

```text
Changed Parts: 3
New Parts: 1
Removed Parts: 2
Quantity Changes: 4
```

This could become a major future capability.

---

# 24. Future Feature — Quality Inspection Generation

Engineering drawings contain dimensions and tolerances such as:

```text
Ø25 ±0.02 mm
```

BlueprintAI could extract them and automatically create a quality inspection sheet.

Example:

| Feature        | Nominal | Tolerance | Inspection |
| -------------- | ------: | --------: | ---------- |
| Shaft Diameter |   25 mm |  ±0.02 mm | Measure    |
| Hole Diameter  |    8 mm |  ±0.05 mm | Measure    |

This would extend BlueprintAI from:

**Drawing → BOM**

to:

**Drawing → Production + Quality Data**

---

# 25. Future Feature — Quotation Intelligence

A machining or fabrication supplier could upload customer drawings.

BlueprintAI could extract:

```text
Material
Dimensions
Quantity
Tolerance
Surface Finish
Manufacturing Notes
```

and create:

**Quotation Preparation Summary**

This could become an important commercial use case for manufacturing SMEs.

---

# 26. Technology Stack

## Frontend

**Streamlit**

Used for the hackathon because it enables rapid development of interactive Python applications.

Responsibilities:

* File upload
* Drawing viewer
* BOM table
* User interactions
* Highlight overlays
* Download controls

For a production product, the frontend could later move to React or another dedicated web framework.

---

## Backend

**Python**

Main responsibilities:

* Document processing
* Vision model calls
* JSON validation
* Spatial reconciliation
* Export generation

---

## Vision Intelligence

Primary hackathon option:

**Gemini multimodal API**

Responsibilities:

* Drawing understanding
* BOM extraction
* Callout identification
* Bounding box estimation
* Structured JSON output

Possible fallback/local research options:

* Qwen-VL
* Florence-based vision models

---

## Image Processing

### OpenCV

Used for:

* Cropping
* Scaling
* Image manipulation
* Region isolation
* Coordinate transformation

### pdf2image

Used for:

```text
PDF → High-resolution image
```

---

## Data Processing

### Pandas

Used for:

* BOM manipulation
* Table processing
* Cost calculations

### OpenPyXL

Used for:

* Excel formatting
* Multiple worksheets
* Styled exports

---

## Database

For the hackathon:

**SQLite**

Stores:

* Uploaded document metadata
* Processing results
* Extracted BOM
* Bounding coordinates
* Historical analyses

Streamlit Session State can manage temporary UI state.

---

# 27. System Data Model

A component can internally be represented as:

```json
{
  "id": 1,
  "bubble_number": "3",
  "part_number": "FB-M8-001",
  "part_name": "Hexagonal Flange Bolt M8",
  "quantity": 6,
  "material_specification": "Grade 8.8 Carbon Steel",
  "revision": "B",
  "location_description": "Upper-left mounting bracket",
  "bounding_box": {
    "ymin": 412,
    "xmin": 185,
    "ymax": 458,
    "xmax": 230
  },
  "confidence_score": 0.97,
  "procurement_data": {
    "estimated_unit_cost_usd": 0.45,
    "supplier_source": "Industrial Supply Corp",
    "stock_status": "In Stock"
  }
}
```

---

# 28. End-to-End Processing Flow

```text
USER
 │
 │ Upload Engineering Drawing
 ▼
PDF / PNG / JPEG
 │
 ▼
DOCUMENT PROCESSOR
 │
 ├── PDF Rasterization
 ├── Resolution Adjustment
 └── Region Extraction
 │
 ▼
VISION AI
 │
 ├── BOM Extraction
 ├── Callout Detection
 ├── Metadata Extraction
 └── Bounding Boxes
 │
 ▼
STRUCTURED JSON
 │
 ▼
RECONCILIATION ENGINE
 │
 ├── Match Bubble → Item
 ├── Attach Coordinates
 ├── Validate Missing Items
 └── Calculate Confidence
 │
 ▼
BLUEPRINTAI WORKSPACE
 │
 ├── Interactive Drawing
 ├── Interactive BOM
 ├── Validation Alerts
 └── Procurement Estimate
 │
 ▼
EXPORT
 │
 ├── Excel
 └── CSV
```

---

# 29. Example User Journey

A manufacturing supplier receives an assembly drawing from a customer.

### Step 1

Engineer uploads:

**Assembly_Drawing_RevB.pdf**

### Step 2

BlueprintAI processes the drawing.

### Step 3

System identifies:

```text
27 BOM Items
26 Drawing Callouts
```

### Step 4

BlueprintAI reports:

```text
26 items successfully linked

1 BOM item has no visible callout

2 items have low extraction confidence
```

### Step 5

Engineer clicks:

**Item 17 — Bearing 6204**

The corresponding callout is highlighted on the drawing.

### Step 6

Engineer corrects any AI extraction errors.

### Step 7

BlueprintAI calculates preliminary procurement information.

### Step 8

Engineer exports:

**Assembly_Drawing_RevB_BOM.xlsx**

The previously unstructured engineering drawing has now been converted into usable manufacturing data.

---

# 30. What BlueprintAI Is Not

For the hackathon scope, BlueprintAI is **not** intended to:

* Replace AutoCAD/SolidWorks/CATIA
* Modify CAD geometry
* Generate manufacturing-ready CAD models
* Automatically approve engineering drawings
* Guarantee engineering correctness
* Replace engineering review
* Perform full manufacturing process planning

Its purpose is:

> **To understand engineering drawings and convert their visual and spatial information into structured, traceable, actionable data.**

---

# 31. Key Differentiator

Traditional document AI:

```text
Document
   ↓
OCR
   ↓
Text
```

Typical LLM document systems:

```text
Document
   ↓
Extract Text
   ↓
Ask Questions
```

BlueprintAI:

```text
Engineering Drawing
        ↓
Understand Visual Structure
        ↓
Extract BOM + Callouts
        ↓
Understand Spatial Relationships
        ↓
Connect Drawing ↔ Engineering Data
        ↓
Validate
        ↓
Create Actionable Manufacturing Data
```

The main innovation is therefore not OCR.

It is:

> **Spatial reconciliation between engineering drawing elements and structured engineering information.**

---

# 32. Hackathon Pitch

### One-Line Pitch

**BlueprintAI turns engineering drawings into interactive, structured manufacturing intelligence.**

### Problem

Manufacturing teams still spend significant engineering effort manually interpreting drawings, tracing component callouts, transferring BOM information and preparing downstream production or procurement data.

### Solution

BlueprintAI uses multimodal AI and spatial intelligence to automatically identify components, map BOM entries to their exact locations in an engineering drawing, detect inconsistencies and convert the result into structured manufacturing data.

### Demonstration

```text
Upload Drawing
      ↓
AI extracts BOM
      ↓
AI identifies callouts
      ↓
Click BOM Item
      ↓
Part highlighted on drawing
      ↓
Detect missing/mismatched items
      ↓
Export engineering BOM
```

### Long-Term Vision

BlueprintAI could evolve from:

**Drawing Intelligence**

into:

```text
Drawing
  ↓
BOM
  ↓
Costing
  ↓
Procurement
  ↓
Quality Inspection
  ↓
Revision Intelligence
  ↓
Manufacturing Workflow
```

making engineering drawings directly usable across the manufacturing organization.

---

# 33. Team Split & Build Plan

## Streamlit Hackathon Build

**Five Laptops, One Folder**

How five people build BlueprintAI independently on their own laptops, then combine five folders into one project and run the complete system.

**One repo → five folders → no overlap → one integration run**

Hackathon build: Streamlit workspace + Python processing + Vision AI.

The core demo is **Engineering Drawing ↔ BOM Data with spatial highlighting**.

---

## 33.1 The Working Model

Each person owns one top-level folder and avoids editing anyone else's core files. That single rule lets five laptops combine with minimal merge conflicts.

### The One Directory

```text
blueprintai/
├── app.py                 ← integration shell (agreed)
├── contracts/             ← shared JSON + mock data
├── drawing-ui/             ← Person 1 ONLY
├── bom-ui/                 ← Person 2 ONLY
├── document-processor/     ← Person 3 ONLY
├── vision-extractor/       ← Person 4 ONLY
└── intelligence/           ← Person 5 ONLY
```

Everyone can build their own folder using the same mock JSON. At integration, replace mock calls with real functions/APIs and connect everything through the shared contract.

### Why This Model Works

Streamlit is fast for a hackathon, but two people should not keep editing the same `app.py`. Separate pages/components prevent overlap and allow both UI developers to work independently.

---

## 33.2 Two Day-1 Agreements

Do these before anyone writes real code. They are what make independent work possible.

### Agreement 1 — The Data Contract

Agree the exact JSON shape for every extracted component. The two Streamlit developers build against fake data while the three backend developers build the real modules that produce the same shapes.

**Integration later = swap the data source, not rewrite the UI.**

### Agreement 2 — The Shared Interface

Agree exactly how modules are called: function names or REST endpoints, input files, output JSON, and error responses. Keep configuration values in one place and never hardcode them across many files.

| Service / Module | Owner | Local Run |
|---|---|---|
| Drawing UI (Streamlit) | Person 1 | `localhost:8501` |
| BOM UI (Streamlit) | Person 2 | `localhost:8502` |
| Document processing | Person 3 | Python module/API |
| Vision extraction | Person 4 | Python module/API |
| Reconciliation & export | Person 5 | Python module/API |

> **The rule that saves your night:** Frontend people should never depend on an unfinished backend. Use `contracts/sample_workspace.json` from Day 1. Backend people only need to ensure their final output matches that contract.

---

## 33.3 Who Owns What

| Folder | Person & Role | Best Suited To |
|---|---|---|
| `drawing-ui/` | Person 1 — Streamlit Drawing UI | UI / Python |
| `bom-ui/` | Person 2 — Streamlit BOM & Results UI | UI / Python |
| `document-processor/` | Person 3 — Document Processing | Strong Python |
| `vision-extractor/` | Person 4 — Vision AI Extraction | AI / API |
| `intelligence/` | Person 5 — Reconciliation, Validation & Export | Strong Python / data |

**Balance tip:** Persons 1 and 2 are the Streamlit/UI pair. Persons 3, 4 and 5 are the processing/intelligence pair. Give the drawing and reconciliation work to people comfortable with Python; give the AI extraction work to the person most comfortable with API prompts and structured JSON.

Each person should be able to demonstrate their own folder before integration. No one should wait for another member to finish.

---

## 33.4 Person 3, Person 4 & Person 5

### Person 3 — Document Processing

**Folder:** `document-processor/`

Builds:

- File validation
- PDF → high-resolution image conversion
- PNG/JPEG handling
- Resolution adjustment
- Optional OpenCV region isolation for the drawing canvas and BOM/title-block region

**Stack:** Python · pdf2image · Pillow · OpenCV

**Works alone by:** Using sample engineering drawings and returning processed images + metadata.

**Owns:** Everything from uploaded file → AI-ready image.

### Person 4 — Vision AI Extraction

**Folder:** `vision-extractor/`

Builds:

- Gemini/vision-model client
- Prompts for BOM extraction
- Prompts for callout detection
- Structured JSON validation
- Confidence handling
- Fallback mock output

**Stack:** Python · Gemini multimodal API · Pydantic

**Works alone by:** Taking processed sample images and producing JSON that exactly matches the shared contract.

**Owns:** Everything from image → structured BOM items + callout bubbles + bounding boxes.

### Person 5 — Reconciliation, Validation & Export

**Folder:** `intelligence/`

Builds:

- Deterministic Bubble Number → BOM Item Number matching
- Unified component records
- Validation flags
- Confidence review flags
- Mock procurement calculation
- Excel/CSV export

**Stack:** Python · Pandas · OpenPyXL

**Works alone by:** Using sample BOM JSON and sample callout JSON — pure data in, workspace JSON out.

**Owns:** The intelligence that turns two extracted datasets into one usable engineering workspace.

---

## 33.5 Person 1 & Person 2

### Person 1 — Drawing Workspace

**Folder:** `drawing-ui/`

Builds:

- Streamlit upload flow
- Engineering drawing viewer
- Image scaling
- Normalized bounding-box overlays
- Selected callout highlighting
- Visual side of the main interaction

**Stack:** Streamlit · Python · Pillow/OpenCV helpers

**Works alone by:** Reading `contracts/sample_workspace.json` and displaying fake extracted results immediately.

**Owns:** Everything the engineer sees on the drawing side.

### Person 2 — BOM & Results Workspace

**Folder:** `bom-ui/`

Builds:

- BOM table
- Confidence badges
- Validation panel
- Editable component fields
- Procurement summary
- Excel/CSV download controls

**Stack:** Streamlit · Python · Pandas display helpers

**Works alone by:** Using the exact same mock JSON as Person 1. No backend dependency is required.

**Owns:** Everything the engineer sees on the structured-data side.

### How the Two Streamlit Developers Synchronize

Agree on one shared field: `selected_item_id`.

Clicking Item 3 in the BOM sets it to `'3'`. The drawing viewer reads the same value and highlights Bubble 3.

During the hackathon, keep this logic simple and explicit.

---

## 33.6 The Shared Contract

Agree these shapes on Day 1. UI builds against them; backend produces them. Extend together, never silently alone.

### `component.json`

```json
{
  "id": "cmp_003",
  "item_number": "3",
  "bubble_number": "3",
  "part_number": "FB-M8-001",
  "part_name": "Hexagonal Flange Bolt M8",
  "quantity": 6,
  "material_specification": "Grade 8.8 Carbon Steel",
  "confidence_score": 0.97,
  "bounding_box": {
    "xmin": 185,
    "ymin": 412,
    "xmax": 230,
    "ymax": 458
  }
}
```

### `validation.json`

```json
{
  "component_id": "cmp_003",
  "issues": [],
  "status": "linked"
}
```

### Important Coordinate Rule

Store AI locations in one normalized coordinate system. The drawing UI converts them to screen positions when rendering. This prevents highlights from breaking when the image size or browser layout changes.

---

## 33.7 Putting It Together & Running

Use one shared GitHub repository. Each person commits only inside their own main folder. The final integration should mostly be wiring, not rewriting.

### The Single Demo Path Everyone Tests Together

```text
Engineer uploads drawing
        ↓
PDF/image is processed
        ↓
Vision AI extracts BOM + callouts
        ↓
Reconciliation links Bubble 3 to Item 3
        ↓
Streamlit shows drawing and BOM
        ↓
Engineer clicks Item 3
        ↓
Exact drawing location is highlighted
        ↓
Validation flags are shown
        ↓
Engineer exports Excel
```

### Integration Steps

1. Each person pushes only their folder to the shared repository.
2. Copy/merge the five folders into `blueprintai/` next to `contracts/` and the integration shell.
3. Run all five modules using sample data first.
4. Connect Person 3 → Person 4: processed image becomes vision input.
5. Connect Person 4 → Person 5: extraction JSON becomes reconciliation input.
6. Connect Person 5 → Persons 1 & 2: unified workspace JSON replaces mock data.
7. Test the complete demo path with at least one clean sample drawing and one imperfect drawing.

> If everyone honored the Day-1 contract, integration should be connecting modules — not fixing mismatched data formats. That is the entire point of the five-folder model.
