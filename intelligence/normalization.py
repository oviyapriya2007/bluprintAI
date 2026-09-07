"""Deterministic identifier normalization.

Engineering BOM/callout data represents the same identifier in many
surface forms: ``3``, ``"3"``, ``"03"``, ``"Item 3"``, ``"BUBBLE 3"``,
``"Bubble-3"``. To match a bubble number to a BOM item number reliably we
need a single canonical form for each of these -- without ever guessing
at meaning.

Rule (intentionally simple and auditable): an identifier is considered
normalizable only if it contains *exactly one* run of digits. That run
is taken as the identifier, with leading zeros stripped. Anything else
(no digits, multiple separate digit runs, non-integer numbers) is
declared ambiguous and returned as ``None`` -- callers must not guess
and must instead flag the value for human review.

This deliberately does NOT do fuzzy/approximate matching. Two values
either normalize to the same canonical string, or they don't match.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_DIGIT_RUN = re.compile(r"\d+")


def normalize_identifier(raw: Any) -> Optional[str]:
    """Return a canonical string identifier for ``raw``, or ``None``.

    ``None`` means "this value is ambiguous -- do not attempt to match
    it automatically." Examples of ambiguous input: empty strings,
    strings with no digits, strings with multiple separate digit runs
    (e.g. "3-4"), and non-integer numbers (e.g. 3.5).
    """
    if raw is None:
        return None

    if isinstance(raw, bool):
        # bool is a subclass of int in Python; explicitly reject it so
        # a stray True/False never silently becomes "1"/"0".
        return None

    if isinstance(raw, int):
        return str(raw)

    if isinstance(raw, float):
        if raw.is_integer():
            return str(int(raw))
        return None  # e.g. 3.5 has no unambiguous integer identifier

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        digit_runs = _DIGIT_RUN.findall(text)
        if len(digit_runs) != 1:
            return None  # zero or multiple digit groups -> ambiguous
        digits = digit_runs[0]
        try:
            return str(int(digits))  # strips leading zeros ("03" -> "3")
        except ValueError:
            return None

    return None
