"""Tests for second-pass callout verification."""

from PIL import Image

from vision_extractor.models import BoundingBox, Callout, LeaderEndpoint
from vision_extractor.verification import (
    apply_verification_to_callout,
    build_verification_prompt,
    crop_around_bubble,
    parse_verification_response,
    verify_callouts,
)


def test_build_verification_prompt_includes_proposed_detection():
    callout = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=185, ymin=412, xmax=230, ymax=458),
        confidence_score=0.9,
        leader_line_status="clear",
        leader_endpoint=LeaderEndpoint(x=320, y=560),
    )
    prompt = build_verification_prompt(callout)
    assert "proposed_bubble_number: 3" in prompt
    assert "185.0" in prompt
    assert '"valid": true' in prompt or '"valid": true' in prompt.replace(" ", "")


def test_parse_verification_valid():
    result = parse_verification_response(
        {
            "valid": True,
            "bubble_number": "3",
            "leader_visible": True,
            "endpoint_visible": True,
            "bbox_surrounds_bubble": True,
            "confidence_score": 0.96,
        }
    )
    assert result.valid is True
    assert result.bubble_number == "3"
    assert result.confidence_score == 0.96


def test_parse_verification_invalid():
    result = parse_verification_response(
        {
            "valid": False,
            "reason": "No clear leader line connected to the bubble",
        }
    )
    assert result.valid is False
    assert "leader" in result.reason.lower()


def test_parse_verification_bad_bbox_becomes_invalid():
    result = parse_verification_response(
        {
            "valid": True,
            "bubble_number": "3",
            "leader_visible": True,
            "endpoint_visible": True,
            "bbox_surrounds_bubble": False,
            "confidence_score": 0.9,
        }
    )
    assert result.valid is False
    assert "bounding box" in result.reason.lower()


def test_apply_verification_rejects_invalid():
    callout = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=150, ymax=150),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    result = parse_verification_response(
        {"valid": False, "reason": "No numbered callout bubble visible in the crop"}
    )
    assert apply_verification_to_callout(callout, result) is None


def test_apply_verification_updates_leader_flags():
    callout = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=150, ymax=150),
        confidence_score=0.9,
        leader_line_status="clear",
        leader_endpoint=LeaderEndpoint(x=200, y=200),
    )
    result = parse_verification_response(
        {
            "valid": True,
            "bubble_number": "3",
            "leader_visible": True,
            "endpoint_visible": False,
            "bbox_surrounds_bubble": True,
            "confidence_score": 0.88,
        }
    )
    updated = apply_verification_to_callout(callout, result)
    assert updated is not None
    assert updated.leader_line_status == "unclear"
    assert updated.leader_endpoint is None
    assert updated.confidence_score == 0.88


def test_crop_around_bubble_stays_inside_image():
    image = Image.new("RGB", (1000, 800), color=(255, 255, 255))
    box = BoundingBox(xmin=0, ymin=0, xmax=50, ymax=50)
    crop = crop_around_bubble(image, box)
    assert crop.size[0] > 0 and crop.size[1] > 0
    assert crop.size[0] <= 1000 and crop.size[1] <= 800


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def detect_callouts(self, image, prompt):
        self.calls += 1
        return self._responses.pop(0)


def test_verify_callouts_keeps_valid_drops_invalid():
    image = Image.new("RGB", (1000, 1000), color=(255, 255, 255))
    keep = Callout(
        bubble_number="1",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=140, ymax=140),
        confidence_score=0.9,
        leader_line_status="clear",
        leader_endpoint=LeaderEndpoint(x=200, y=200),
    )
    drop = Callout(
        bubble_number="2",
        bubble_bbox=BoundingBox(xmin=500, ymin=500, xmax=540, ymax=540),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    client = _FakeClient(
        [
            '{"valid": true, "bubble_number": "1", "leader_visible": true, '
            '"endpoint_visible": true, "bbox_surrounds_bubble": true, "confidence_score": 0.97}',
            '{"valid": false, "reason": "No numbered callout bubble visible in the crop"}',
        ]
    )
    kept, warnings = verify_callouts(client, image, [keep, drop])
    assert len(kept) == 1
    assert kept[0].bubble_number == "1"
    assert kept[0].confidence_score == 0.97
    assert any("Rejected callout bubble '2'" in w for w in warnings)
    assert client.calls == 2
