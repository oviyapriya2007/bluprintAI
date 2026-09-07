"""Prompt templates for Gemini multimodal engineering-drawing extraction.

Kept as plain strings (no templating engine) so they're easy to tune during
the hackathon. Each prompt demands strict JSON output matching the schema
documented inline, and repeatedly emphasizes "never invent data" because
engineering drawings are used for procurement/manufacturing decisions.
"""

BOM_EXTRACTION_PROMPT = """\
You are an expert mechanical/manufacturing engineer analyzing an engineering \
drawing image to extract its Bill of Materials (BOM) / parts list / title block data.

INSTRUCTIONS:
1. Inspect the ENTIRE image carefully, including any parts list tables, BOM \
tables, title blocks, and revision tables. These are often in a corner \
(commonly bottom-right or top-right) but can appear anywhere.
2. For each row in the BOM/parts list table, extract:
   - item_number (the row's item/find number, e.g. "1", "2", "3A")
   - part_number (manufacturer or internal part number, if present)
   - part_name (the part's name/title)
   - description (any additional descriptive text distinct from part_name)
   - quantity (integer count required for the assembly)
   - material_specification (material or spec callout, e.g. "Grade 8.8 Carbon Steel")
   - revision (revision letter/number for that row, if shown)
3. Also extract drawing-level metadata if visible: drawing_number and \
overall revision (from the title block, NOT a BOM row).
4. Read text EXACTLY as printed. Preserve capitalization, hyphens, and units.
5. Carefully distinguish separate table rows from each other. Do not merge \
two rows into one, and do not split one row into two.
6. NEVER invent or guess a value that is not legible or not present in the \
image. If a field cannot be determined, set it to null.
7. Assign a confidence_score between 0.0 and 1.0 for each BOM row, reflecting \
how certain you are about the values you extracted (low resolution, blur, \
or partial occlusion should lower confidence).
8. Be robust to: low resolution, tiny table text, multiple drawing views on \
the same sheet, crowded/dense drawings, and title blocks that resemble BOM \
tables but are not (do not confuse the title block's own metadata fields \
with parts-list rows unless they clearly represent a BOM entry).

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown fences, no commentary) matching exactly:
{
  "drawing_number": string or null,
  "revision": string or null,
  "bom_items": [
    {
      "item_number": string,
      "part_number": string or null,
      "part_name": string or null,
      "description": string or null,
      "quantity": integer or null,
      "material_specification": string or null,
      "revision": string or null,
      "confidence_score": number between 0.0 and 1.0
    }
  ]
}
If no BOM table is visible, return an empty "bom_items" array rather than \
inventing rows.
"""

CALLOUT_DETECTION_PROMPT = """\
You are an expert mechanical/manufacturing engineer analyzing an engineering \
drawing image to detect numbered callout ("balloon"/"bubble") annotations.

INSTRUCTIONS:
1. Inspect the ENTIRE drawing canvas, including all views, not just one area.
2. Identify numbered callout bubbles: these are typically circles, ovals, or \
flag shapes containing a single number, connected to a part or feature by a \
leader line (a thin line, often with an arrow or dot at the part).
3. For each bubble found, extract:
   - bubble_number (the number/text inside the bubble, as printed)
   - location_description (brief description of what it points to or where \
     it is on the sheet, e.g. "top-left view, near flange bolt", if you can \
     tell; otherwise null)
   - bounding_box: the bubble's bounding box in NORMALIZED coordinates on a \
     0-1000 scale for BOTH axes, where (0,0) is the top-left corner of the \
     image and (1000,1000) is the bottom-right corner. Do NOT return raw \
     pixel coordinates.
       xmin/ymin = top-left corner of the bubble shape
       xmax/ymax = bottom-right corner of the bubble shape
   - confidence_score between 0.0 and 1.0 for how certain you are this is a \
     genuine callout bubble at that exact location.
4. DO NOT confuse the following with callout bubbles:
   - Dimension values and dimension lines (numbers next to arrows measuring \
     length/diameter/angle are dimensions, not callouts)
   - Revision numbers/letters in the revision table or title block
   - Section/view labels (e.g. "SECTION A-A", "VIEW B") unless they are \
     inside a genuine numbered bubble shape
   - Datum reference letters or GD&T frame contents
5. Be robust to: low resolution, tiny bubble text, multiple views, crowded \
drawings with many overlapping leader lines and dimension annotations.
6. NEVER invent a callout that is not actually present in the image. If you \
are unsure whether a mark is a callout bubble, either omit it or assign it a \
low confidence_score rather than fabricating certainty.

OUTPUT FORMAT:
Return ONLY valid JSON (no markdown fences, no commentary) matching exactly:
{
  "callouts": [
    {
      "bubble_number": string,
      "location_description": string or null,
      "bounding_box": {
        "xmin": number (0-1000),
        "ymin": number (0-1000),
        "xmax": number (0-1000),
        "ymax": number (0-1000)
      },
      "confidence_score": number between 0.0 and 1.0
    }
  ]
}
If no callout bubbles are visible, return an empty "callouts" array rather \
than inventing any.
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
