"""Optional live Claude Vision integration test.

Skipped automatically unless a real ANTHROPIC_API_KEY is present in the
environment, so the rest of the suite never needs network access or a key.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; skipping live Claude integration test",
)


def test_live_extraction_returns_valid_result():
    import glob

    from vision_extractor import VisionExtractor

    images = glob.glob("examples/sample_input/*.png") + glob.glob("examples/sample_input/*.jpg")
    if not images:
        pytest.skip("No sample image available in examples/sample_input/")

    os.environ["USE_MOCK"] = "false"
    extractor = VisionExtractor()
    result = extractor.extract_from_image(images[0])
    assert result is not None
    assert isinstance(result.model_dump(), dict)
