"""
Image helpers for BlueprintAI document preprocessing.

Provides PDF → image conversion, loading, resizing, and cropping.
Uses pdf2image, Pillow, and OpenCV. No AI inference lives here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pdf2image import convert_from_path
from pdf2image.exceptions import (
    PDFInfoNotInstalledError,
    PDFPageCountError,
    PDFPopplerTimeoutError,
    PDFSyntaxError,
)

# Pillow's default MAX_IMAGE_PIXELS (~89.5M) is a decompression-bomb guard
# meant for images from untrusted sources. Large-format engineering sheets
# (ANSI D/E, ARCH E, etc.) rasterized at 300 DPI routinely exceed it -- e.g.
# a 34x44in ANSI E sheet at 300 DPI is ~134M pixels -- which otherwise spams
# DecompressionBombWarning (and, above 2x the default, raises outright) for
# perfectly legitimate drawings produced by our own pdf_to_images() below.
# Raised, not disabled, so a genuinely corrupt/malicious file still trips it.
Image.MAX_IMAGE_PIXELS = 400_000_000

try:
    from .config import ProcessingConfig, DEFAULT_CONFIG
    from .exceptions import (
        CorruptImageError,
        ImageProcessingError,
        InvalidPDFError,
        PopplerError,
        UnsupportedFormatError,
    )
except ImportError:
    from config import ProcessingConfig, DEFAULT_CONFIG
    from exceptions import (
        CorruptImageError,
        ImageProcessingError,
        InvalidPDFError,
        PopplerError,
        UnsupportedFormatError,
    )

# Type aliases for clarity
ImageArray = np.ndarray  # BGR uint8 arrays as used by OpenCV
PilImage = Image.Image
CropBox = tuple[int, int, int, int]  # left, top, right, bottom (Pillow convention)

_SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_EXIF_ORIENTATION_TAG = 274  # standard EXIF Orientation tag id


def pdf_to_images(
    pdf_path: str,
    output_dir: str,
    dpi: int = 300,
    poppler_path: str | None = None,
) -> list[dict]:
    """
    Convert every PDF page into a high-resolution PNG.

    Does not resize pages. Requires Poppler (on PATH or via ``poppler_path`` /
    ``POPPLER_PATH`` / ``DEFAULT_CONFIG.poppler_path``).

    Parameters
    ----------
    pdf_path:
        Path to the source PDF.
    output_dir:
        Directory where page_001.png, page_002.png, ... will be written.
        Created automatically if missing.
    dpi:
        Rasterization density (default 300).
    poppler_path:
        Optional directory containing pdftoppm. Overrides config/env when set.

    Returns
    -------
    list[dict]
        One metadata dict per page:
        {
          "page_number": 1,
          "image_path": "...",
          "width": 4961,
          "height": 3508,
          "dpi": 300,
        }

    Raises
    ------
    FileNotFoundError
        If the PDF path does not exist.
    ValueError
        If dpi is not a positive integer.
    PopplerError / InvalidPDFError / ImageProcessingError
        On conversion or write failures.
    """
    if not isinstance(dpi, int) or dpi <= 0:
        raise ValueError(f"dpi must be a positive integer, got: {dpi!r}")

    source = Path(pdf_path)
    if not source.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not source.is_file():
        raise FileNotFoundError(f"PDF path is not a file: {pdf_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_poppler = poppler_path or DEFAULT_CONFIG.poppler_path
    convert_kwargs: dict[str, Any] = {"dpi": dpi}
    if resolved_poppler:
        convert_kwargs["poppler_path"] = str(resolved_poppler)

    try:
        # Full-resolution conversion — no resize in this function
        pages = convert_from_path(str(source), **convert_kwargs)
    except PDFInfoNotInstalledError as exc:
        raise PopplerError(
            "Poppler is not installed or not on PATH. "
            "Install Poppler and set POPPLER_PATH (Windows) or add it to PATH."
        ) from exc
    except (PDFPageCountError, PDFSyntaxError) as exc:
        raise InvalidPDFError(
            f"Invalid or unreadable PDF '{pdf_path}': {exc}"
        ) from exc
    except PDFPopplerTimeoutError as exc:
        raise PopplerError(
            f"PDF conversion timed out for '{pdf_path}'"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — wrap unknown pdf2image failures
        raise PopplerError(
            f"pdf2image/Poppler failed for '{pdf_path}': {exc}"
        ) from exc

    if not pages:
        raise InvalidPDFError(f"PDF produced no pages: {pdf_path}")

    results: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        filename = f"page_{index:03d}.png"
        image_path = out_dir / filename
        try:
            # Save at native converted resolution (no resize)
            page.save(image_path, format="PNG")
        except OSError as exc:
            raise ImageProcessingError(
                f"Failed to write PDF page image '{image_path.name}': {exc}"
            ) from exc

        width, height = page.size
        results.append(
            {
                "page_number": index,
                "image_path": str(image_path.resolve()),
                "width": width,
                "height": height,
                "dpi": dpi,
            }
        )

    return results


def load_image(image_path: str) -> dict:
    """
    Load a PNG/JPEG, normalize to upright RGB, and return metadata.

    Uses Pillow for EXIF orientation and mode conversion.
    Uses OpenCV to verify the final image can be decoded.

    The original file is never modified. If orientation correction or an
    RGB conversion is required, a normalized copy is written under
    ``processed/`` and that path is returned in ``image_path``.

    Parameters
    ----------
    image_path:
        Path to a .png, .jpg, or .jpeg file.

    Returns
    -------
    dict
        {
          "image_path": "...",
          "width": 3508,
          "height": 2480,
          "mode": "RGB",
          "format": "PNG",
        }

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    UnsupportedFormatError
        If the extension is not PNG/JPEG.
    CorruptImageError / ImageProcessingError
        If the image cannot be opened, converted, or verified.
    """
    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not source.is_file():
        raise FileNotFoundError(f"Image path is not a file: {image_path}")

    suffix = source.suffix.lower()
    if suffix not in _SUPPORTED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(_SUPPORTED_IMAGE_EXTENSIONS))
        raise UnsupportedFormatError(
            f"Unsupported image type '{suffix}'. Allowed: {allowed}"
        )

    try:
        with Image.open(source) as opened:
            opened.load()
            original_format = (opened.format or _format_from_suffix(suffix)).upper()
            if original_format == "JPG":
                original_format = "JPEG"

            needs_orientation = _needs_exif_orientation(opened)
            needs_rgb = opened.mode != "RGB"
            needs_processing = needs_orientation or needs_rgb

            # Correct orientation first (Pillow), then force RGB
            image = ImageOps.exif_transpose(opened)
            if image is None:
                image = opened
            image = image.convert("RGB")
            width, height = image.size

            if needs_processing:
                output_path = _write_normalized_copy(source, image, original_format)
                result_path = output_path
                result_format = _format_from_suffix(output_path.suffix)
            else:
                # Already upright RGB — keep pointing at the untouched original
                result_path = source.resolve()
                result_format = original_format
                image.close()
    except FileNotFoundError:
        raise
    except UnsupportedFormatError:
        raise
    except UnidentifiedImageError as exc:
        raise CorruptImageError(
            f"Corrupt or unreadable image: {image_path}"
        ) from exc
    except OSError as exc:
        raise ImageProcessingError(
            f"Failed to read or write image '{image_path}': {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(
            f"Image processing failed for '{image_path}': {exc}"
        ) from exc

    # OpenCV verification of the file that callers will use next
    _verify_with_opencv(result_path)

    return {
        "image_path": str(result_path),
        "width": width,
        "height": height,
        "mode": "RGB",
        "format": result_format,
    }


def normalize_resolution(
    image_path: str,
    output_path: str,
    max_dimension: int = 7000,
    min_dimension: int = 2000,
) -> dict:
    """
    Normalize an engineering drawing's resolution while preserving aspect ratio.

    - If the longest side exceeds ``max_dimension``, downscale so the longest
      side equals ``max_dimension``.
    - If the longest side is below ``min_dimension``, upscale so the longest
      side equals ``min_dimension`` (only when the image is too small).
    - If already within ``[min_dimension, max_dimension]``, dimensions are
      left unchanged (no unnecessary upscale/downscale).
    - Never distorts; uses Pillow LANCZOS for high-quality resizing.

    The original file is not modified. The result is always written to
    ``output_path``.

    Returns
    -------
    dict
        {
          "original_width": int,
          "original_height": int,
          "processed_width": int,
          "processed_height": int,
          "resized": bool,
        }
    """
    if not isinstance(max_dimension, int) or max_dimension <= 0:
        raise ValueError(f"max_dimension must be a positive int, got: {max_dimension!r}")
    if not isinstance(min_dimension, int) or min_dimension <= 0:
        raise ValueError(f"min_dimension must be a positive int, got: {min_dimension!r}")
    if min_dimension > max_dimension:
        raise ValueError(
            f"min_dimension ({min_dimension}) cannot exceed max_dimension ({max_dimension})"
        )

    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not source.is_file():
        raise FileNotFoundError(f"Image path is not a file: {image_path}")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened)
            if image is None:
                image = opened
            image = image.convert("RGB")
            original_width, original_height = image.size

            target_width, target_height, resized = _fit_dimensions(
                original_width,
                original_height,
                max_dimension=max_dimension,
                min_dimension=min_dimension,
            )

            if resized:
                image = image.resize(
                    (target_width, target_height),
                    resample=Image.Resampling.LANCZOS,
                )

            _save_rgb_image(image, destination)
            processed_width, processed_height = image.size
    except FileNotFoundError:
        raise
    except UnidentifiedImageError as exc:
        raise CorruptImageError(
            f"Corrupt or unreadable image: {image_path}"
        ) from exc
    except OSError as exc:
        raise ImageProcessingError(
            f"Failed to normalize resolution for '{image_path}': {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(
            f"Image processing failed while resizing '{image_path}': {exc}"
        ) from exc

    return {
        "original_width": original_width,
        "original_height": original_height,
        "processed_width": processed_width,
        "processed_height": processed_height,
        "resized": resized,
    }


# Default engineering-drawing layout (normalized 0–1000).
# Drawing: most of the sheet. Title block/BOM: bottom-right.
DEFAULT_DRAWING_REGION = {
    "xmin": 0,
    "ymin": 0,
    "xmax": 1000,
    "ymax": 850,
}
DEFAULT_TITLE_BLOCK_REGION = {
    "xmin": 650,
    "ymin": 720,
    "xmax": 1000,
    "ymax": 1000,
}


def isolate_regions(
    image_path: str,
    output_dir: str,
    *,
    mode: str = "manual",
    drawing_region: dict | None = None,
    title_block_region: dict | None = None,
    drawing_ymax_pct: float | None = None,
    title_block_width_pct: float | None = None,
    title_block_height_pct: float | None = None,
) -> dict:
    """
    Isolate the main drawing area and title-block/BOM region.

    Modes
    -----
    manual:
        Percentage-based / normalized-bbox cropping. Reliable for hackathon use.
        Override with ``drawing_region`` / ``title_block_region`` (0–1000), or
        with percentage helpers:
          - ``drawing_ymax_pct`` — fraction of height covered by the drawing
            (default 0.85 → ymax=850)
          - ``title_block_width_pct`` — width of bottom-right block (default 0.35)
          - ``title_block_height_pct`` — height of bottom-right block (default 0.28)
    heuristic:
        Uses the same stable default layout as manual. No complex CV detection;
        reliability over cleverness for the hackathon.

    The original file is never modified. Crops are written under ``output_dir``.

    Returns
    -------
    dict
        {
          "full_image": "...",
          "drawing_region": "...",
          "title_block_region": "...",
          "regions": {
            "drawing": {"xmin", "ymin", "xmax", "ymax"},
            "title_block": {"xmin", "ymin", "xmax", "ymax"},
          },
          "mode": "manual" | "heuristic",
        }
    """
    mode_normalized = (mode or "manual").strip().lower()
    if mode_normalized not in {"manual", "heuristic"}:
        raise ValueError(
            f"Unsupported isolate_regions mode '{mode}'. "
            "Use 'manual' or 'heuristic'."
        )

    source = Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not source.is_file():
        raise FileNotFoundError(f"Image path is not a file: {image_path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(source) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened)
            if image is None:
                image = opened
            image = image.convert("RGB")
            width, height = image.size

            regions = _resolve_isolation_regions(
                mode=mode_normalized,
                drawing_region=drawing_region,
                title_block_region=title_block_region,
                drawing_ymax_pct=drawing_ymax_pct,
                title_block_width_pct=title_block_width_pct,
                title_block_height_pct=title_block_height_pct,
            )

            stem = source.stem
            full_path = out_dir / f"{stem}_full.png"
            drawing_path = out_dir / f"{stem}_drawing.png"
            title_path = out_dir / f"{stem}_title_block.png"

            _save_rgb_image(image, full_path)

            drawing_crop = _crop_normalized_region(image, regions["drawing"], width, height)
            title_crop = _crop_normalized_region(
                image, regions["title_block"], width, height
            )
            _save_rgb_image(drawing_crop, drawing_path)
            _save_rgb_image(title_crop, title_path)
    except FileNotFoundError:
        raise
    except UnidentifiedImageError as exc:
        raise CorruptImageError(
            f"Corrupt or unreadable image: {image_path}"
        ) from exc
    except OSError as exc:
        raise ImageProcessingError(
            f"Failed to isolate regions for '{image_path}': {exc}"
        ) from exc
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(
            f"Image processing failed during region isolation for '{image_path}': {exc}"
        ) from exc

    return {
        "full_image": str(full_path.resolve()),
        "drawing_region": str(drawing_path.resolve()),
        "title_block_region": str(title_path.resolve()),
        "regions": regions,
        "mode": mode_normalized,
    }


def _resolve_isolation_regions(
    *,
    mode: str,
    drawing_region: dict | None,
    title_block_region: dict | None,
    drawing_ymax_pct: float | None,
    title_block_width_pct: float | None,
    title_block_height_pct: float | None,
) -> dict[str, dict[str, int]]:
    """Build normalized drawing / title-block boxes for the chosen mode."""
    # Heuristic: stable default layout only (no advanced CV for hackathon).
    if mode == "heuristic":
        return {
            "drawing": dict(DEFAULT_DRAWING_REGION),
            "title_block": dict(DEFAULT_TITLE_BLOCK_REGION),
        }

    # Manual: start from defaults, then apply percentage / explicit overrides.
    drawing = dict(DEFAULT_DRAWING_REGION)
    title_block = dict(DEFAULT_TITLE_BLOCK_REGION)

    if drawing_ymax_pct is not None:
        drawing["ymax"] = _pct_to_norm(drawing_ymax_pct)

    if title_block_width_pct is not None or title_block_height_pct is not None:
        width_pct = (
            title_block_width_pct
            if title_block_width_pct is not None
            else (NORMALIZED_COORD_MAX - title_block["xmin"]) / NORMALIZED_COORD_MAX
        )
        height_pct = (
            title_block_height_pct
            if title_block_height_pct is not None
            else (NORMALIZED_COORD_MAX - title_block["ymin"]) / NORMALIZED_COORD_MAX
        )
        title_block["xmin"] = NORMALIZED_COORD_MAX - _pct_to_norm(width_pct)
        title_block["ymin"] = NORMALIZED_COORD_MAX - _pct_to_norm(height_pct)
        title_block["xmax"] = NORMALIZED_COORD_MAX
        title_block["ymax"] = NORMALIZED_COORD_MAX

    if drawing_region is not None:
        drawing = _normalize_region_dict(drawing_region, name="drawing")
    if title_block_region is not None:
        title_block = _normalize_region_dict(title_block_region, name="title_block")

    _validate_region_dict(drawing, name="drawing")
    _validate_region_dict(title_block, name="title_block")
    return {"drawing": drawing, "title_block": title_block}


def _pct_to_norm(pct: float) -> int:
    """Convert a 0–1 (or 0–100) percentage to a 0–1000 normalized int."""
    value = float(pct)
    if value > 1.0:
        # Allow 85 meaning 85% for convenience
        value = value / 100.0
    if value <= 0.0 or value > 1.0:
        raise ValueError(f"Percentage must be in (0, 1] or (0, 100], got: {pct!r}")
    return int(round(value * NORMALIZED_COORD_MAX))


def _normalize_region_dict(region: dict, *, name: str) -> dict[str, int]:
    required = ("xmin", "ymin", "xmax", "ymax")
    missing = [key for key in required if key not in region]
    if missing:
        raise ValueError(f"{name} region missing keys: {missing}")
    return {
        "xmin": int(round(float(region["xmin"]))),
        "ymin": int(round(float(region["ymin"]))),
        "xmax": int(round(float(region["xmax"]))),
        "ymax": int(round(float(region["ymax"]))),
    }


def _validate_region_dict(region: dict[str, int], *, name: str) -> None:
    xmin, ymin, xmax, ymax = (
        region["xmin"],
        region["ymin"],
        region["xmax"],
        region["ymax"],
    )
    for key, value in region.items():
        if value < 0 or value > NORMALIZED_COORD_MAX:
            raise ValueError(
                f"{name} region {key}={value} outside 0–{NORMALIZED_COORD_MAX}"
            )
    if xmax <= xmin or ymax <= ymin:
        raise ValueError(f"Invalid {name} region box: {region}")


def _crop_normalized_region(
    image: PilImage,
    region: dict[str, int],
    image_width: int,
    image_height: int,
) -> PilImage:
    """Crop using a normalized 0–1000 bbox; returns a new Pillow image."""
    xmin, ymin, xmax, ymax = normalized_bbox_to_pixels(
        region["xmin"],
        region["ymin"],
        region["xmax"],
        region["ymax"],
        image_width,
        image_height,
    )
    # Ensure at least a 1px crop even after rounding
    if xmax <= xmin:
        xmax = min(image_width, xmin + 1)
    if ymax <= ymin:
        ymax = min(image_height, ymin + 1)
    return image.crop((xmin, ymin, xmax, ymax))


def _fit_dimensions(
    width: int,
    height: int,
    *,
    max_dimension: int,
    min_dimension: int,
) -> tuple[int, int, bool]:
    """
    Compute target size preserving aspect ratio.

    Returns (width, height, resized).
    """
    longest = max(width, height)
    if longest <= 0:
        raise ImageProcessingError(f"Invalid image dimensions: {width}x{height}")

    if longest > max_dimension:
        target = max_dimension
    elif longest < min_dimension:
        # Necessary upscale only for drawings that are too small
        target = min_dimension
    else:
        # Already in a reasonable range — leave unchanged
        return width, height, False

    if width >= height:
        new_w = target
        new_h = max(1, int(round(height * (target / float(width)))))
    else:
        new_h = target
        new_w = max(1, int(round(width * (target / float(height)))))

    return new_w, new_h, True


def _save_rgb_image(image: PilImage, destination: Path) -> None:
    """Save an RGB image; format inferred from destination suffix."""
    suffix = destination.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        image.save(
            destination,
            format="JPEG",
            quality=DEFAULT_CONFIG.jpeg_quality,
            optimize=True,
        )
    else:
        # .png or unspecified — write PNG bytes to the given path
        image.save(
            destination,
            format="PNG",
            compress_level=DEFAULT_CONFIG.png_compress_level,
        )


def _needs_exif_orientation(image: PilImage) -> bool:
    """Return True when EXIF Orientation is present and not identity (1)."""
    try:
        orientation = image.getexif().get(_EXIF_ORIENTATION_TAG)
    except Exception:  # noqa: BLE001 — treat missing/broken EXIF as no-op
        return False
    return orientation is not None and orientation != 1


def _format_from_suffix(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix == ".png":
        return "PNG"
    if suffix in (".jpg", ".jpeg"):
        return "JPEG"
    return suffix.lstrip(".").upper() or "PNG"


def _write_normalized_copy(
    source: Path,
    image: PilImage,
    original_format: str,
) -> Path:
    """
    Save an RGB (optionally re-oriented) copy under processed/.

    Original file is left untouched.
    """
    output_dir = DEFAULT_CONFIG.ensure_output_dir()
    # Prefer PNG for lossless drawings; keep JPEG when the source was JPEG
    if original_format == "JPEG":
        destination = output_dir / f"{source.stem}_normalized.jpg"
        image.save(
            destination,
            format="JPEG",
            quality=DEFAULT_CONFIG.jpeg_quality,
            optimize=True,
        )
    else:
        destination = output_dir / f"{source.stem}_normalized.png"
        image.save(
            destination,
            format="PNG",
            compress_level=DEFAULT_CONFIG.png_compress_level,
        )
    return destination.resolve()


def _verify_with_opencv(path: Path) -> None:
    """Ensure OpenCV can decode the image; raise CorruptImageError on failure."""
    array = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if array is None:
        raise CorruptImageError(f"Corrupt or unreadable image: {path}")


def load_image_cv(path: Path | str) -> ImageArray:
    """
    Load an image from disk as an OpenCV BGR ndarray.

    Low-level helper retained for callers that need pixel buffers.
    Prefer load_image() for normalized PNG/JPEG preprocessing metadata.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"OpenCV could not decode image: {path}")
    return image


