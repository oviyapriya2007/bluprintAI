"""
Person 3 output models for BlueprintAI document preprocessing.

Pydantic models only — no BOM extraction, Gemini, FastAPI, or database shapes.
Coordinates use the BlueprintAI normalized 0–1000 system where applicable.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class BoundingRegion(BaseModel):
    """Axis-aligned region in BlueprintAI normalized coordinates (0–1000)."""

    xmin: int = Field(..., ge=0, le=1000, description="Left edge (0–1000)")
    ymin: int = Field(..., ge=0, le=1000, description="Top edge (0–1000)")
    xmax: int = Field(..., ge=0, le=1000, description="Right edge (0–1000)")
    ymax: int = Field(..., ge=0, le=1000, description="Bottom edge (0–1000)")

    @model_validator(mode="after")
    def validate_box_order(self) -> BoundingRegion:
        if self.xmax <= self.xmin or self.ymax <= self.ymin:
            raise ValueError(
                f"Invalid bounding region: ({self.xmin}, {self.ymin}, "
                f"{self.xmax}, {self.ymax})"
            )
        return self


class ProcessingError(BaseModel):
    """Structured error from Person 3 validation or preprocessing."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable explanation")
    field: Optional[str] = Field(
        default=None,
        description="Related input field, if any",
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based page number when the error is page-specific",
    )


class ProcessedPage(BaseModel):
    """One processed page from an engineering drawing document."""

    page_id: str = Field(..., description="Stable page id, e.g. page_001")
    page_number: int = Field(..., ge=1, description="1-based page number")
    image_path: str = Field(..., description="Path to the full-page raster image")
    width: int = Field(..., gt=0, description="Page image width in pixels")
    height: int = Field(..., gt=0, description="Page image height in pixels")
    drawing_region_path: Optional[str] = Field(
        default=None,
        description="Path to isolated main drawing crop, if produced",
    )
    title_block_region_path: Optional[str] = Field(
        default=None,
        description="Path to isolated title-block/BOM crop, if produced",
    )
    drawing_region: Optional[BoundingRegion] = Field(
        default=None,
        description="Normalized drawing crop box (0–1000), if isolated",
    )
    title_block_region: Optional[BoundingRegion] = Field(
        default=None,
        description="Normalized title-block crop box (0–1000), if isolated",
    )


class ProcessedDocument(BaseModel):
    """
    Final Person 3 preprocessing output for one uploaded drawing document.

    Independent of BOM extraction and Gemini — paths and geometry only.
    """

    document_id: str = Field(..., description="Stable document id, e.g. doc_001")
    original_filename: str = Field(..., description="Original upload filename")
    file_type: str = Field(..., description="pdf | png | jpg | jpeg")
    page_count: int = Field(..., ge=0, description="Number of processed pages")
    pages: list[ProcessedPage] = Field(
        default_factory=list,
        description="Per-page preprocessing results",
    )
    status: Literal["processed", "failed", "partial"] = Field(
        default="processed",
        description="Overall preprocessing status",
    )
    errors: list[ProcessingError] = Field(
        default_factory=list,
        description="Validation or preprocessing errors, if any",
    )

    @field_validator("file_type")
    @classmethod
    def normalize_file_type(cls, value: str) -> str:
        normalized = value.strip().lower().lstrip(".")
        if normalized == "jpg":
            return "jpg"
        if normalized == "jpeg":
            return "jpeg"
        return normalized

    @model_validator(mode="after")
    def validate_page_count(self) -> ProcessedDocument:
        if self.page_count != len(self.pages):
            raise ValueError(
                f"page_count ({self.page_count}) does not match "
                f"len(pages) ({len(self.pages)})"
            )
        return self
