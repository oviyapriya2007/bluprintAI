"""Temporary live-vision diagnostics (debug dumps + structured logs).

Used to pinpoint whether extraction failures happen at image loading, model
response, JSON parsing, or validator filtering. Does not alter extraction
results — only observes and writes artifacts under ``debug-output/``.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from PIL import Image

logger = logging.getLogger(__name__)

RecordMode = Literal["both", "bom", "callouts"]
InputSource = Literal["full_page", "crop"]


@dataclass
class LiveVisionDiagnostics:
    """Per-page capture of vision inputs and intermediate extraction artifacts."""

    out_dir: Path
    bom_source: InputSource = "full_page"
    callout_source: InputSource = "full_page"
    record_mode: RecordMode = "both"

    vision_input_exists: bool = False
    vision_input_width: Optional[int] = None
    vision_input_height: Optional[int] = None

    raw_bom_response: Optional[str] = None
    parsed_bom: Any = None
    parsed_bom_count: int = 0
    validated_bom_count: int = 0

    raw_callout_response: Optional[str] = None
    parsed_callouts: Any = None
    parsed_callout_count: int = 0
    validated_callout_count: int = 0

    validation_warnings: list[str] = field(default_factory=list)
    bom_parse_error: Optional[str] = None
    callout_parse_error: Optional[str] = None

    def ensure_out_dir(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def set_full_page_image_meta(self, image_path: Optional[Path]) -> None:
        """Record whether the full-page vision input exists and its dimensions."""
        if image_path is None or not Path(image_path).is_file():
            self.vision_input_exists = False
            self.vision_input_width = None
            self.vision_input_height = None
            return
        self.vision_input_exists = True
        try:
            with Image.open(image_path) as img:
                self.vision_input_width, self.vision_input_height = img.size
        except OSError:
            self.vision_input_exists = False
            self.vision_input_width = None
            self.vision_input_height = None

    def save_image_copy(self, source: Optional[Path], dest_name: str) -> None:
        """Copy an existing image file into the debug directory (if present)."""
        if source is None or not Path(source).is_file():
            return
        self.ensure_out_dir()
        shutil.copy2(source, self.out_dir / dest_name)

    def save_pil_image(self, image: Image.Image, dest_name: str) -> None:
        self.ensure_out_dir()
        image.convert("RGB").save(self.out_dir / dest_name, format="PNG")

    def record_bom_raw(self, raw_text: Optional[str]) -> None:
        if self.record_mode not in ("both", "bom"):
            return
        self.raw_bom_response = raw_text

    def record_bom_parsed(self, parsed: Any, *, error: Optional[str] = None) -> None:
        if self.record_mode not in ("both", "bom"):
            return
        self.parsed_bom = parsed
        self.bom_parse_error = error
        if isinstance(parsed, dict):
            items = parsed.get("bom_items", [])
            self.parsed_bom_count = len(items) if isinstance(items, list) else 0
        else:
            self.parsed_bom_count = 0

    def record_bom_validated(self, count: int) -> None:
        if self.record_mode not in ("both", "bom"):
            return
        self.validated_bom_count = count

    def record_callout_raw(self, raw_text: Optional[str]) -> None:
        if self.record_mode not in ("both", "callouts"):
            return
        if self.raw_callout_response is None:
            self.raw_callout_response = raw_text or ""
        else:
            # Tiled detection may produce multiple responses — keep them all.
            self.raw_callout_response += "\n\n--- TILE BOUNDARY ---\n\n" + (raw_text or "")

    def record_callout_parsed(self, parsed: Any, *, error: Optional[str] = None) -> None:
        if self.record_mode not in ("both", "callouts"):
            return
        self.callout_parse_error = error
        if error:
            return
        if self.parsed_callouts is None:
            self.parsed_callouts = parsed
        elif isinstance(self.parsed_callouts, dict) and isinstance(parsed, dict):
            # Merge tiled callout lists when both look like callout payloads.
            existing = self.parsed_callouts.get("callouts", [])
            incoming = parsed.get("callouts", [])
            if isinstance(existing, list) and isinstance(incoming, list):
                merged = dict(self.parsed_callouts)
                merged["callouts"] = existing + incoming
                self.parsed_callouts = merged
            else:
                self.parsed_callouts = parsed
        else:
            self.parsed_callouts = parsed

        if isinstance(self.parsed_callouts, dict):
            items = self.parsed_callouts.get("callouts", [])
            self.parsed_callout_count = len(items) if isinstance(items, list) else 0
        else:
            self.parsed_callout_count = 0

    def record_callout_validated(self, count: int) -> None:
        if self.record_mode not in ("both", "callouts"):
            return
        # For tiled runs this is called once at the end with the final count.
        self.validated_callout_count = count

    def extend_warnings(self, warnings: list[str]) -> None:
        self.validation_warnings.extend(warnings)

    def write_artifacts(self) -> None:
        """Persist all captured text/JSON artifacts (images saved separately)."""
        self.ensure_out_dir()

        bom_raw = self.raw_bom_response if self.raw_bom_response is not None else ""
        (self.out_dir / "raw_bom_response.txt").write_text(bom_raw, encoding="utf-8")

        callout_raw = (
            self.raw_callout_response if self.raw_callout_response is not None else ""
        )
        (self.out_dir / "raw_callout_response.txt").write_text(
            callout_raw, encoding="utf-8"
        )

        parsed_bom_payload: Any
        if self.bom_parse_error:
            parsed_bom_payload = {"parse_error": self.bom_parse_error, "parsed": self.parsed_bom}
        else:
            parsed_bom_payload = self.parsed_bom if self.parsed_bom is not None else {}
        (self.out_dir / "parsed_bom.json").write_text(
            json.dumps(parsed_bom_payload, indent=2, default=str),
            encoding="utf-8",
        )

        parsed_callout_payload: Any
        if self.callout_parse_error and self.parsed_callouts is None:
            parsed_callout_payload = {
                "parse_error": self.callout_parse_error,
                "parsed": None,
            }
        elif self.callout_parse_error:
            parsed_callout_payload = {
                "parse_error": self.callout_parse_error,
                "parsed": self.parsed_callouts,
            }
        else:
            parsed_callout_payload = (
                self.parsed_callouts if self.parsed_callouts is not None else {}
            )
        (self.out_dir / "parsed_callouts.json").write_text(
            json.dumps(parsed_callout_payload, indent=2, default=str),
            encoding="utf-8",
        )

        (self.out_dir / "validation_warnings.json").write_text(
            json.dumps(self.validation_warnings, indent=2),
            encoding="utf-8",
        )

    def log_summary(self, *, page_id: str, document_id: str) -> None:
        raw_bom_len = len(self.raw_bom_response) if self.raw_bom_response is not None else 0
        raw_callout_len = (
            len(self.raw_callout_response) if self.raw_callout_response is not None else 0
        )
        logger.info(
            "VISION DIAGNOSTICS document_id=%s page_id=%s\n"
            "VISION INPUT EXISTS: %s\n"
            "VISION INPUT WIDTH: %s\n"
            "VISION INPUT HEIGHT: %s\n"
            "VISION INPUT SOURCE FOR BOM: %s\n"
            "VISION INPUT SOURCE FOR CALLOUTS: %s\n"
            "RAW BOM RESPONSE LENGTH: %s\n"
            "RAW CALLOUT RESPONSE LENGTH: %s\n"
            "PARSED BOM COUNT: %s\n"
            "PARSED CALLOUT COUNT: %s\n"
            "VALIDATED BOM COUNT: %s\n"
            "VALIDATED CALLOUT COUNT: %s\n"
            "DEBUG DIR: %s",
            document_id,
            page_id,
            str(self.vision_input_exists).lower(),
            self.vision_input_width if self.vision_input_width is not None else "n/a",
            self.vision_input_height if self.vision_input_height is not None else "n/a",
            self.bom_source,
            self.callout_source,
            raw_bom_len,
            raw_callout_len,
            self.parsed_bom_count,
            self.parsed_callout_count,
            self.validated_bom_count,
            self.validated_callout_count,
            self.out_dir,
        )

    def finalize(self, *, page_id: str, document_id: str) -> None:
        self.write_artifacts()
        self.log_summary(page_id=page_id, document_id=document_id)
