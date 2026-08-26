"""PR body contract and merge readiness.

Merge readiness is the existing completion Done Gate. READY_TO_SHIP is
surfaced as READY_TO_MERGE. Draft PRs may exist before that gate is green.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from nexus_harness.completion import evaluate_completion

PR_SECTIONS = (
    "Summary",
    "Issue",
    "Scope",
    "Acceptance",
    "Verification",
    "Quality",
    "Security",
    "Deployment impact",
    "Known limitations",
)
FRONTEND_SECTION = "Frontend evidence"


@dataclass
class MergeReadiness:
    status: str
    reasons: list[str] = field(default_factory=list)
    draft_allowed: bool = True


def render_pr_body(
    issue,
    partial: bool = False,
    summary: str = "",
    evidence: Sequence[str] | None = None,
    *,
    scope: str = "",
    acceptance: str = "",
    verification: str = "",
    quality: str = "",
    security: str = "",
    frontend: bool = False,
    frontend_evidence: str = "",
    deployment_impact: str = "",
    known_limitations: str = "",
) -> str:
    reference = f"Refs #{issue}" if partial else f"Closes #{issue}"
    values = {
        "Summary": summary,
        "Issue": reference,
        "Scope": scope,
        "Acceptance": acceptance,
        "Verification": _verification(verification, evidence),
        "Quality": quality,
        "Security": security,
        "Deployment impact": deployment_impact,
        "Known limitations": known_limitations,
    }

    blocks: list[str] = []
    for heading in PR_SECTIONS:
        blocks.append(f"## {heading}")
        blocks.append("")
        blocks.append(str(values.get(heading, "")).strip())
        blocks.append("")
        if heading == "Security" and (frontend or frontend_evidence.strip()):
            blocks.append(f"## {FRONTEND_SECTION}")
            blocks.append("")
            blocks.append(frontend_evidence.strip())
            blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def ready_to_merge(state) -> MergeReadiness:
    completion = evaluate_completion(state)
    if completion.status == "READY_TO_SHIP":
        return MergeReadiness(status="READY_TO_MERGE", reasons=[])
    return MergeReadiness(status="FAIL", reasons=list(completion.reasons))


def _verification(verification: str, evidence: Sequence[str] | None) -> str:
    parts = [verification.strip()] if verification.strip() else []
    parts.extend(str(item).strip() for item in (evidence or ()) if str(item).strip())
    return "\n".join(parts)
