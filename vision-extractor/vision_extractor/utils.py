"""Reusable helpers: coordinate normalization and image loading."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

NORMALIZED_MIN = 0.0
NORMALIZED_MAX = 1000.0

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def clamp(value: float, low: float = NORMALIZED_MIN, high: float = NORMALIZED_MAX) -> float:
    """Clamp value into [low, high]."""
    return max(low, min(high, value))


def normalize_coordinate(pixel_value: float, dimension_size: float) -> float:
    """Convert a single pixel coordinate into the 0-1000 normalized scale.

    normalized = pixel / dimension_size * 1000, clamped to [0, 1000].
    """
    if dimension_size <= 0:
        raise ValueError(f"dimension_size must be positive, got {dimension_size}")
    normalized = (pixel_value / dimension_size) * NORMALIZED_MAX
    return clamp(normalized)


def normalize_bbox_pixels(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    image_width: float,
    image_height: float,
) -> dict[str, float]:
    """Convert a pixel-space bounding box into normalized 0-1000 coordinates."""
    return {
        "xmin": normalize_coordinate(xmin, image_width),
        "ymin": normalize_coordinate(ymin, image_height),
        "xmax": normalize_coordinate(xmax, image_width),
        "ymax": normalize_coordinate(ymax, image_height),
    }


def is_already_normalized(xmin: float, ymin: float, xmax: float, ymax: float) -> bool:
    """Heuristic: values already within [0, 1000] are assumed normalized already.

    Gemini is prompted to return normalized coordinates directly, but this
    guards against a model that occasionally echoes raw pixel values for a
    small image (which would coincidentally also fall under 1000).
    """
    return all(0.0 <= v <= NORMALIZED_MAX for v in (xmin, ymin, xmax, ymax))


def load_image(image_path: str | Path) -> Image.Image:
    """Load an image file (PNG/JPEG/JPG) as a PIL Image, validating the extension."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension '{path.suffix}'. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return Image.open(path).convert("RGB")


def get_image_dimensions(image: Image.Image) -> tuple[int, int]:
    """Return (width, height) of a PIL Image."""
    return image.size
