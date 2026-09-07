"""Pydantic models implementing the shared BlueprintAI data contract.

Coordinates are always normalized to a 0-1000 scale, regardless of the
source image's pixel dimensions. See utils.normalize_bbox for conversion.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

COORD_MIN = 0.0
COORD_MAX = 1000.0


class BoundingBox(BaseModel):
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @field_validator("xmin", "ymin", "xmax", "ymax")
    @classmethod
    def _within_normalized_range(cls, value: float) -> float:
        if value < COORD_MIN or value > COORD_MAX:
            raise ValueError(
                f"coordinate {value} outside normalized range [{COORD_MIN}, {COORD_MAX}]"
            )
        return value

    @model_validator(mode="after")
    def _check_ordering(self) -> "BoundingBox":
        if self.xmin >= self.xmax:
            raise ValueError(f"xmin ({self.xmin}) must be < xmax ({self.xmax})")
        if self.ymin >= self.ymax:
            raise ValueError(f"ymin ({self.ymin}) must be < ymax ({self.ymax})")
        return self


class BOMItem(BaseModel):
    item_number: str
    part_number: Optional[str] = None
    part_name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    material_specification: Optional[str] = None
    revision: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)

    @field_validator("quantity")
    @classmethod
    def _quantity_non_negative(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError(f"quantity cannot be negative, got {value}")
        return value


class LeaderEndpoint(BaseModel):
    """Normalized (0-1000) point where a callout leader line terminates.

    This is the component/target tip — never the bubble location.
    """

    x: float
    y: float

    @field_validator("x", "y")
    @classmethod
    def _within_normalized_range(cls, value: float) -> float:
        if value < COORD_MIN or value > COORD_MAX:
            raise ValueError(
                f"coordinate {value} outside normalized range [{COORD_MIN}, {COORD_MAX}]"
            )
        return value


LeaderLineStatus = Literal["clear", "unclear", "missing"]


class Callout(BaseModel):
    """A numbered callout bubble on the drawing.

    ``bubble_bbox`` localizes the numbered bubble/circle ONLY.
    ``leader_endpoint`` (when status is ``clear``) is where the leader
    terminates. Vision extraction does not infer components from geometry.
    """

    bubble_number: str
    location_description: Optional[str] = None
    bubble_bbox: BoundingBox
    confidence_score: float = Field(ge=0.0, le=1.0)
    leader_endpoint: Optional[LeaderEndpoint] = None
    leader_line_status: LeaderLineStatus = "missing"

    @model_validator(mode="after")
    def _leader_consistency(self) -> "Callout":
        # Unclear/missing leaders must never carry an invented endpoint.
        if self.leader_line_status in ("unclear", "missing"):
            object.__setattr__(self, "leader_endpoint", None)
        return self


class ExtractedComponent(BaseModel):
    id: str
    item_number: Optional[str] = None
    bubble_number: Optional[str] = None
    part_number: Optional[str] = None
    part_name: Optional[str] = None
    quantity: Optional[int] = None
    material_specification: Optional[str] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    bounding_box: BoundingBox

    @field_validator("quantity")
    @classmethod
    def _quantity_non_negative(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError(f"quantity cannot be negative, got {value}")
        return value


class ExtractionResult(BaseModel):
    drawing_number: Optional[str] = None
    revision: Optional[str] = None
    bom_items: list[BOMItem] = Field(default_factory=list)
    callouts: list[Callout] = Field(default_factory=list)
    components: list[ExtractedComponent] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
    # "mock" only when USE_MOCK=true; live Claude runs always use "claude".
    extraction_source: Literal["claude", "mock"] = "claude"
