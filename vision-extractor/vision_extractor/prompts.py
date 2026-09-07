"""Prompt templates for Gemini multimodal engineering-drawing extraction.

Kept as plain strings (no templating engine) so they're easy to tune during
the hackathon. Each prompt demands strict JSON output matching the schema
documented inline, and repeatedly emphasizes "never invent data" because
engineering drawings are used for procurement/manufacturing decisions.
"""

BOM_EXTRACTION_PROMPT = """\
You are extracting a Bill of Materials from an engineering drawing.

Your task is transcription, not interpretation.

Read ONLY the visible BOM / PARTS LIST table in this image.

Rules:
- Extract only rows that are visibly present in the table.
- Do not infer part names from the drawing geometry.
- Do not rename parts.
- Do not normalize descriptions into more common engineering terms.
- Do not invent missing rows.
- Preserve the visible wording exactly as much as possible.
- If a field is unreadable, return null.
- If there is no visible BOM table, return an empty list.
- Do not use general engineering knowledge to fill gaps.
- Do NOT invent a separate part_name field. The transcribed table text for the \
part belongs ONLY in description.
- Do not create a component name outside bom_items[].description.

Return ONLY JSON.

Schema:
{
  "bom_items": [
    {
      "item_number": "1",
      "part_number": "HB-M8-001",
      "description": "Hexagon Head Bolt M8 x 25",
      "material": "Carbon Steel",
      "quantity": 4,
      "confidence_score": 0.98
    }
  ]
}

If no BOM table is visible, return {"bom_items": []}.
"""

CALLOUT_DETECTION_PROMPT = """\
Detect numbered BOM callout balloons in this engineering drawing.

A valid callout balloon:
- contains a visible item number
- is a distinct circular or balloon-style annotation
- is connected to the drawing by a leader line
- is not a dimension
- is not a section label
- is not title-block text
- is not a grid coordinate
- is not ordinary geometry

Return the bounding box of the BALLOON ONLY.

Do not return the component location.
Do not return the leader endpoint.
Do not identify the component.
Do not infer anything from nearby shapes.

If you are not certain a mark is a real numbered callout balloon, omit it.

Return only balloons with confidence >= 0.85.

Coordinates must be normalized 0–1000.

Field name is bubble_bbox — NEVER use bounding_box.

Return ONLY JSON:

{
  "callouts": [
    {
      "bubble_number": "1",
      "bubble_bbox": {
        "xmin": 100,
        "ymin": 80,
        "xmax": 140,
        "ymax": 120
      },
      "confidence_score": 0.96
    }
  ]
}

If no valid callout balloons are visible, return {"callouts": []}.
"""

DRAWING_METADATA_PROMPT = """\
You are analyzing an engineering drawing's title block only.

Extract, reading text EXACTLY as printed and using null when not legible or \
not present:
   - drawing_number
   - revision

Return ONLY valid JSON (no markdown fences, no commentary) matching exactly:
{
  "drawing_number": string or null,
  "revision": string or null
}
"""

CALLOUT_VERIFICATION_PROMPT = """\
Verify this previously detected engineering callout.

You are given a crop containing a suspected numbered callout bubble.

Check only:

1. Is there actually a numbered callout bubble?
2. What is the exact number?
3. Is a leader line visibly connected to it?
4. Can the leader line endpoint be seen?
5. Does the proposed bubble bounding box surround the actual bubble?

Do NOT invent a bubble, number, leader, or endpoint that is not clearly visible.
Do NOT treat dimensions, notes, revision markers, weld symbols, section labels, \
or ordinary circles as callouts.
If the detection was hallucinated or ambiguous, mark it invalid.

Proposed detection (for reference only — trust the image, not this text):
- proposed_bubble_number: {proposed_bubble_number}
- proposed_bubble_bbox (full-page 0–1000 coords): {proposed_bubble_bbox}

Return ONLY valid JSON.

If the detection is confirmed:

{{
  "valid": true,
  "bubble_number": "3",
  "leader_visible": true,
  "endpoint_visible": true,
  "bbox_surrounds_bubble": true,
  "confidence_score": 0.96
}}

If any detection was hallucinated or ambiguous, return:

{{
  "valid": false,
  "reason": "No clear leader line connected to the bubble"
}}

Rules for valid=false (examples of reasons):
- "No numbered callout bubble visible in the crop"
- "Bubble number is unreadable"
- "No clear leader line connected to the bubble"
- "Leader endpoint is not visible"
- "Proposed bounding box does not surround the bubble"
- "Suspected mark is a dimension/note/symbol, not a callout"

If valid=true:
- bubble_number must be the exact printed number
- leader_visible / endpoint_visible / bbox_surrounds_bubble must be honest booleans
- If bbox_surrounds_bubble is false, you MUST return valid=false instead
- confidence_score is 0.0–1.0 for this verification
"""
