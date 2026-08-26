"""Minimal quality toolchain detection and one-command quality execution."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from nexus_harness.config import load_toml
from nexus_harness.quality import (
    Metric,
    QualityReport,
    evaluate_report,
    load_quality_profile,
)
from nexus_harness.security import SecurityReport, normalize_trivy

_CORE_POLICIES = Path(__file__).resolve().parents[2] / "core" / "policies"
_TOOLING_POLICY = _CORE_POLICIES / "tooling.toml"

STATUS_EXISTING = "EXISTING"
STATUS_MIGRATION_RECOMMENDED = "MIGRATION_RECOMMENDED"
STATUS_BASELINE = "BASELINE"
STATUS_CONFLICT = "CONFLICT"

# Public role keys (Plan 4 contract). Policy TOML uses format_lint for lint.
BASELINE_TOOLS: dict[str, str] = {
    "lint": "biome",
    "unit_integration": "vitest",
    "e2e_visual": "playwright",
    "security": "trivy",
}

_DEV_DEP_PACKAGES = {
    "biome": "@biomejs/biome",
    "vitest": "vitest",
    "playwright": "@playwright/test",
}

_LINT_BASELINE = frozenset({"@biomejs/biome", "biome"})
_LINT_LEGACY = frozenset({"eslint", "prettier", "@eslint/js"})
_UNIT_BASELINE = frozenset({"vitest"})
_UNIT_LEGACY = frozenset({"jest", "@jest/globals", "mocha", "ava"})
_E2E_BASELINE = frozenset({"@playwright/test", "playwright"})
_E2E_LEGACY = frozenset({"cypress", "puppeteer", "protractor", "nightwatch"})
_SECURITY_OVERLAP = frozenset(
    {"snyk", "semgrep", "gitleaks", "codecov", "@snyk/protect"}
)

CommandRunner = Callable[..., tuple[int, str, str]]


@dataclass(frozen=True)
class ToolDetection:
    role: str
    baseline: str
    status: str
    found: tuple[str, ...] = ()
    action: str = ""


@dataclass(frozen=True)
class BootstrapPlan:
    package_manager: str | None
    detections: tuple[ToolDetection, ...]
    install_dev_deps: tuple[str, ...] = ()
    expect_host_tools: tuple[str, ...] = ("trivy",)


@dataclass
class QualityRunResult:
    quality: QualityReport
    security: SecurityReport | None = None
    steps: list[str] = field(default_factory=list)
    exit_code: int = 0


def load_tooling_policy(path: Path | None = None) -> dict:
    return load_toml(path or _TOOLING_POLICY)


def detect_package_manager(project_root: Path) -> str | None:
    root = Path(project_root)
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        return "bun"
    if (root / "package-lock.json").exists() or (root / "npm-shrinkwrap.json").exists():
        return "npm"
    if (root / "package.json").exists():
        return "npm"
    return None


def _read_package_json(project_root: Path) -> dict:
    path = Path(project_root) / "package.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _declared_packages(package: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for section in (
        "dependencies",
        "devDependencies",
        "optionalDependencies",
        "peerDependencies",
    ):
        block = package.get(section) or {}
        if isinstance(block, Mapping):
            names.update(str(key) for key in block)
    return names


def _config_signals(project_root: Path) -> set[str]:
    root = Path(project_root)
    found: set[str] = set()
    pairs = (
        ("biome", ("biome.json", "biome.jsonc")),
        (
            "eslint",
            (
                ".eslintrc",
                ".eslintrc.js",
                ".eslintrc.cjs",
                ".eslintrc.json",
                "eslint.config.js",
                "eslint.config.mjs",
                "eslint.config.cjs",
            ),
        ),
        (
            "vitest",
            (
                "vitest.config.ts",
                "vitest.config.js",
                "vitest.config.mts",
                "vitest.config.mjs",
            ),
        ),
        (
            "jest",
            ("jest.config.js", "jest.config.ts", "jest.config.cjs", "jest.config.mjs"),
        ),
        (
            "playwright",
            ("playwright.config.ts", "playwright.config.js", "playwright.config.mts"),
        ),
        ("cypress", ("cypress.config.ts", "cypress.config.js", "cypress.json")),
    )
    for label, names in pairs:
        if any((root / name).exists() for name in names):
            found.add(label)
    return found


def _classify(
    role: str, baseline: str, baseline_hits: set[str], legacy_hits: set[str]
) -> ToolDetection:
    if baseline_hits and legacy_hits:
        return ToolDetection(
            role=role,
            baseline=baseline,
            status=STATUS_CONFLICT,
            found=tuple(sorted(baseline_hits | legacy_hits)),
            action="resolve_overlap",
        )
    if baseline_hits:
        return ToolDetection(
            role=role,
            baseline=baseline,
            status=STATUS_EXISTING,
            found=tuple(sorted(baseline_hits)),
            action="keep",
        )
    if legacy_hits:
        return ToolDetection(
            role=role,
            baseline=baseline,
            status=STATUS_MIGRATION_RECOMMENDED,
            found=tuple(sorted(legacy_hits)),
            action="migrate",
        )
    return ToolDetection(
        role=role,
        baseline=baseline,
        status=STATUS_BASELINE,
        found=(),
        action="install" if role != "security" else "expect_ci_host",
    )


def detect_tools(
    project_root: Path, policy: Mapping[str, Any] | None = None
) -> BootstrapPlan:
    policy = policy or load_tooling_policy()
    package = _read_package_json(project_root)
    declared = _declared_packages(package)
    signals = _config_signals(project_root)
    pm = detect_package_manager(project_root)

    lint_baseline = (declared & _LINT_BASELINE) | ({"biome"} & signals)
    lint_legacy = (declared & _LINT_LEGACY) | ({"eslint"} & signals)
    unit_baseline = (declared & _UNIT_BASELINE) | ({"vitest"} & signals)
    unit_legacy = (declared & _UNIT_LEGACY) | ({"jest"} & signals)
    e2e_baseline = (declared & _E2E_BASELINE) | ({"playwright"} & signals)
    e2e_legacy = (declared & _E2E_LEGACY) | ({"cypress"} & signals)
    security_overlap = declared & _SECURITY_OVERLAP

    if security_overlap:
        security = ToolDetection(
            role="security",
            baseline=BASELINE_TOOLS["security"],
            status=STATUS_MIGRATION_RECOMMENDED,
            found=tuple(sorted(security_overlap)),
            action="migrate",
        )
    else:
        security = ToolDetection(
            role="security",
            baseline=BASELINE_TOOLS["security"],
            status=STATUS_BASELINE,
            found=(),
            action="expect_ci_host",
        )

    detections = (
        _classify("lint", BASELINE_TOOLS["lint"], lint_baseline, lint_legacy),
        _classify(
            "unit_integration",
            BASELINE_TOOLS["unit_integration"],
            unit_baseline,
            unit_legacy,
        ),
        _classify(
            "e2e_visual",
            BASELINE_TOOLS["e2e_visual"],
            e2e_baseline,
            e2e_legacy,
        ),
        security,
    )

    # Prefer existing / do not stack tools. Only install when every JS role is BASELINE.
    install: list[str] = []
    js_roles = [d for d in detections if d.role != "security"]
    if js_roles and all(d.status == STATUS_BASELINE for d in js_roles):
        for role, tool in (
            ("lint", "biome"),
            ("unit_integration", "vitest"),
            ("e2e_visual", "playwright"),
        ):
            install.append(_DEV_DEP_PACKAGES[tool])

    # Policy consistency: one primary tool; never auto-add not_baseline scanners.
    _ = policy.get("one_primary_tool_per_responsibility", True)

    return BootstrapPlan(
        package_manager=pm,
        detections=detections,
        install_dev_deps=tuple(install),
        expect_host_tools=("trivy",),
    )


def bootstrap_guidance(
    project_root: Path, policy: Mapping[str, Any] | None = None
) -> BootstrapPlan:
    return detect_tools(project_root, policy=policy)


def _default_runner(argv: Sequence[str], *, cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _pm_exec(package_manager: str | None) -> list[str]:
    if package_manager == "pnpm":
        return ["pnpm", "exec"]
    if package_manager == "yarn":
        return ["yarn", "exec"]
    if package_manager == "bun":
        return ["bun", "x"]
    return ["npx", "--yes"]


def _affected_checks(affected: Any) -> set[str]:
    if affected is None:
        return set()
    if isinstance(affected, Mapping):
        return {str(item).lower() for item in (affected.get("checks") or ())}
    checks = getattr(affected, "checks", None)
    if checks is not None:
        return {str(item).lower() for item in checks}
    return set()


def _affected_is_empty(affected: Any) -> bool:
    if affected is None:
        return False
    if isinstance(affected, Mapping):
        components = affected.get("components") or ()
        checks = affected.get("checks") or ()
        images = affected.get("images") or ()
        return not (components or checks or images)
    components = getattr(affected, "components", ()) or ()
    checks = getattr(affected, "checks", ()) or ()
    images = getattr(affected, "images", ()) or ()
    return not (components or checks or images)


def _wants_playwright(profile: Mapping[str, Any], affected: Any) -> bool:
    if profile.get("e2e_visual"):
        return True
    checks = _affected_checks(affected)
    markers = ("playwright", "e2e", "visual", "browser")
    return any(any(marker in check for marker in markers) for check in checks)


def _has_typecheck(package: Mapping[str, Any]) -> bool:
    scripts = package.get("scripts") or {}
    if not isinstance(scripts, Mapping):
        return False
    if "typecheck" in scripts:
        return True
    return any("tsc" in str(value) for value in scripts.values())


def _parse_json(stdout: str) -> dict:
    text = (stdout or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # Some runners wrap JSON; try last object-looking chunk.
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
        return {}
    return payload if isinstance(payload, dict) else {}


def _lint_warnings(payload: Mapping[str, Any], returncode: int) -> int:
    summary = (
        payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    )
    diagnostics = summary.get("diagnostics") if isinstance(summary, Mapping) else None
    if isinstance(diagnostics, Mapping):
        warn = diagnostics.get("warn")
        error = diagnostics.get("error")
        total = 0
        if isinstance(warn, int):
            total += warn
        if isinstance(error, int):
            total += error
        return total
    if "diagnostics" in payload and isinstance(payload["diagnostics"], list):
        return len(payload["diagnostics"])
    return 0 if returncode == 0 else 1


def _vitest_metrics(
    payload: Mapping[str, Any], returncode: int
) -> tuple[int, float | None]:
    failing = payload.get("numFailedTests")
    if not isinstance(failing, int):
        failing = 0 if returncode == 0 else 1
    coverage = None
    cov = payload.get("coverage")
    if isinstance(cov, Mapping):
        lines = cov.get("lines")
        if isinstance(lines, Mapping) and isinstance(lines.get("pct"), (int, float)):
            coverage = float(lines["pct"])
        elif isinstance(cov.get("pct"), (int, float)):
            coverage = float(cov["pct"])
        elif isinstance(cov.get("total"), (int, float)):
            coverage = float(cov["total"])
    return failing, coverage


def run_quality(
    profile: str = "standard",
    *,
    affected: Any = None,
    project_root: Path | str | None = None,
    runner: CommandRunner | None = None,
    baselines: Mapping[str, float | int] | None = None,
    write_reports_to: Path | None = None,
) -> QualityRunResult:
    """Orchestrate Biome / typecheck / Vitest / Playwright / Trivy for a profile.

    Maps to CLI intent ``nexus quality run --profile <name>``. Inject ``runner``
    in tests; production default shells out locally (no network assumed).
    """
    root = Path(project_root or Path.cwd())
    run = runner or _default_runner
    baselines = dict(baselines or {})
    profile_cfg = load_quality_profile(profile)

    if _affected_is_empty(affected):
        quality = evaluate_report([], profile=profile)
        return QualityRunResult(quality=quality, security=None, steps=[], exit_code=0)

    package = _read_package_json(root)
    pm = detect_package_manager(root)
    exec_prefix = _pm_exec(pm)
    steps: list[str] = []
    metrics: list[Metric] = []
    security_report: SecurityReport | None = None
    failed = False

    if profile_cfg.get("format_lint"):
        code, stdout, _stderr = run(
            [*exec_prefix, "biome", "check", "--reporter=json", "."], cwd=root
        )
        steps.append("biome")
        payload = _parse_json(stdout)
        warnings = _lint_warnings(payload, code)
        metrics.append(
            Metric(
                "lint_warnings",
                current=warnings,
                baseline=baselines.get("lint_warnings"),
                mode="ratchet",
                direction="lower",
                required=True,
            )
        )
        if code != 0:
            failed = True

    if profile_cfg.get("typecheck_when_configured") and _has_typecheck(package):
        scripts = package.get("scripts") or {}
        if isinstance(scripts, Mapping) and "typecheck" in scripts:
            argv = (
                [pm or "npm", "run", "typecheck"] if pm else ["npm", "run", "typecheck"]
            )
        else:
            argv = [*exec_prefix, "tsc", "--noEmit"]
        code, _stdout, _stderr = run(argv, cwd=root)
        steps.append("typecheck")
        metrics.append(
            Metric(
                "build_type_errors",
                current=0 if code == 0 else 1,
                threshold=0,
                mode="absolute",
                direction="lower",
                required=True,
            )
        )
        if code != 0:
            failed = True

    if profile_cfg.get("unit_tests"):
        vitest_argv = [*exec_prefix, "vitest", "run", "--reporter=json"]
        if profile_cfg.get("coverage"):
            vitest_argv.append("--coverage")
        code, stdout, _stderr = run(vitest_argv, cwd=root)
        steps.append("vitest")
        payload = _parse_json(stdout)
        failing, coverage = _vitest_metrics(payload, code)
        metrics.append(
            Metric(
                "failing_tests",
                current=failing,
                threshold=0,
                mode="absolute",
                direction="lower",
                required=True,
            )
        )
        if profile_cfg.get("coverage"):
            cov_value = 0.0 if coverage is None else coverage
            metrics.append(
                Metric(
                    "coverage",
                    current=cov_value,
                    baseline=baselines.get("coverage"),
                    mode="ratchet",
                    direction="higher",
                    required=True,
                )
            )
        if code != 0 or failing:
            failed = True

    if _wants_playwright(profile_cfg, affected):
        code, _stdout, _stderr = run(
            [*exec_prefix, "playwright", "test", "--reporter=json"],
            cwd=root,
        )
        steps.append("playwright")
        metrics.append(
            Metric(
                "failing_e2e",
                current=0 if code == 0 else 1,
                threshold=0,
                mode="absolute",
                direction="lower",
                required=True,
            )
        )
        if code != 0:
            failed = True

    if profile_cfg.get("security_scan"):
        # Single primary scanner: Trivy (no Semgrep/Gitleaks/Snyk/Codecov).
        code, stdout, _stderr = run(
            [
                "trivy",
                "fs",
                "--scanners",
                "vuln,secret,misconfig",
                "--format",
                "json",
                ".",
            ],
            cwd=root,
        )
        steps.append("trivy")
        payload = _parse_json(stdout) or {"Results": []}
        security_report = normalize_trivy(payload)
        critical = int(security_report.counts.get("critical", 0))
        metrics.append(
            Metric(
                "critical_security",
                current=critical,
                threshold=0,
                mode="absolute",
                direction="lower",
                required=True,
            )
        )
        if security_report.gate == "FAIL" or code not in (0, 1):
            # Trivy uses exit 1 when vulnerabilities are found depending on flags;
            # gate follows normalize_trivy policy, not raw exit alone.
            if security_report.gate == "FAIL":
                failed = True
            elif code not in (0, 1):
                failed = True

    quality = evaluate_report(metrics, profile=profile)
    if failed and quality.gate == "PASS":
        # Preserve required-metric semantics; also fail on tool process errors.
        quality = QualityReport(
            gate="FAIL",
            metrics=quality.metrics,
            profile=quality.profile,
            diff_hash=quality.diff_hash,
            score=quality.score,
        )

    if write_reports_to is not None:
        out = Path(write_reports_to)
        out.mkdir(parents=True, exist_ok=True)
        (out / "quality-report.json").write_text(
            json.dumps(quality.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        if security_report is not None:
            (out / "security-report.json").write_text(
                json.dumps(security_report.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )

    exit_code = (
        0
        if quality.gate == "PASS"
        and (security_report is None or security_report.gate == "PASS")
        else 1
    )
    return QualityRunResult(
        quality=quality,
        security=security_report,
        steps=steps,
        exit_code=exit_code,
    )
