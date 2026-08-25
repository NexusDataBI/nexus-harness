from collections import defaultdict
from hashlib import sha256
from pathlib import Path

DECISIONS = frozenset(
    {
        "canonicalize",
        "upstream",
        "reference",
        "merge",
        "obsolete",
        "extract_then_remove_entrypoint",
    }
)

_CANONICAL = {
    "nexus-frontend": "skills/nexus-frontend/SKILL.md",
    "nexus-ship": "skills/nexus-ship/SKILL.md",
    "nexus-workflow": "skills/nexus-workflow/SKILL.md",
    "nexus-quality": "skills/nexus-quality/SKILL.md",
    "nexus-verify": "skills/nexus-verify/SKILL.md",
    "nexus-handoff": "skills/nexus-handoff/SKILL.md",
    "accessibility": "skills/accessibility/SKILL.md",
}

_UPSTREAM = {
    "impeccable": "upstream/impeccable/SKILL.md",
    "design-motion-principles": "upstream/design-motion-principles/SKILL.md",
    "vercel-react-best-practices": "upstream/vercel-react-best-practices/SKILL.md",
    "vercel-composition-patterns": "upstream/vercel-composition-patterns/SKILL.md",
    "test-driven-development": "upstream/superpowers/test-driven-development/SKILL.md",
    "systematic-debugging": "upstream/superpowers/systematic-debugging/SKILL.md",
    "subagent-driven-development": "upstream/superpowers/subagent-driven-development/SKILL.md",
    "brainstorming": "upstream/superpowers/brainstorming/SKILL.md",
    "writing-plans": "upstream/superpowers/writing-plans/SKILL.md",
    "using-git-worktrees": "upstream/superpowers/using-git-worktrees/SKILL.md",
    "verification-before-completion": "upstream/superpowers/verification-before-completion/SKILL.md",
    "requesting-code-review": "upstream/superpowers/requesting-code-review/SKILL.md",
    "receiving-code-review": "upstream/superpowers/receiving-code-review/SKILL.md",
    "finishing-a-development-branch": "upstream/superpowers/finishing-a-development-branch/SKILL.md",
    "dispatching-parallel-agents": "upstream/superpowers/dispatching-parallel-agents/SKILL.md",
    "executing-plans": "upstream/superpowers/executing-plans/SKILL.md",
    "using-superpowers": "upstream/superpowers/using-superpowers/SKILL.md",
    "writing-skills": "upstream/superpowers/writing-skills/SKILL.md",
    "ask-matt": "upstream/matt-pocock/ask-matt/SKILL.md",
    "batch-grill-me": "upstream/matt-pocock/batch-grill-me/SKILL.md",
    "grill-me": "upstream/matt-pocock/grill-me/SKILL.md",
    "grill-with-docs": "upstream/matt-pocock/grill-with-docs/SKILL.md",
    "grilling": "upstream/matt-pocock/grilling/SKILL.md",
    "implement": "upstream/matt-pocock/implement/SKILL.md",
    "prototype": "upstream/matt-pocock/prototype/SKILL.md",
    "research": "upstream/matt-pocock/research/SKILL.md",
    "setup-matt-pocock-skills": "upstream/matt-pocock/setup-matt-pocock-skills/SKILL.md",
    "teach": "upstream/matt-pocock/teach/SKILL.md",
    "to-questionnaire": "upstream/matt-pocock/to-questionnaire/SKILL.md",
    "to-spec": "upstream/matt-pocock/to-spec/SKILL.md",
    "to-tickets": "upstream/matt-pocock/to-tickets/SKILL.md",
    "triage": "upstream/matt-pocock/triage/SKILL.md",
    "wayfinder": "upstream/matt-pocock/wayfinder/SKILL.md",
    "codebase-design": "upstream/matt-pocock/codebase-design/SKILL.md",
    "domain-modeling": "upstream/matt-pocock/domain-modeling/SKILL.md",
    "writing-great-skills": "upstream/matt-pocock/writing-great-skills/SKILL.md",
    "resolving-merge-conflicts": "upstream/matt-pocock/resolving-merge-conflicts/SKILL.md",
    "improve-codebase-architecture": "upstream/matt-pocock/improve-codebase-architecture/SKILL.md",
}

_MERGE = {
    "tdd": "upstream/superpowers/test-driven-development/SKILL.md",
    "tdd-workflow": "skills/nexus-workflow/SKILL.md",
    "diagnosing-bugs": "upstream/superpowers/systematic-debugging/SKILL.md",
    "root-cause-tracing": "agents/root-cause-analyst.md",
    "verification-loop": "skills/nexus-verify/SKILL.md",
    "code-review": "skills/nexus-quality/SKILL.md",
    "source-command-review": "skills/nexus-quality/SKILL.md",
    "source-command-plan": "skills/nexus-workflow/SKILL.md",
    "source-command-branch": "skills/nexus-ship/SKILL.md",
    "source-command-commit": "skills/nexus-ship/SKILL.md",
    "source-command-push": "skills/nexus-ship/SKILL.md",
    "source-command-pr": "skills/nexus-ship/SKILL.md",
    "handoff": "skills/nexus-handoff/SKILL.md",
    "deploy": "skills/nexus-ship/SKILL.md",
    "frontend-redesign-orchestrator": "skills/nexus-frontend/SKILL.md",
    "design-taste-frontend": "skills/nexus-frontend/SKILL.md",
    "interface-review": "skills/nexus-frontend/SKILL.md",
    "explain-interface": "skills/nexus-frontend/SKILL.md",
    "better-accessibility": "skills/accessibility/SKILL.md",
    "fixing-accessibility": "skills/accessibility/SKILL.md",
}

