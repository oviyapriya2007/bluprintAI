import sys
from pathlib import Path

# Make the vision_extractor package importable without an install step,
# regardless of the directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
