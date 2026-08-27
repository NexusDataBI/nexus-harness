"""Stable Nexus Harness CLI: ``python3 -m nexus_harness.cli``.

Command surface:

- ``validate`` / ``build`` / ``install``
- ``ci affected`` / ``quality run`` / ``images build``
- ``workflow advance`` / ``project show`` / ``frontend capture``
- ``incidents classify|render`` (local/policy/render only)
- ``doctor --profile local|release|ci-host`` / ``evals run``
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Sequence

from nexus_harness.affected import (
    AffectedPlan,
    CiProfile,
    load_ci_profile,
    resolve_affected,
)
from nexus_harness.build import build_affected_images, image_specs_from_profile
from nexus_harness.compile import compile_harness
from nexus_harness.incident_issue import apply_incident_issue
from nexus_harness.incident_policy import classify_incident
from nexus_harness.incidents import normalize_posthog_problem
from nexus_harness.install import atomic_install
from nexus_harness.project import ProjectRegistry, ProjectRegistryError
from nexus_harness.runtime_install import LiveInstallError
from nexus_harness.serialize import dumps_report
from nexus_harness.state import load_task_state, save_task_state
from nexus_harness.tooling import run_quality
from nexus_harness.validate import validate_repository
from nexus_harness.workflow import advance_stage

GitDiffFn = Callable[[str, str, Path], tuple[str, ...]]
Runner = Callable[..., tuple[int, str, str]]

_CAPTURE_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _validate_capture_task_id(task_id: str | None) -> str:
    from nexus_harness.safe import PathSafetyError

    tid = (task_id or "adhoc").strip() or "adhoc"
    if (
        ".." in tid
        or "/" in tid
        or "\\" in tid
        or "\x00" in tid
        or not _CAPTURE_TASK_ID.fullmatch(tid)
    ):
        raise PathSafetyError("unsafe task id")
    return tid


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(2)


def _json_mode(args) -> bool:
    return bool(getattr(args, "json_out", False))


def cmd_unavailable(command: str, *, json_mode: bool) -> int:
    message = f"{command} is not available yet"
    payload = {
        "status": "unavailable",
        "command": command,
        "message": message,
    }
    if json_mode:
        print(dumps_report(payload))
    else:
        print(message, file=sys.stderr)
    return 2


def _try_optional_main(module: str):
    try:
        mod = __import__(f"nexus_harness.{module}", fromlist=["main"])
    except ImportError:
        return None
    return getattr(mod, "main", None)


def _git_diff_names(base: str, head: str, cwd: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            f"git diff failed (exit {completed.returncode}): "
            f"{(completed.stderr or completed.stdout or '').strip()}"
        )
    lines = [
        line.strip() for line in (completed.stdout or "").splitlines() if line.strip()
    ]
    return tuple(lines)


def _discover_ci_profile(project_root: Path) -> Path:
    env = (os.environ.get("NEXUS_CI_PROFILE") or "").strip()
    if env:
        path = Path(env)
        if not path.is_absolute():
            path = project_root / path
        if not path.is_file():
            raise SystemExit(f"NEXUS_CI_PROFILE not found: {path}")
        return path
    profiles_dir = project_root / "profiles" / "projects"
    if profiles_dir.is_dir():
        matches = sorted(profiles_dir.glob("*.toml"))
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(p.name for p in matches)
            raise SystemExit(
                "multiple CI profiles under profiles/projects/; set "
                f"NEXUS_CI_PROFILE to one of: {names}"
            )
    raise SystemExit(
        "no CI profile found — set NEXUS_CI_PROFILE or add profiles/projects/<id>.toml"
    )


def affected_plan_to_dict(plan: AffectedPlan) -> dict:
    return {
        "components": list(plan.components),
        "checks": list(plan.checks),
        "images": list(plan.images),
        "unmatched": list(plan.unmatched),
    }


def affected_plan_from_dict(payload: Mapping) -> AffectedPlan:
    return AffectedPlan(
        components=tuple(str(x) for x in (payload.get("components") or ())),
        checks=tuple(str(x) for x in (payload.get("checks") or ())),
        images=tuple(str(x) for x in (payload.get("images") or ())),
        unmatched=tuple(str(x) for x in (payload.get("unmatched") or ())),
    )


def load_affected_plan(path: Path) -> AffectedPlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read affected plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"affected plan must be a JSON object: {path}")
    return affected_plan_from_dict(payload)


def cmd_ci_affected(
    *,
    base: str,
    head: str,
    output: Path,
    project_root: Path,
    git_diff: GitDiffFn | None = None,
    profile_path: Path | None = None,
    json_mode: bool = False,
) -> int:
    root = project_root
    profile_file = profile_path or _discover_ci_profile(root)
    profile = load_ci_profile(profile_file)
    diff_fn = git_diff or _git_diff_names
    changed = diff_fn(base, head, root)
    plan = resolve_affected(
        changed,
        profile.components,
        global_paths=profile.global_paths,
    )
    plan_dict = affected_plan_to_dict(plan)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(plan_dict, indent=2) + "\n",
        encoding="utf-8",
    )
    if json_mode:
        print(dumps_report(plan_dict))
    else:
        print(f"wrote affected plan → {output}")
    return 0


def cmd_quality_run(
    *,
    profile: str,
    from_affected: Path,
    project_root: Path,
    runner: Runner | None = None,
    json_mode: bool = False,
) -> int:
    plan = load_affected_plan(from_affected)
    result = run_quality(
        profile=profile,
        affected=plan,
        project_root=project_root,
        runner=runner,
    )
    if json_mode:
        quality = result.quality
        print(
            dumps_report(
                {
                    "exit_code": int(result.exit_code),
                    "quality": quality.to_dict()
                    if hasattr(quality, "to_dict")
                    else quality,
                    "steps": result.steps,
                }
            )
        )
    return int(result.exit_code)


def cmd_images_build(
    *,
    from_affected: Path,
    project_root: Path,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    dry_run: bool = False,
    json_mode: bool = False,
) -> int:
    plan = load_affected_plan(from_affected)
    profile_file = profile_path or _discover_ci_profile(project_root)
    ci_profile: CiProfile = load_ci_profile(profile_file)
    specs = image_specs_from_profile(ci_profile)
    commit = (
        os.environ.get("GITHUB_SHA") or os.environ.get("NEXUS_BUILD_COMMIT") or ""
    ).strip()
    if not commit:
        # Prefer HEAD when running locally / tests without GITHUB_SHA.
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        commit = (completed.stdout or "").strip()
    if not commit and dry_run:
        commit = "dry-run"
    if not commit:
        raise SystemExit(
            "commit SHA required (GITHUB_SHA / NEXUS_BUILD_COMMIT / git HEAD)"
        )
    repository = (
        os.environ.get("NEXUS_BUILD_REPOSITORY") or ci_profile.repository or ""
    ).strip()
    if not repository:
        raise SystemExit(
            "repository required (profile project.repository or NEXUS_BUILD_REPOSITORY)"
        )

    if dry_run or os.environ.get("NEXUS_IMAGES_DRY_RUN") == "1":
        from nexus_harness.build import plan_image_builds

        plans = plan_image_builds(
            plan.images,
            repository=repository,
            commit=commit,
            project_root=project_root,
            image_specs=specs,
        )
        payload = {
            "dry_run": True,
            "repository": repository,
            "commit": commit,
            "plans": [
                {
                    "service": p.service,
                    "image": p.image,
                    "dockerfile": p.dockerfile,
                    "context": p.context,
                }
                for p in plans
            ],
        }
        print(dumps_report(payload) if json_mode else json.dumps(payload, indent=2))
        return 0

    use_runner = runner
    if use_runner is None and os.environ.get("NEXUS_IMAGES_FAKE_RUNNER") == "1":
        # Injectable no-docker path for hermetic tests / local dry builds.
        def fake_runner(argv: Sequence[str], *, cwd=None) -> tuple[int, str, str]:
            meta_arg = next(
                (a for a in argv if str(a).startswith("--metadata-file=")),
                None,
            )
            if meta_arg:
                meta_path = Path(str(meta_arg).split("=", 1)[1])
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                digest = "sha256:" + ("0" * 64)
                meta_path.write_text(
                    json.dumps({"containerimage.digest": digest}),
                    encoding="utf-8",
                )
            return 0, "", ""

        use_runner = fake_runner

    manifest = build_affected_images(
        plan.images,
        repository=repository,
        commit=commit,
        project_root=project_root,
        runner=use_runner,
        image_specs=specs,
    )
    print(dumps_report(manifest) if json_mode else json.dumps(manifest, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="nexus",
        description="Nexus Harness CLI",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="deterministic JSON on stdout (no progress prose)",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    validate = sub.add_parser("validate", help="validate canonical harness tree")
    validate.add_argument("root", nargs="?", type=Path, default=None)

    build = sub.add_parser("build", help="compile generated runtime files")
    build.add_argument(
        "target",
        nargs="?",
        default=None,
        help="optional compile target; `adapters` compiles the project root",
    )

    install = sub.add_parser("install", help="install generated harness files")
    install.add_argument("source", type=Path)
    install.add_argument("target", type=Path)

    runtime = sub.add_parser(
        "runtime", help="live runtime mapping (plan/apply/rollback)"
    )
    runtime_sub = runtime.add_subparsers(dest="runtime_cmd", required=True)
    rinspect = runtime_sub.add_parser("inspect", help="inspect live runtime layout")
    rinspect.add_argument("runtime_name", choices=("codex", "cursor", "claude"))
    rinspect.add_argument("--home", type=Path, default=None)
    rinstall = runtime_sub.add_parser(
        "install", help="plan or apply live runtime integration"
    )
    rinstall.add_argument("runtime_name", choices=("codex", "cursor", "claude"))
    rinstall.add_argument(
        "--plan",
        action="store_true",
        help="print mapping with zero mutation (default if --apply is omitted)",
    )
    rinstall.add_argument(
        "--apply",
        action="store_true",
        help="apply a conflict-free plan; refused when blocked",
    )
    rinstall.add_argument("--home", type=Path, default=None)
    rinstall.add_argument("--dist", type=Path, default=None)
    rinstall.add_argument("--engine-root", type=Path, default=None)
    rinstall.add_argument("--project", type=Path, default=None)
    rinstall.add_argument("--backup-root", type=Path, default=None)
    rrollback = runtime_sub.add_parser(
        "rollback", help="restore live shared-file backup"
    )
    rrollback.add_argument("runtime_name", choices=("codex", "cursor", "claude"))
    rrollback.add_argument("--backup", type=Path, required=True)

    doctor = sub.add_parser("doctor", help="environment doctor")
    doctor.add_argument(
        "--profile",
        choices=("local", "release", "ci-host"),
        default="local",
        help="local harness, local release assembly, or hermetic CI-host fixture",
    )
    doctor.add_argument(
        "--project",
        dest="doctor_project",
        default=None,
        help="optional managed project id for Biome/Vitest/Playwright/Trivy checks",
    )
    evals = sub.add_parser("evals", help="eval runner")
    evals_sub = evals.add_subparsers(dest="evals_cmd", required=True)
    erun = evals_sub.add_parser("run", help="run deterministic policy evals")
    erun.add_argument(
        "cases",
        nargs="?",
        type=Path,
        default=None,
        help="directory of JSON eval cases (default: evals/cases)",
    )

    workflow = sub.add_parser("workflow", help="task lifecycle")
    workflow_sub = workflow.add_subparsers(dest="workflow_cmd", required=True)
    advance = workflow_sub.add_parser("advance", help="advance task stage")
    advance.add_argument("--state", type=Path, required=True)
    advance.add_argument("--to", type=int, required=True)

    quality = sub.add_parser("quality", help="quality gate runners")
    quality_sub = quality.add_subparsers(dest="quality_cmd", required=True)
    qrun = quality_sub.add_parser("run", help="run quality profile from affected plan")
    qrun.add_argument("--profile", default="standard")
    qrun.add_argument("--from-affected", type=Path, required=True)

    project = sub.add_parser("project", help="project registry")
    project_sub = project.add_subparsers(dest="project_cmd", required=True)
    show = project_sub.add_parser("show", help="show project identity")
    show.add_argument("--id", dest="project_id", default=None)
    show.add_argument("--repository", default=None)

    frontend = sub.add_parser("frontend", help="frontend visual QA")
    frontend_sub = frontend.add_subparsers(dest="frontend_cmd", required=True)
    capture = frontend_sub.add_parser(
        "capture", help="capture Playwright visual evidence for a route"
    )
    capture.add_argument("--route", required=True)
    capture.add_argument("--task-id", default=None)

    incidents = sub.add_parser("incidents", help="local incident policy and render")
    incidents_sub = incidents.add_subparsers(dest="incidents_cmd", required=True)
    classify = incidents_sub.add_parser("classify", help="classify without GitHub")
    classify.add_argument("--input", type=Path, required=True)
    render = incidents_sub.add_parser("render", help="render issue body without GitHub")
    render.add_argument("--input", type=Path, required=True)

    ci = sub.add_parser("ci", help="CI plan helpers")
    ci_sub = ci.add_subparsers(dest="ci_cmd", required=True)
    affected = ci_sub.add_parser(
        "affected", help="resolve affected plan from git range"
    )
    affected.add_argument("--base", required=True)
    affected.add_argument("--head", required=True)
    affected.add_argument("--output", type=Path, required=True)

    images = sub.add_parser("images", help="image build helpers")
    images_sub = images.add_subparsers(dest="images_cmd", required=True)
    ibuild = images_sub.add_parser(
        "build", help="build affected images from affected plan"
    )
    ibuild.add_argument("--from-affected", type=Path, required=True)
    ibuild.add_argument(
        "--dry-run",
        action="store_true",
        help="plan only; do not invoke docker",
    )
    return parser


def _coerce_probe(probe):
    if probe is True:
        return lambda url: True
    if probe is False:
        return lambda url: False
    return probe


def cmd_frontend_capture(
    *,
    route: str,
    project_root: Path,
    task_id: str | None = None,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    artifact_root: Path | None = None,
    probe=None,
    popen=None,
    json_mode: bool = False,
) -> int:
    from nexus_harness.devserver import (
        FrontendConfig,
        FrontendConfigError,
        ensure_dev_server,
        probe_readiness,
    )
    from nexus_harness.playwright import PlaywrightError, capture_route, validate_route
    from nexus_harness.safe import PathSafetyError, confine
    from nexus_harness.state import TaskState
    from nexus_harness.visual import bind_visual_requirement

    try:
        profile_file = profile_path or _discover_ci_profile(project_root)
        profile = load_ci_profile(profile_file)
    except SystemExit as exc:
        print(exc.args[0] if exc.args else "no CI profile found")
        return 2
    except FrontendConfigError as exc:
        print(exc.failure.message)
        return 2

    frontend = profile.frontend
    if not isinstance(frontend, FrontendConfig):
        print("profile has no [frontend] table")
        return 2

    try:
        tid = _validate_capture_task_id(task_id)
        validate_route(route)
        tasks_root = project_root / ".nexus" / "tasks"
        out_root = (
            Path(artifact_root)
            if artifact_root is not None
            else confine(tasks_root / tid / "evidence", tasks_root)
        )
        out_root.mkdir(parents=True, exist_ok=True)
        state_file = tasks_root / tid / "state.json"
        loaded = False
        task_state = None
        if state_file.is_file():
            try:
                task_state = load_task_state(state_file)
                loaded = True
            except (OSError, ValueError, TypeError, KeyError):
                task_state = None
        if task_state is None:
            task_state = TaskState.new(tid, profile.project_id)
        bind_visual_requirement(task_state, profile, list(task_state.changed_paths))
        state_path = state_file if loaded else None
        if state_path is not None:
            save_task_state(task_state, state_path)
        probe_fn = _coerce_probe(probe)
        check = probe_fn or probe_readiness
        if not check(frontend.readiness_url):
            server = ensure_dev_server(
                frontend,
                artifact_root=out_root,
                probe=probe_fn,
                popen=popen,
                cwd=project_root,
                project_root=project_root,
            )
            if not server.ok:
                failure = server.failure
                print(
                    failure.message if failure is not None else "localhost is not ready"
                )
                return 1
        result = capture_route(
            route,
            config=frontend,
            artifact_root=out_root,
            runner=runner,
            task_id=tid,
            task_state=task_state,
            project_root=project_root,
            state_path=state_path,
        )
    except (PlaywrightError, PathSafetyError) as exc:
        if json_mode:
            print(dumps_report({"ok": False, "error": str(exc)}))
        else:
            print(str(exc))
        return 2
    if json_mode:
        print(
            dumps_report({"ok": bool(result.ok), "output_dir": str(result.output_dir)})
        )
    else:
        print(f"wrote playwright capture → {result.output_dir}")
    return 0 if result.ok else 1


def cmd_validate(*, root: Path, json_mode: bool) -> int:
    result = validate_repository(root)
    payload = {"ok": not result.errors, "errors": list(result.errors)}
    if json_mode:
        print(dumps_report(payload))
    else:
        for error in result.errors:
            print(error, file=sys.stderr)
        if not result.errors:
            print("validate ok")
    return 0 if not result.errors else 1


def cmd_build(*, root: Path, json_mode: bool) -> int:
    lock = compile_harness(root)
    generated = lock.get("generated_hashes") or {}
    engine = lock.get("engine_hashes") or {}
    payload = {
        "ok": True,
        "generated": len(generated),
        "engine": len(engine),
    }
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"compiled {len(generated)} generated files, {len(engine)} engine files")
    return 0


def cmd_install(*, source: Path, target: Path, json_mode: bool) -> int:
    backup = atomic_install(source, target)
    payload = {"ok": True, "backup": str(backup)}
    if json_mode:
        print(dumps_report(payload))
    else:
        print(backup)
    return 0


def cmd_runtime_inspect(
    *, runtime_name: str, home: Path | None, json_mode: bool
) -> int:
    from nexus_harness.runtime_install import default_runtime_home, inspect_live_runtime

    target = home if home is not None else default_runtime_home(runtime_name)
    payload = inspect_live_runtime(runtime_name, target)
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"{payload['runtime']} home={payload['home']} exists={payload['exists']}")
        for name, artifact in (payload.get("artifacts") or {}).items():
            print(
                f"  {name}: {artifact.get('scope')} "
                f"{artifact.get('path')} exists={artifact.get('exists')}"
            )
    return 0


def cmd_runtime_install(
    *,
    runtime_name: str,
    plan_only: bool,
    apply: bool,
    home: Path | None,
    dist: Path | None,
    engine_root: Path | None,
    project: Path | None,
    backup_root: Path | None,
    project_root: Path,
    json_mode: bool,
) -> int:
    from nexus_harness.runtime_install import (
        apply_live_install,
        default_engine_root,
        default_runtime_home,
        plan_live_install,
    )

    if apply and plan_only:
        raise LiveInstallError("use either --plan or --apply, not both")
    target = home if home is not None else default_runtime_home(runtime_name)
    dist_path = Path(dist) if dist is not None else Path(project_root) / "dist"
    engine = Path(engine_root) if engine_root is not None else default_engine_root()
    plan = plan_live_install(
        runtime_name,
        home=target,
        dist=dist_path,
        engine_root=engine,
        project_root=project,
        backup_root=backup_root,
    )
    if apply:
        result = apply_live_install(plan)
        payload = {
            "ok": result.ok,
            "runtime": result.runtime,
            "backup_root": result.backup_root,
            "files": list(result.files),
            "plan": plan.to_dict(),
        }
        if json_mode:
            print(dumps_report(payload))
        else:
            print(f"applied {result.runtime}; backup {result.backup_root}")
        return 0
    payload = plan.to_dict()
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"{plan.runtime} blocked={plan.blocked}")
        for item in plan.mutations:
            print(
                f"  {item.operation} {item.artifact} -> {item.destination} "
                f"[{item.scope}] {item.risk}"
            )
    return 2 if plan.blocked else 0


def cmd_runtime_rollback(*, backup: Path, json_mode: bool) -> int:
    from nexus_harness.runtime_install import LiveApplyResult, rollback_live_install

    payload = json.loads(
        Path(backup).joinpath("MANIFEST.json").read_text(encoding="utf-8")
    )
    result = LiveApplyResult(
        ok=True,
        runtime=str(payload.get("runtime") or "unknown"),
        backup_root=str(backup),
        engine_backup=payload.get("engine_backup"),
        files=tuple(
            str(item.get("destination")) for item in (payload.get("files") or ())
        ),
    )
    rollback_live_install(result)
    if json_mode:
        print(dumps_report({"ok": True, "backup": str(backup)}))
    else:
        print(f"restored {backup}")
    return 0


def cmd_workflow_advance(
    *, state_path: Path, target_stage: int, json_mode: bool
) -> int:
    state = load_task_state(state_path)
    advanced = advance_stage(state, target_stage)
    save_task_state(advanced, state_path)
    payload = advanced.to_dict()
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"stage {advanced.stage}")
    return 0


def cmd_project_show(
    *,
    project_root: Path,
    project_id: str | None,
    repository: str | None,
    json_mode: bool,
) -> int:
    registry_path = project_root / "projects.toml"
    registry = ProjectRegistry.load(registry_path if registry_path.is_file() else None)
    if project_id:
        project = registry.by_id(project_id)
    elif repository:
        project = registry.by_repository(repository)
    else:
        if json_mode:
            print(
                dumps_report(
                    {
                        "ok": False,
                        "error": "project show requires --id or --repository",
                    }
                )
            )
        else:
            print("project show requires --id or --repository", file=sys.stderr)
        return 2
    payload = {
        "id": project.id,
        "name": project.name,
        "repository": project.repository,
        "client": project.client,
        "status": project.status,
    }
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"{project.id} {project.repository} {project.status}")
    return 0


def _load_incident_problem(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("incident input must be a JSON object")
    return payload


def _incident_decision(problem: dict, candidate):
    return classify_incident(
        occurrences=candidate.occurrences,
        affected_users=candidate.affected_users,
        fingerprint=candidate.fingerprint,
        regression=bool(problem.get("regression")),
        fatal=bool(problem.get("fatal")),
        security_adjacent=bool(problem.get("security_adjacent")),
        open_issues=problem.get("open_issues") or (),
    )


def cmd_incidents_classify(*, input_path: Path, json_mode: bool) -> int:
    problem = _load_incident_problem(input_path)
    candidate = normalize_posthog_problem(problem)
    decision = _incident_decision(problem, candidate)
    payload = {
        "action": decision.action,
        "reason": decision.reason,
        "issue_number": decision.issue_number,
        "fingerprint": candidate.fingerprint,
        "mutated": False,
    }
    if json_mode:
        print(dumps_report(payload))
    else:
        print(f"{decision.action} {decision.reason}".strip())
    return 0


def cmd_incidents_render(
    *,
    input_path: Path,
    json_mode: bool,
    github=None,
) -> int:
    problem = _load_incident_problem(input_path)
    candidate = normalize_posthog_problem(problem)
    decision = _incident_decision(problem, candidate)
    result = apply_incident_issue(
        candidate,
        github,
        repo="",
        action=decision.action,
        authorize_remote_mutation=False,
    )
    payload = {
        "action": result.action,
        "request_title": result.request_title,
        "request_body": result.request_body,
        "issue_number": result.issue_number,
        "mutated": bool(result.mutated),
    }
    if json_mode:
        print(dumps_report(payload))
    else:
        print(result.request_body)
    return 0


def cmd_doctor(
    *,
    project_root: Path,
    profile: str,
    json_mode: bool,
    selected_project: str | None = None,
) -> int:
    from nexus_harness.doctor import format_doctor_report, run_doctor

    report = run_doctor(
        project_root,
        profile=profile,
        selected_project=selected_project,
    )
    if json_mode:
        print(dumps_report(report.to_dict()))
    else:
        print(format_doctor_report(report))
    return 1 if report.gate == "FAIL" else 0


def cmd_evals_run(
    *,
    project_root: Path,
    cases: Path | None,
    json_mode: bool,
) -> int:
    from nexus_harness.evals import format_evals_report, run_evals

    root = Path(project_root)
    cases_dir = Path(cases) if cases else root / "evals" / "cases"
    if not cases_dir.is_absolute():
        cases_dir = root / cases_dir
    report = run_evals(cases_dir, repo_root=root)
    if json_mode:
        print(dumps_report(report.to_dict()))
    else:
        print(format_evals_report(report))
    return 0 if report.gate == "PASS" else 1


def cmd_optional_module(command: str, module: str, *, json_mode: bool) -> int:
    handler = _try_optional_main(module)
    if handler is None:
        return cmd_unavailable(command, json_mode=json_mode)
    return int(handler())


def main(
    argv: Sequence[str] | None = None,
    *,
    git_diff: GitDiffFn | None = None,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    artifact_root: Path | None = None,
    probe=None,
    popen=None,
    github=None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return 2 if exc.code is None else int(exc.code)

    root = Path(args.project_root) if args.project_root else Path.cwd()
    json_mode = _json_mode(args)

    try:
        if args.group == "validate":
            return cmd_validate(
                root=Path(args.root) if args.root else root,
                json_mode=json_mode,
            )
        if args.group == "build":
            raw = getattr(args, "target", None)
            if raw is None or str(raw).strip().lower() in {"adapters", "adapter"}:
                compile_root = root
            else:
                compile_root = Path(raw)
            return cmd_build(
                root=compile_root,
                json_mode=json_mode,
            )
        if args.group == "install":
            return cmd_install(
                source=Path(args.source),
                target=Path(args.target),
                json_mode=json_mode,
            )
        if args.group == "runtime":
            if args.runtime_cmd == "inspect":
                return cmd_runtime_inspect(
                    runtime_name=args.runtime_name,
                    home=getattr(args, "home", None),
                    json_mode=json_mode,
                )
            if args.runtime_cmd == "install":
                return cmd_runtime_install(
                    runtime_name=args.runtime_name,
                    plan_only=bool(getattr(args, "plan", False)),
                    apply=bool(getattr(args, "apply", False)),
                    home=getattr(args, "home", None),
                    dist=getattr(args, "dist", None),
                    engine_root=getattr(args, "engine_root", None),
                    project=getattr(args, "project", None),
                    backup_root=getattr(args, "backup_root", None),
                    project_root=root,
                    json_mode=json_mode,
                )
            if args.runtime_cmd == "rollback":
                return cmd_runtime_rollback(
                    backup=Path(args.backup),
                    json_mode=json_mode,
                )
            return cmd_unavailable("runtime", json_mode=json_mode)
        if args.group == "doctor":
            return cmd_doctor(
                project_root=root,
                profile=getattr(args, "profile", "local"),
                json_mode=json_mode,
                selected_project=getattr(args, "doctor_project", None),
            )
        if args.group == "evals":
            if getattr(args, "evals_cmd", None) == "run":
                return cmd_evals_run(
                    project_root=root,
                    cases=getattr(args, "cases", None),
                    json_mode=json_mode,
                )
            return cmd_unavailable("evals", json_mode=json_mode)
        if args.group == "workflow" and args.workflow_cmd == "advance":
            return cmd_workflow_advance(
                state_path=Path(args.state),
                target_stage=int(args.to),
                json_mode=json_mode,
            )
        if args.group == "project" and args.project_cmd == "show":
            return cmd_project_show(
                project_root=root,
                project_id=getattr(args, "project_id", None),
                repository=getattr(args, "repository", None),
                json_mode=json_mode,
            )
        if args.group == "incidents" and args.incidents_cmd == "classify":
            return cmd_incidents_classify(
                input_path=Path(args.input),
                json_mode=json_mode,
            )
        if args.group == "incidents" and args.incidents_cmd == "render":
            return cmd_incidents_render(
                input_path=Path(args.input),
                json_mode=json_mode,
                github=github,
            )
        if args.group == "ci" and args.ci_cmd == "affected":
            return cmd_ci_affected(
                base=args.base,
                head=args.head,
                output=Path(args.output),
                project_root=root,
                git_diff=git_diff,
                profile_path=profile_path,
                json_mode=json_mode,
            )
        if args.group == "quality" and args.quality_cmd == "run":
            return cmd_quality_run(
                profile=args.profile,
                from_affected=Path(args.from_affected),
                project_root=root,
                runner=runner,
                json_mode=json_mode,
            )
        if args.group == "images" and args.images_cmd == "build":
            return cmd_images_build(
                from_affected=Path(args.from_affected),
                project_root=root,
                runner=runner,
                profile_path=profile_path,
                dry_run=bool(getattr(args, "dry_run", False)),
                json_mode=json_mode,
            )
        if (
            args.group == "frontend"
            and getattr(args, "frontend_cmd", None) == "capture"
        ):
            return cmd_frontend_capture(
                route=args.route,
                task_id=getattr(args, "task_id", None),
                project_root=root,
                runner=runner,
                profile_path=profile_path,
                artifact_root=artifact_root,
                probe=probe,
                popen=popen,
                json_mode=json_mode,
            )
    except SystemExit as exc:
        code = 2 if exc.code is None else int(exc.code)
        message = exc.args[0] if exc.args else "command failed"
        if json_mode:
            print(dumps_report({"ok": False, "error": str(message)}))
        elif not isinstance(message, int):
            print(message, file=sys.stderr)
        return code if code else 2
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        ProjectRegistryError,
        LiveInstallError,
    ) as exc:
        if json_mode:
            print(dumps_report({"ok": False, "error": str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
