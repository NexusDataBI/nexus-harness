"""Normalize frontend visual-reviewer output into Plan 2 findings.

Confirmed blocker/high fail the visual gate. Medium/low are retained.
This module does not create a second Done Gate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from nexus_harness.completion import (
    _BLOCKING_FINDINGS,
    _finding_confirmed,
    _finding_severity,
)
from nexus_harness.visual import VisualEvidence

FINDING_CATEGORIES = frozenset(
    {
        "layout",
        "responsive",
        "state",
        "motion",
        "accessibility",
        "design-system",
    }
)


class UnknownCategoryError(ValueError):
    """Reviewer category is outside the closed visual-finding set."""


@dataclass(frozen=True)
class VisualFinding:
    severity: str
    category: str
    description: str
    route: str
    confidence: float | str | None = None
    viewport: str | None = None
    screenshot: str | None = None
    evidence: object = None
    confirmed: bool = False
    status: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "route": self.route,
            "confirmed": self.confirmed,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.viewport is not None:
            payload["viewport"] = self.viewport
        if self.screenshot is not None:
            payload["screenshot"] = self.screenshot
        if self.evidence is not None:
            payload["evidence"] = self.evidence
        if self.status is not None:
            payload["status"] = self.status
        return payload


def normalize_finding(raw) -> VisualFinding:
    if not isinstance(raw, dict):
        raise TypeError("reviewer finding must be a dict")
    category = str(raw.get("category") or "").strip().lower()
    if category not in FINDING_CATEGORIES:
        raise UnknownCategoryError(f"unknown visual finding category: {category!r}")
    status = _opt_str(raw.get("status"))
    screenshot = _opt_str(raw.get("screenshot")) or _opt_str(raw.get("screenshot_ref"))
    return VisualFinding(
        severity=_finding_severity(raw),
        category=category,
        description=str(raw.get("description") or "").strip(),
        route=str(raw.get("route") or "").strip(),
        confidence=raw.get("confidence"),
        viewport=_opt_str(raw.get("viewport")),
        screenshot=screenshot,
        evidence=raw.get("evidence"),
        confirmed=_finding_confirmed(raw),
        status=status,
    )


def normalize_reviewer_response(payload) -> tuple[VisualFinding, ...]:
    if payload is None:
        return ()
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("findings") or ()
    else:
        raise TypeError("reviewer response must be a dict or list")
    return tuple(normalize_finding(item) for item in items)


def evaluate_visual_gate(findings) -> str:
    for finding in findings or ():
        if not _finding_confirmed(finding):
            continue
        if _finding_severity(finding) in _BLOCKING_FINDINGS:
            return "FAIL"
    return "PASS"


def apply_reviewer_status(evidence: VisualEvidence, status: str) -> VisualEvidence:
    return replace(evidence, reviewer_status=status)


def _opt_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