def pil_to_cv(image: PilImage) -> ImageArray:
    """Convert a Pillow RGB/RGBA image to an OpenCV BGR ndarray."""
    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cv_to_pil(image: ImageArray) -> PilImage:
    """Convert an OpenCV BGR ndarray to a Pillow RGB image."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def resize_image(
    image: Union[ImageArray, PilImage],
    max_resolution: Optional[int] = None,
    config: ProcessingConfig = DEFAULT_CONFIG,
) -> Union[ImageArray, PilImage]:
    """
    Downscale so the longer side does not exceed `max_resolution`.

    Preserves aspect ratio. Returns the same type as the input (ndarray or PIL).
    """
    limit = max_resolution if max_resolution is not None else config.max_resolution
    is_pil = isinstance(image, Image.Image)

    if is_pil:
        width, height = image.size
    else:
        height, width = image.shape[:2]

    longest = max(width, height)
    if longest <= limit:
        return image

    scale = limit / float(longest)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))

    if is_pil:
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def crop_image(
    image: Union[ImageArray, PilImage],
    box: CropBox,
) -> Union[ImageArray, PilImage]:
    """
    Crop using a (left, top, right, bottom) box in pixel coordinates.

    Coordinates follow Pillow's convention for both PIL and OpenCV inputs.
    """
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        raise ValueError(f"Invalid crop box: {box}")

    if isinstance(image, Image.Image):
        return image.crop((left, top, right, bottom))

    # OpenCV: rows = y, cols = x
    return image[top:bottom, left:right].copy()


def save_image(
    image: Union[ImageArray, PilImage],
    destination: Path | str,
    config: ProcessingConfig = DEFAULT_CONFIG,
) -> Path:
    """
    Persist an image to disk. Format is inferred from the destination suffix.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    suffix = destination.suffix.lower()
    pil_image = image if isinstance(image, Image.Image) else cv_to_pil(image)

    if suffix in (".jpg", ".jpeg"):
        pil_image = pil_image.convert("RGB")
        pil_image.save(destination, quality=config.jpeg_quality, optimize=True)
    elif suffix == ".png":
        pil_image.save(destination, compress_level=config.png_compress_level)
    else:
        destination = destination.with_suffix(".png")
        pil_image.save(destination, compress_level=config.png_compress_level)

    return destination


