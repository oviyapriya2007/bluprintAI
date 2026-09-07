"""Minimal CLI for locally exercising the extractor.

Usage:
    python -m vision_extractor.cli --image examples/sample_input/sample.png --mock
    python -m vision_extractor.cli --mock
    python -m vision_extractor.cli --image drawing.png
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from .extractor import VisionExtractor
from .mock_data import build_mock_extraction_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the vision_extractor module locally.")
    parser.add_argument("--image", type=str, default=None, help="Path to a PNG/JPG drawing image")
    parser.add_argument("--mock", action="store_true", help="Force mock mode (no Gemini call)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.mock:
        os.environ["USE_MOCK"] = "true"

    if args.image:
        extractor = VisionExtractor()
        result = extractor.extract_from_image(args.image)
    else:
        result = build_mock_extraction_result()

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
