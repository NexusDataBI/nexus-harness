"""Live runtime integration: owned-tree vs shared-config mapping.

Canonical templates stay portable. Live apply rewrites hook commands to the
installed engine root. Never atomic_install a shared runtime home.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib

from nexus_harness.install import atomic_install, rollback_install, tree_digests
from nexus_harness.release import RELEASE_VERSION
from nexus_harness.safe import reject_symlinks, reject_tree_symlinks

MD_BEGIN = "<!-- NEXUS_HARNESS_BEGIN -->"
MD_END = "<!-- NEXUS_HARNESS_END -->"
TOML_BEGIN = "# NEXUS_HARNESS_BEGIN"
TOML_END = "# NEXUS_HARNESS_END"

_SANDBOX_STRICTNESS = {
    "read-only": 3,
    "workspace-write": 2,
    "danger-full-access": 1,
}
_APPROVAL_STRICTNESS = {
    "untrusted": 4,
    "on-request": 3,
    "on-failure": 2,
    "never": 1,
}

_NEXUS_HOOK_MARKER = "claude_event.py"


class LiveInstallError(ValueError):
    """Fail-closed live install (malformed config, conflict, or unsafe apply)."""


@dataclass(frozen=True)
class PlannedMutation:
    runtime: str
    artifact: str
    source: str | None
    destination: str
    ownership: str
    operation: str
    scope: str
    classification: str
    backup_path: str | None
    risk: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LivePlan:
    runtime: str
    home: str
    engine_root: str
    dist: str
    backup_root: str
    blocked: bool
    mutations: tuple[PlannedMutation, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mutations"] = [asdict(item) for item in self.mutations]
        return payload


@dataclass(frozen=True)
class LiveApplyResult:
    ok: bool
    runtime: str
    backup_root: str
    engine_backup: str | None
    files: tuple[str, ...]
    plan: LivePlan | None = None


def default_engine_root(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home)
    return (base / ".nexus-harness" / "install" / RELEASE_VERSION).resolve()


def default_runtime_home(runtime: str, environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    mapping = {
        "codex": ("CODEX_HOME", ".codex"),
        "cursor": ("CURSOR_HOME", ".cursor"),
        "claude": ("CLAUDE_HOME", ".claude"),
    }
    if runtime not in mapping:
        raise LiveInstallError(f"unknown runtime: {runtime}")
    key, relative = mapping[runtime]
    raw = (env.get(key) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / relative).resolve()


def inspect_live_runtime(runtime: str, home: Path) -> dict[str, Any]:
    home = Path(home)
    report: dict[str, Any] = {
        "runtime": runtime,
        "home": str(home.resolve()) if home.exists() else str(home),
        "exists": home.exists(),
        "artifacts": {},
    }
    if runtime == "codex":
        report["artifacts"] = {
            "config.toml": {
                "path": str(home / "config.toml"),
                "exists": (home / "config.toml").is_file(),
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "GLOBAL_SUPPORTED",
            },
            "AGENTS.md": {
                "path": str(home / "AGENTS.md"),
                "exists": (home / "AGENTS.md").is_file(),
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "GLOBAL_SUPPORTED",
            },
        }
    elif runtime == "claude":
        report["artifacts"] = {
            "CLAUDE.md": {
                "path": str(home / "CLAUDE.md"),
                "exists": (home / "CLAUDE.md").is_file(),
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "GLOBAL_SUPPORTED",
            },
            "settings.json": {
                "path": str(home / "settings.json"),
                "exists": (home / "settings.json").is_file(),
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "GLOBAL_SUPPORTED",
            },
        }
    elif runtime == "cursor":
        report["artifacts"] = {
            "USER_RULES.md": {
                "path": str(home / "USER_RULES.md"),
                "exists": False,
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "NOT_APPLICABLE",
            },
            "cursor/sandbox.json": {
                "path": str(home / "sandbox.json"),
                "exists": False,
                "ownership": "NEXUS_OWNED_TREE",
                "scope": "NEXUS_INTERNAL_ONLY",
            },
            ".cursor/rules/nexus-workflow.mdc": {
                "path": ".cursor/rules/nexus-workflow.mdc",
                "exists": False,
                "ownership": "SHARED_RUNTIME_CONFIG",
                "scope": "PROJECT_SUPPORTED",
            },
        }
    else:
        raise LiveInstallError(f"unknown runtime: {runtime}")
    return report


def plan_live_install(
    runtime: str,
    *,
    home: Path,
    dist: Path,
    engine_root: Path,
    project_root: Path | None = None,
    backup_root: Path | None = None,
) -> LivePlan:
    runtime = runtime.strip().lower()
    if runtime not in {"codex", "cursor", "claude"}:
        raise LiveInstallError(f"unknown runtime: {runtime}")
    home = Path(home)
    dist = Path(dist)
    engine_root = Path(engine_root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = (
        Path(backup_root)
        if backup_root
        else home.parent / f"nexus-live-{runtime}-{stamp}"
    )
    mutations: list[PlannedMutation] = [
        _plan_engine(runtime, dist, engine_root, backup),
    ]
    if runtime == "codex":
        mutations.extend(_plan_codex(home, dist, backup))
    elif runtime == "claude":
        mutations.extend(_plan_claude(home, dist, engine_root, backup))
    else:
        mutations.extend(_plan_cursor(home, dist, project_root, backup))
    blocked = any(item.operation == "CONFLICT" for item in mutations)
    return LivePlan(
        runtime=runtime,
        home=str(home),
        engine_root=str(engine_root),
        dist=str(dist),
        backup_root=str(backup),
        blocked=blocked,
        mutations=tuple(mutations),
    )


def apply_live_install(plan: LivePlan) -> LiveApplyResult:
    if plan.blocked:
        raise LiveInstallError("live install blocked by CONFLICT; refuse apply")
    backup = Path(plan.backup_root)
    backup.mkdir(parents=True, exist_ok=True)
    files_dir = backup / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"runtime": plan.runtime, "files": []}
    engine_backup = None
    written: list[str] = []
    try:
        for item in plan.mutations:
            if item.operation in {"PRESERVE", "NOOP", "SKIP"}:
                continue
            dest = Path(item.destination)
            record = {
                "artifact": item.artifact,
                "destination": str(dest),
                "existed": dest.is_file(),
                "mode": oct(dest.stat().st_mode) if dest.exists() else None,
                "sha256": _sha256(dest) if dest.is_file() else None,
                "ownership": item.ownership,
                "operation": item.operation,
            }
            if item.ownership == "NEXUS_OWNED_TREE" and item.artifact == "engine":
                source = Path(plan.dist)
                stage = _engine_stage(
                    source, Path(plan.engine_root).parent / ".engine-stage"
                )
                engine_target = Path(plan.engine_root)
                if engine_target.exists():
                    engine_backup = str(atomic_install(stage, engine_target))
                else:
                    engine_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(stage, engine_target)
                    engine_backup = None
                shutil.rmtree(stage, ignore_errors=True)
                record["engine_backup"] = engine_backup
                manifest["files"].append(record)
                written.append(str(engine_target))
                continue
            if dest.is_file():
                rel = dest.name if dest.parent == Path(plan.home) else dest.name
                copy_to = files_dir / rel
                if copy_to.exists():
                    copy_to = files_dir / f"{dest.parent.name}-{dest.name}"
                shutil.copy2(dest, copy_to)
                record["backup_copy"] = str(copy_to)
            elif dest.exists() and dest.is_dir():
                raise LiveInstallError(f"refusing to replace directory: {dest}")
            _apply_shared(item, plan)
            manifest["files"].append(record)
            written.append(str(dest))
        manifest["engine_backup"] = engine_backup
        (backup / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return LiveApplyResult(
            ok=True,
            runtime=plan.runtime,
            backup_root=str(backup),
            engine_backup=engine_backup,
            files=tuple(written),
            plan=plan,
        )
    except Exception:
        if (backup / "MANIFEST.json").is_file() or engine_backup:
            try:
                rollback_live_install(
                    LiveApplyResult(
                        ok=False,
                        runtime=plan.runtime,
                        backup_root=str(backup),
                        engine_backup=engine_backup,
                        files=tuple(written),
                        plan=plan,
                    )
                )
            except Exception:
                pass
        raise


def rollback_live_install(result: LiveApplyResult) -> None:
    backup = Path(result.backup_root)
    manifest_path = backup / "MANIFEST.json"
    if not manifest_path.is_file():
        raise LiveInstallError(f"missing live backup manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for record in reversed(list(manifest.get("files") or ())):
        dest = Path(record["destination"])
        if (
            record.get("ownership") == "NEXUS_OWNED_TREE"
            and record.get("artifact") == "engine"
        ):
            engine_backup = record.get("engine_backup") or manifest.get("engine_backup")
            if engine_backup:
                rollback_install(Path(engine_backup), dest)
            elif dest.exists() and not record.get("existed"):
                shutil.rmtree(dest)
            continue
        copy_to = record.get("backup_copy")
        if record.get("existed") and copy_to:
            shutil.copy2(copy_to, dest)
            mode = record.get("mode")
            if mode:
                os.chmod(dest, int(mode, 8) & 0o777)
        elif dest.is_file() and not record.get("existed"):
            dest.unlink()


def _plan_engine(
    runtime: str, dist: Path, engine_root: Path, backup: Path
) -> PlannedMutation:
    return PlannedMutation(
        runtime=runtime,
        artifact="engine",
        source=str(dist),
        destination=str(engine_root),
        ownership="NEXUS_OWNED_TREE",
        operation="CREATE" if not engine_root.exists() else "UPDATE_OWNED",
        scope="NEXUS_INTERNAL_ONLY",
        classification="MIGRATE_TO_NEXUS",
        backup_path=str(backup / "engine"),
        risk="replaces Nexus-owned install tree only",
        detail={"version": RELEASE_VERSION},
    )


def _plan_codex(home: Path, dist: Path, backup: Path) -> list[PlannedMutation]:
    mutations = []
    config = home / "config.toml"
    generated = dist / "codex" / "config.toml"
    desired = _generated_codex_defaults(generated)
    existing_text = config.read_text(encoding="utf-8") if config.is_file() else ""
    try:
        parsed = tomllib.loads(existing_text) if existing_text.strip() else {}
    except tomllib.TOMLDecodeError as exc:
        mutations.append(
            _mutation(
                "codex",
                "config.toml",
                str(generated),
                config,
                "CONFLICT",
                "SHARED_RUNTIME_CONFIG",
                "GLOBAL_SUPPORTED",
                "CONFLICT",
                backup,
                f"malformed TOML: {exc}",
            )
        )
        parsed = {}
    else:
        op, detail = _codex_config_operation(parsed, desired)
        mutations.append(
            _mutation(
                "codex",
                "config.toml",
                str(generated),
                config,
                op,
                "SHARED_RUNTIME_CONFIG",
                "GLOBAL_SUPPORTED",
                "MIGRATE_TO_NEXUS"
                if op in {"CREATE", "UPDATE_OWNED", "MERGE"}
                else "KEEP_EXTERNAL",
                backup,
                "merge Nexus-owned keys; never replace the file",
                detail,
            )
        )
    agents = home / "AGENTS.md"
    body = (dist / "AGENTS.md").read_text(encoding="utf-8")
    op, detail = _markdown_operation(agents, body)
    mutations.append(
        _mutation(
            "codex",
            "AGENTS.md",
            str(dist / "AGENTS.md"),
            agents,
            op,
            "SHARED_RUNTIME_CONFIG",
            "GLOBAL_SUPPORTED",
            "KEEP_EXTERNAL" if op != "CONFLICT" else "CONFLICT",
            backup,
            "owned markdown block; preserve outside bytes",
            detail,
        )
    )
    return mutations


def _plan_claude(
    home: Path, dist: Path, engine_root: Path, backup: Path
) -> list[PlannedMutation]:
    mutations = []
    settings = home / "settings.json"
    generated = dist / "claude" / "settings.json"
    op, detail = _claude_settings_operation(settings, generated, engine_root)
    mutations.append(
        _mutation(
            "claude",
            "settings.json",
            str(generated),
            settings,
            op,
            "SHARED_RUNTIME_CONFIG",
            "GLOBAL_SUPPORTED",
            "CONFLICT" if op == "CONFLICT" else "MIGRATE_TO_NEXUS",
            backup,
            "merge Nexus-owned hooks only; preserve unrelated keys",
            detail,
        )
    )
    md = home / "CLAUDE.md"
    body = (dist / "claude" / "CLAUDE.md").read_text(encoding="utf-8")
    md_op, md_detail = _markdown_operation(md, body)
    mutations.append(
        _mutation(
            "claude",
            "CLAUDE.md",
            str(dist / "claude" / "CLAUDE.md"),
            md,
            md_op,
            "SHARED_RUNTIME_CONFIG",
            "GLOBAL_SUPPORTED",
            "KEEP_EXTERNAL" if md_op != "CONFLICT" else "CONFLICT",
            backup,
            "owned markdown block; preserve outside bytes",
            md_detail,
        )
    )
    return mutations


def _plan_cursor(
    home: Path, dist: Path, project_root: Path | None, backup: Path
) -> list[PlannedMutation]:
    mutations = [
        _mutation(
            "cursor",
            "USER_RULES.md",
            str(dist / "USER_RULES.md"),
            home / "USER_RULES.md",
            "SKIP",
            "SHARED_RUNTIME_CONFIG",
            "NOT_APPLICABLE",
            "NOT_APPLICABLE",
            backup,
            "Cursor 3.x does not consume ~/.cursor/USER_RULES.md",
        ),
        _mutation(
            "cursor",
            "cursor/sandbox.json",
            str(dist / "cursor" / "sandbox.json"),
            home / "sandbox.json",
            "SKIP",
            "NEXUS_OWNED_TREE",
            "NEXUS_INTERNAL_ONLY",
            "NOT_APPLICABLE",
            backup,
            "sandbox.json is not a Cursor global config; cli-config.json stays KEEP_EXTERNAL",
        ),
    ]
    dest = (
        (Path(project_root) / ".cursor" / "rules" / "nexus-workflow.mdc")
        if project_root is not None
        else Path(".cursor/rules/nexus-workflow.mdc")
    )
    source = dist / ".cursor" / "rules" / "nexus-workflow.mdc"
    if project_root is None:
        mutations.append(
            _mutation(
                "cursor",
                ".cursor/rules/nexus-workflow.mdc",
                str(source),
                dest,
                "SKIP",
                "SHARED_RUNTIME_CONFIG",
                "PROJECT_SUPPORTED",
                "MIGRATE_TO_NEXUS",
                backup,
                "project-scope only; pass --project to apply",
            )
        )
        return mutations
    body = source.read_text(encoding="utf-8")
    op, detail = _markdown_operation(dest, body)
    if op == "CREATE" or not dest.exists():
        op = "CREATE"
    elif op == "NOOP":
        op = "NOOP"
    else:
        op = "UPDATE_OWNED"
    mutations.append(
        _mutation(
            "cursor",
            ".cursor/rules/nexus-workflow.mdc",
            str(source),
            dest,
            op,
            "SHARED_RUNTIME_CONFIG",
            "PROJECT_SUPPORTED",
            "MIGRATE_TO_NEXUS",
            backup,
            "project rules file; do not write ~/.cursor",
            detail,
        )
    )
    return mutations


def _apply_shared(item: PlannedMutation, plan: LivePlan) -> None:
    dest = Path(item.destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if item.artifact == "config.toml":
        desired = _generated_codex_defaults(Path(item.source or ""))
        text = dest.read_text(encoding="utf-8") if dest.is_file() else ""
        dest.write_text(_merge_codex_toml(text, desired), encoding="utf-8")
        return
    if item.artifact in {"AGENTS.md", "CLAUDE.md", ".cursor/rules/nexus-workflow.mdc"}:
        body = Path(item.source or "").read_text(encoding="utf-8")
        current = dest.read_text(encoding="utf-8") if dest.is_file() else ""
        dest.write_text(_upsert_markdown_block(current, body), encoding="utf-8")
        return
    if item.artifact == "settings.json":
        generated = json.loads(Path(item.source or "").read_text(encoding="utf-8"))
        current_text = dest.read_text(encoding="utf-8") if dest.is_file() else "{}\n"
        current = json.loads(current_text)
        merged = _merge_claude_settings(current, generated, Path(plan.engine_root))
        mode = stat.S_IMODE(dest.stat().st_mode) if dest.is_file() else 0o600
        _atomic_write_text(
            dest, json.dumps(merged, indent=2, ensure_ascii=False) + "\n", mode
        )
        return
    raise LiveInstallError(f"unsupported shared artifact: {item.artifact}")


def _codex_config_operation(
    parsed: dict[str, Any], desired: dict[str, str]
) -> tuple[str, dict[str, Any]]:
    detail: dict[str, Any] = {"desired": desired, "decisions": {}}
    changes = False
    for key, want in desired.items():
        have = parsed.get(key)
        if have is None:
            detail["decisions"][key] = "CREATE"
            changes = True
            continue
        have_s = str(have)
        if have_s == want:
            detail["decisions"][key] = "NOOP"
            continue
        if _is_stricter(key, have_s, want):
            detail["decisions"][key] = "PRESERVE"
            continue
        detail["decisions"][key] = "UPDATE_OWNED"
        changes = True
    if not changes:
        return "NOOP", detail
    if all(v == "CREATE" for v in detail["decisions"].values()):
        return "CREATE" if not parsed else "MERGE", detail
    return "MERGE", detail


def _is_stricter(key: str, have: str, want: str) -> bool:
    table = _SANDBOX_STRICTNESS if key == "sandbox_mode" else _APPROVAL_STRICTNESS
    if have not in table or want not in table:
        return False
    return table[have] > table[want]


def _generated_codex_defaults(path: Path) -> dict[str, str]:
    payload = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        "sandbox_mode": str(payload.get("sandbox_mode") or "workspace-write"),
        "approval_policy": str(payload.get("approval_policy") or "on-request"),
    }


def _toml_owned_block(values: dict[str, str]) -> str:
    lines = [TOML_BEGIN, "# GENERATED BY NEXUS HARNESS — DO NOT EDIT"]
    for key in ("sandbox_mode", "approval_policy"):
        if key in values:
            lines.append(f'{key} = "{values[key]}"')
    lines.append(TOML_END)
    return "\n".join(lines) + "\n"


def _strip_toml_block(text: str) -> str:
    pattern = re.compile(
        re.escape(TOML_BEGIN) + r".*?" + re.escape(TOML_END) + r"\n?",
        re.DOTALL,
    )
    return pattern.sub("", text)


def _merge_codex_toml(existing: str, desired: dict[str, str]) -> str:
    begin_count = existing.count(TOML_BEGIN)
    end_count = existing.count(TOML_END)
    if begin_count > 1 or end_count > 1 or begin_count != end_count:
        raise LiveInstallError("duplicate or malformed Nexus TOML block")
    body = _strip_toml_block(existing)
    parsed = tomllib.loads(body) if body.strip() else {}
    block_values: dict[str, str] = {}
    for key, want in desired.items():
        have = parsed.get(key)
        if have is None:
            block_values[key] = want
            continue
        if _is_stricter(key, str(have), want) or str(have) == want:
            continue
        body, count = re.subn(
            rf'(?m)^{re.escape(key)}\s*=\s*".*?"',
            f'{key} = "{want}"',
            body,
            count=1,
        )
        if count != 1:
            raise LiveInstallError(f"cannot update {key} in config.toml")
    if not block_values:
        return body if body.endswith("\n") else body + "\n"
    prefix = body.lstrip("\n")
    return _toml_owned_block(block_values) + ("\n" if prefix else "") + prefix


def _markdown_operation(path: Path, body: str) -> tuple[str, dict[str, Any]]:
    if not path.is_file():
        return "CREATE", {"reason": "absent"}
    text = path.read_text(encoding="utf-8")
    begins = text.count(MD_BEGIN)
    ends = text.count(MD_END)
    if begins > 1 or ends > 1 or begins != ends:
        return "CONFLICT", {"reason": "duplicate or malformed Nexus block"}
    if begins == 0:
        return "UPDATE_OWNED", {"reason": "append owned block"}
    current = _owned_markdown_block(body)
    if MD_BEGIN in text and current.strip() in text:
        # Compare inner body
        match = re.search(
            re.escape(MD_BEGIN) + r"(.*?)" + re.escape(MD_END), text, re.DOTALL
        )
        if match and match.group(0).strip() == current.strip():
            return "NOOP", {"reason": "owned block matches"}
        return "UPDATE_OWNED", {"reason": "refresh owned block"}
    return "UPDATE_OWNED", {"reason": "refresh owned block"}


def _owned_markdown_block(body: str) -> str:
    inner = body.strip() + "\n"
    return f"{MD_BEGIN}\n{inner}{MD_END}\n"


def _upsert_markdown_block(existing: str, body: str) -> str:
    begins = existing.count(MD_BEGIN)
    ends = existing.count(MD_END)
    if begins > 1 or ends > 1 or begins != ends:
        raise LiveInstallError("duplicate or malformed Nexus markdown block")
    block = _owned_markdown_block(body)
    if begins == 1:
        pattern = re.compile(
            re.escape(MD_BEGIN) + r".*?" + re.escape(MD_END),
            re.DOTALL,
        )
        return pattern.sub(block.rstrip("\n"), existing)
    if not existing:
        return block
    if not existing.endswith("\n"):
        existing += "\n"
    return existing + "\n" + block


def _claude_settings_operation(
    settings_path: Path, generated_path: Path, engine_root: Path
) -> tuple[str, dict[str, Any]]:
    if settings_path.is_file():
        try:
            current = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return "CONFLICT", {"reason": f"malformed JSON: {exc}"}
        if not isinstance(current, dict):
            return "CONFLICT", {"reason": "settings.json root must be an object"}
    else:
        current = {}
    try:
        generated = json.loads(generated_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return "CONFLICT", {"reason": f"generated settings malformed: {exc}"}
    try:
        _merge_claude_settings(current, generated, engine_root)
    except LiveInstallError as exc:
        return "CONFLICT", {"reason": str(exc)}
    return "MERGE", {"events": sorted((generated.get("hooks") or {}).keys())}


def _merge_claude_settings(
    current: dict[str, Any], generated: dict[str, Any], engine_root: Path
) -> dict[str, Any]:
    merged = json.loads(json.dumps(current))  # deep copy via JSON
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise LiveInstallError("hooks must be an object")
    wanted = generated.get("hooks") or {}
    if not isinstance(wanted, dict):
        raise LiveInstallError("generated hooks must be an object")
    for event, matchers in wanted.items():
        command = _hook_command(engine_root, event, matchers)
        existing = hooks.get(event) or []
        if not isinstance(existing, list):
            raise LiveInstallError(f"hooks.{event} must be a list")
        nexus_indexes = [
            idx for idx, matcher in enumerate(existing) if _matcher_is_nexus(matcher)
        ]
        if len(nexus_indexes) > 1:
            raise LiveInstallError(f"duplicate Nexus hooks for {event}")
        replacement = {
            "hooks": [{"type": "command", "command": command}],
        }
        if not nexus_indexes:
            existing = list(existing)
            existing.append(replacement)
            hooks[event] = existing
            continue
        idx = nexus_indexes[0]
        current_cmd = _matcher_command(existing[idx])
        if current_cmd == command:
            continue
        existing = list(existing)
        existing[idx] = replacement
        hooks[event] = existing
    return merged


def _hook_command(engine_root: Path, event: str, _matchers: Any) -> str:
    hook = (Path(engine_root) / "hooks" / "claude_event.py").resolve()
    extra = " --completion-gate" if event == "TaskCompleted" else ""
    return f"python3 {hook} --event {event}{extra}"


def _matcher_is_nexus(matcher: Any) -> bool:
    command = _matcher_command(matcher)
    return _NEXUS_HOOK_MARKER in command


def _matcher_command(matcher: Any) -> str:
    if not isinstance(matcher, dict):
        return ""
    hooks = matcher.get("hooks") or []
    if not isinstance(hooks, list):
        return ""
    for hook in hooks:
        if isinstance(hook, dict):
            return str(hook.get("command") or "")
    return ""


def _engine_stage(dist: Path, stage: Path) -> Path:
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "hooks").mkdir(parents=True)
    (stage / "src").mkdir(parents=True)
    (stage / "core").mkdir(parents=True)
    src = dist / "src" / "nexus_harness"
    core = dist / "core"
    if src.is_dir():
        shutil.copytree(src, stage / "src" / "nexus_harness")
    if core.is_dir():
        shutil.copytree(core, stage / "core", dirs_exist_ok=True)
    for name in ("nexus_event.py", "claude_event.py"):
        hook = dist / "hooks" / name
        if hook.is_file():
            shutil.copy2(hook, stage / "hooks" / name)
    return stage


def _atomic_write_text(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.parent / f".{path.name}.staging-{os.getpid()}-{time.time_ns()}"
    staging.write_text(text, encoding="utf-8")
    os.chmod(staging, mode)
    with staging.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(staging, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutation(
    runtime: str,
    artifact: str,
    source: str | None,
    destination: Path,
    operation: str,
    ownership: str,
    scope: str,
    classification: str,
    backup: Path,
    risk: str,
    detail: dict[str, Any] | None = None,
) -> PlannedMutation:
    return PlannedMutation(
        runtime=runtime,
        artifact=artifact,
        source=source,
        destination=str(destination),
        ownership=ownership,
        operation=operation,
        scope=scope,
        classification=classification,
        backup_path=str(backup / "files" / destination.name),
        risk=risk,
        detail=detail or {},
    )


# tree_digests imported for callers; keep reject helpers available for future guards.
_ = (reject_symlinks, reject_tree_symlinks, tree_digests)
