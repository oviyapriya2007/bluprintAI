"""
classify.py -- Stage 4 of the BlueprintAI hybrid detection pipeline.

This is the ONLY stage that calls the Claude API. It takes cropped
balloon/callout candidates from callout_detect.py and asks Claude a single
narrowly-scoped question per crop: "Is this a valid BOM balloon/callout,
and if so what number is printed inside it?" Claude never sees the full
page, never returns coordinates, and never counts anything across the
sheet -- all of that comes from callout_detect.py.

Calls are parallelized. There is no existing asyncio pattern anywhere else
in this codebase to match (document-processor, vision-extractor, and
intelligence are all synchronous), so a plain ThreadPoolExecutor is used
per the project's own stated fallback.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

if __package__:
    from .callout_detect import CalloutCandidate
    from .config import get_settings
else:  # flat imports when run as a standalone script from backend/
    from callout_detect import CalloutCandidate
    from config import get_settings

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = (
    "You are looking at a small cropped region from an engineering drawing. "
    "Is this a valid BOM balloon/callout (a circle or similar enclosed shape "
    "containing a reference number, used to link the drawing to a "
    "bill-of-materials row)? If yes, what number is printed inside it?\n\n"
    "Respond with ONLY a JSON object and nothing else: "
    '{"is_balloon": true|false, "number": <integer or null>, "confidence": <0.0-1.0>}'
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class ClassificationResult:
    crop_id: str
    is_balloon: bool
    number: Optional[int]
    confidence: float
    error: Optional[str] = None


def classify_candidates(candidates: list[CalloutCandidate]) -> list[ClassificationResult]:
    """Classify every candidate crop, in parallel.

    Never raises for an individual crop -- a failed request or unparseable
    response comes back as ``is_balloon=False`` with ``confidence=0.0`` and
    an ``error`` note, so one bad crop never aborts the whole batch.
    """
    if not candidates:
        return []

    settings = get_settings()

    if settings.use_mock_classify:
        logger.warning(
            "[classify] ANTHROPIC_API_KEY not set (or USE_MOCK_CLASSIFY=true); "
            "returning deterministic mock classifications for %d candidate(s)",
            len(candidates),
        )
        results = [_mock_classify(c, i) for i, c in enumerate(candidates, start=1)]
    else:
        client = _build_client(settings)
        results = [None] * len(candidates)
        with ThreadPoolExecutor(max_workers=settings.classify_max_workers) as pool:
            future_to_index = {
                pool.submit(_classify_one, client, settings, candidate): index
                for index, candidate in enumerate(candidates)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                results[index] = future.result()

    balloon_count = sum(1 for r in results if r.is_balloon)
    logger.info(
        "[classify] classified %d candidate(s): classified as balloons: %d",
        len(results),
        balloon_count,
    )
    return results


def _build_client(settings):
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "classify.py requires the 'anthropic' package. Install it with "
            "`pip install anthropic`, or set USE_MOCK_CLASSIFY=true to run "
            "without an API key."
        ) from exc
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _classify_one(client, settings, candidate: CalloutCandidate) -> ClassificationResult:
    try:
        image_b64 = base64.standard_b64encode(candidate.crop_bytes).decode("ascii")
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=200,
            timeout=settings.classify_timeout_seconds,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": CLASSIFY_PROMPT},
                    ],
                }
            ],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return _parse_classification(candidate.crop_id, text)
    except Exception as exc:  # noqa: BLE001 -- one bad crop must not abort the batch
        logger.error("[classify] %s: request failed: %s", candidate.crop_id, exc)
        return ClassificationResult(
            crop_id=candidate.crop_id,
            is_balloon=False,
            number=None,
            confidence=0.0,
            error=str(exc),
        )


def _parse_classification(crop_id: str, text: str) -> ClassificationResult:
    match = _JSON_OBJECT_RE.search(text or "")
    if not match:
        return ClassificationResult(
            crop_id=crop_id,
            is_balloon=False,
            number=None,
            confidence=0.0,
            error=f"unparseable response: {(text or '')[:200]!r}",
        )
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return ClassificationResult(
            crop_id=crop_id,
            is_balloon=False,
            number=None,
            confidence=0.0,
            error=f"invalid JSON: {exc}",
        )

    is_balloon = bool(parsed.get("is_balloon", False))

    raw_number = parsed.get("number")
    try:
        number = int(raw_number) if raw_number is not None else None
    except (TypeError, ValueError):
        number = None

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if is_balloon and number is None:
        # Claude said "yes" but gave no usable number -- treat as
        # not-yet-trustworthy rather than letting a numberless balloon
        # silently match nothing downstream in reconcile.py.
        is_balloon = False

    return ClassificationResult(
        crop_id=crop_id, is_balloon=is_balloon, number=number, confidence=confidence
    )


def _mock_classify(candidate: CalloutCandidate, sequence: int) -> ClassificationResult:
    """Deterministic stand-in used when no ANTHROPIC_API_KEY is configured,
    mirroring the mock-mode pattern already established by
    vision_extractor.mock_data.build_mock_extraction_result."""
    return ClassificationResult(
        crop_id=candidate.crop_id, is_balloon=True, number=sequence, confidence=0.5
    )
