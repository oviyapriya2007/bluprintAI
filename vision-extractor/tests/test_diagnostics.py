"""Unit tests for temporary live-vision diagnostics (no Claude calls)."""

from pathlib import Path

from PIL import Image

from vision_extractor.diagnostics import LiveVisionDiagnostics


def test_diagnostics_writes_expected_artifacts(tmp_path: Path):
    full = tmp_path / "full.png"
    bom = tmp_path / "bom.png"
    callouts = tmp_path / "callouts.png"
    Image.new("RGB", (120, 80), color="white").save(full)
    Image.new("RGB", (40, 30), color="gray").save(bom)
    Image.new("RGB", (90, 70), color="black").save(callouts)

    out = tmp_path / "debug-output" / "doc_test" / "page_001"
    diag = LiveVisionDiagnostics(
        out_dir=out,
        bom_source="crop",
        callout_source="crop",
        record_mode="both",
    )
    diag.set_full_page_image_meta(full)
    diag.save_image_copy(full, "vision_input_full.png")
    diag.save_image_copy(bom, "vision_input_bom.png")
    diag.save_image_copy(callouts, "vision_input_callouts.png")

    diag.record_bom_raw('{"bom_items":[{"item_number":"1"}]}')
    diag.record_bom_parsed({"bom_items": [{"item_number": "1"}, {"item_number": "2"}]})
    diag.record_bom_validated(1)
    diag.record_callout_raw('{"callouts":[]}')
    diag.record_callout_parsed({"callouts": [{"bubble_number": "1"}]})
    diag.record_callout_validated(0)
    diag.extend_warnings(["Skipped invalid BOM row at index 1"])
    diag.finalize(page_id="page_001", document_id="doc_test")

    assert (out / "vision_input_full.png").is_file()
    assert (out / "vision_input_bom.png").is_file()
    assert (out / "vision_input_callouts.png").is_file()
    assert (out / "raw_bom_response.txt").read_text(encoding="utf-8").startswith("{")
    assert (out / "raw_callout_response.txt").is_file()
    assert (out / "parsed_bom.json").is_file()
    assert (out / "parsed_callouts.json").is_file()
    assert (out / "validation_warnings.json").is_file()

    assert diag.vision_input_exists is True
    assert diag.vision_input_width == 120
    assert diag.vision_input_height == 80
    assert diag.parsed_bom_count == 2
    assert diag.parsed_callout_count == 1
    assert diag.validated_bom_count == 1
    assert diag.validated_callout_count == 0


def test_record_mode_bom_ignores_callout_updates(tmp_path: Path):
    diag = LiveVisionDiagnostics(out_dir=tmp_path / "d", record_mode="bom")
    diag.record_bom_raw("bom-raw")
    diag.record_callout_raw("should-ignore")
    diag.record_callout_parsed({"callouts": [1, 2, 3]})
    diag.record_callout_validated(3)

    assert diag.raw_bom_response == "bom-raw"
    assert diag.raw_callout_response is None
    assert diag.parsed_callout_count == 0
    assert diag.validated_callout_count == 0