_EXTRACT = {
    "ui-styling": "skills/nexus-frontend/SKILL.md",
    "ui-ux-pro-max": "skills/nexus-frontend/SKILL.md",
}

_REFERENCE = frozenset(
    {
        "visual-validation",
        "fixing-motion-performance",
        "feature-sliced-design",
        "ui-craft-dense-dashboard",
        "design-system",
        "brand",
        "extract-design-system",
        "variant",
        "banner-design",
        "baseline-ui",
        "better-ui",
        "better-interface",
        "better-layout",
        "better-typography",
        "better-colors",
        "better-writing",
        "web-design-guidelines",
        "design",
        "slides",
        "vercel-react-view-transitions",
        "graphify",
        "napkin",
        "token-optimizer",
        "token-coach",
        "skills-pack",
        "aws-skills",
        "changelog-generator",
        "content-research-writer",
        "owasp-security",
        "software-architecture",
        "trail-of-bits-security",
        "varlock",
        "vibesec",
        "webapp-testing",
        "context-mode",
        "ctx-cloud-setup",
        "ctx-cloud-status",
        "ctx-doctor",
        "ctx-stats",
        "ctx-upgrade",
    }
)

_OBSOLETE = frozenset(
    {
        "babysitting-prs",
        "calibracao-score-engajamento",
        "limpeza-diaria-segura-mac",
        "vuca-reengajamento-conversao",
        "vuca-shadow-guards-flip-review",
        "vuca-worktree-housekeeping",
    }
)

_DIVERGENT_RATIONALE = {
    "code-review": (
        "Claude and Codex copies differ; merge unique review heuristics into "
        "fresh Stage 7 reviewer agents, do not delete either source."
    ),
    "impeccable": (
        "Cursor copy adds license metadata and runtime path variants versus the "
        "shared agents/claude/codex hash; keep all sources and lock the retained "
        "upstream Impeccable tree."
    ),
    "implement": (
        "Claude copy is longer than Codex; retain both as Matt Pocock upstream "
        "primitives and extract unique guidance before dropping an entrypoint."
    ),
    "napkin": (
        "Claude copy is localized; agents-skills and Codex share a hash. Keep "
        "all sources as a focused reference, not a competing canonical skill."
    ),
    "root-cause-tracing": (
        "Claude copy is localized; agents-skills and Codex share a hash. Merge "
        "unique tracing heuristics into systematic-debugging plus "
        "root-cause-analyst; do not delete either source."
    ),
    "tdd-workflow": (
        "Claude and Codex copies diverge; merge unique Nexus workflow glue into "
        "nexus-workflow invoking Superpowers TDD, without deleting sources."
    ),
    "token-optimizer": (
        "Claude tree copy differs mainly in frontmatter quoting from the shared "
        "agents-skills/Codex hash. Keep all sources as a reference; not a "
        "canonical v4 skill."
    ),
    "ui-ux-pro-max": (
        "Three distinct hashes (Claude is substantially larger). Extract unique "
        "heuristics into nexus-frontend, then remove the broad entrypoint; do "
        "not delete any source in this task."
    ),
}


def discover_skill_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("SKILL.md")
        if p.is_file() and not any(part.startswith("._") for part in p.parts)
    )


def group_exact_duplicates(files: list[Path]) -> list[list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        groups[sha256(path.read_bytes()).hexdigest()].append(path)
    return [group for group in groups.values() if len(group) > 1]


def _classify(name: str) -> tuple[str, str | None]:
    if name in _CANONICAL:
        return "canonicalize", _CANONICAL[name]
    if name in _UPSTREAM:
        return "upstream", _UPSTREAM[name]
    if name in _MERGE:
        return "merge", _MERGE[name]
    if name in _EXTRACT:
        return "extract_then_remove_entrypoint", _EXTRACT[name]
    if name in _OBSOLETE:
        return "obsolete", None
    if name in _REFERENCE:
        return "reference", None
    return "reference", None


def _relationship(paths: list[Path]) -> str:
    if len(paths) == 1:
        return "unique"
    hashes = {sha256(path.read_bytes()).hexdigest() for path in paths}
    if len(hashes) == 1:
        return "exact_duplicate"
    return "divergent"


def _relative_sources(root: Path, paths: list[Path]) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in paths)


def build_skill_ledger(root: Path) -> list[dict]:
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in discover_skill_files(root):
        by_name[path.parent.name].append(path)

    ledger: list[dict] = []
    for name in sorted(by_name):
        paths = by_name[name]
        relationship = _relationship(paths)
        decision, target = _classify(name)
        if relationship == "exact_duplicate" and decision == "canonicalize":
            target = target or f"skills/{name}/SKILL.md"
        entry: dict = {
            "decision": decision,
            "name": name,
            "relationship": relationship,
            "sources": _relative_sources(root, paths),
        }
        if relationship == "divergent":
            entry["rationale"] = _DIVERGENT_RATIONALE.get(
                name,
                "Same-name sources have divergent hashes; keep all listed "
                "copies and extract unique heuristics before any removal.",
            )
        entry["target"] = target
        ledger.append(entry)
    return ledger