def load_document_pages(
    path: Path | str,
    config: ProcessingConfig = DEFAULT_CONFIG,
) -> list[PilImage]:
    """
    Load a PDF or raster image into a list of Pillow pages (in memory).

    PDFs may yield multiple pages; PNG/JPEG always yield a single-element list.
    For disk-backed high-DPI conversion with metadata, use pdf_to_images().
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        try:
            convert_kwargs: dict[str, Any] = {"dpi": config.dpi}
            if config.poppler_path:
                convert_kwargs["poppler_path"] = str(config.poppler_path)
            return convert_from_path(str(path), **convert_kwargs)
        except PDFInfoNotInstalledError as exc:
            raise PopplerError(
                "Poppler is not installed or not on PATH. "
                "Install Poppler and set POPPLER_PATH (Windows) or add it to PATH."
            ) from exc
        except (PDFPageCountError, PDFSyntaxError) as exc:
            raise InvalidPDFError(f"Invalid or unreadable PDF '{path}': {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise PopplerError(f"pdf2image/Poppler failed for '{path}': {exc}") from exc

    if suffix in (".png", ".jpg", ".jpeg"):
        return [Image.open(path).convert("RGB")]

    raise UnsupportedFormatError(f"Unsupported image source: {suffix}")


# ---------------------------------------------------------------------------
# BlueprintAI normalized coordinates (0–1000)
# ---------------------------------------------------------------------------

NORMALIZED_COORD_MAX = 1000


def pixel_bbox_to_normalized(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """
    Convert a pixel bounding box to BlueprintAI normalized coordinates (0–1000).

    Mapping:
        norm_x = pixel_x / image_width  * 1000
        norm_y = pixel_y / image_height * 1000

    Example (5000×3000, box 500,300,1000,600) → (100, 100, 200, 200).
    """
    _validate_image_size(image_width, image_height)
    _validate_bbox_order(xmin, ymin, xmax, ymax)

    nxmin = (xmin / image_width) * NORMALIZED_COORD_MAX
    nymin = (ymin / image_height) * NORMALIZED_COORD_MAX
    nxmax = (xmax / image_width) * NORMALIZED_COORD_MAX
    nymax = (ymax / image_height) * NORMALIZED_COORD_MAX

    return (
        _clamp(nxmin, 0.0, float(NORMALIZED_COORD_MAX)),
        _clamp(nymin, 0.0, float(NORMALIZED_COORD_MAX)),
        _clamp(nxmax, 0.0, float(NORMALIZED_COORD_MAX)),
        _clamp(nymax, 0.0, float(NORMALIZED_COORD_MAX)),
    )


def normalized_bbox_to_pixels(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    """
    Convert a BlueprintAI normalized bounding box (0–1000) back to pixels.

    Mapping:
        pixel_x = norm_x / 1000 * image_width
        pixel_y = norm_y / 1000 * image_height

    Results are rounded to the nearest integer and clamped to the image bounds.
    """
    _validate_image_size(image_width, image_height)
    _validate_bbox_order(xmin, ymin, xmax, ymax)

    pxmin = (xmin / NORMALIZED_COORD_MAX) * image_width
    pymin = (ymin / NORMALIZED_COORD_MAX) * image_height
    pxmax = (xmax / NORMALIZED_COORD_MAX) * image_width
    pymax = (ymax / NORMALIZED_COORD_MAX) * image_height

    return (
        int(round(_clamp(pxmin, 0.0, float(image_width)))),
        int(round(_clamp(pymin, 0.0, float(image_height)))),
        int(round(_clamp(pxmax, 0.0, float(image_width)))),
        int(round(_clamp(pymax, 0.0, float(image_height)))),
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _validate_image_size(image_width: int, image_height: int) -> None:
    if image_width <= 0 or image_height <= 0:
        raise ValueError(
            f"image_width and image_height must be positive, got: "
            f"{image_width}x{image_height}"
        )


def _validate_bbox_order(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
) -> None:
    if xmax < xmin or ymax < ymin:
        raise ValueError(
            f"Invalid bbox order: ({xmin}, {ymin}, {xmax}, {ymax})"
        )
