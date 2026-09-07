import sys
from pathlib import Path

# Make the vision_extractor package importable without an install step,
# regardless of the directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importing here (before test collection evaluates any module-level
# pytest.mark.skipif conditions, e.g. test_integration.py's GEMINI_API_KEY
# check) guarantees vision_extractor.config's .env loading has already run,
# regardless of which test file pytest happens to collect first.
import vision_extractor  # noqa: E402,F401
