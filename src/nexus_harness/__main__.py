"""CLI entry: ``python3 -m nexus_harness`` (and ``scripts/nexus`` wrapper).

Subcommands used by the Quality Gate workflow template:

- ``ci affected --base SHA --head SHA --output PATH``
- ``quality run --profile NAME --from-affected PATH``
- ``images build --from-affected PATH``
- ``frontend capture --route /path [--task-id TASK]``
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence

from nexus_harness.affected import (
    AffectedPlan,
    CiProfile,
    load_ci_profile,
    resolve_affected,
)
from nexus_harness.build import build_affected_images, image_specs_from_profile
from nexus_harness.tooling import run_quality

GitDiffFn = Callable[[str, str, Path], tuple[str, ...]]
Runner = Callable[..., tuple[int, str, str]]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(2)


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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(affected_plan_to_dict(plan), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote affected plan → {output}")
    return 0


def cmd_quality_run(
    *,
    profile: str,
    from_affected: Path,
    project_root: Path,
    runner: Runner | None = None,
) -> int:
    plan = load_affected_plan(from_affected)
    result = run_quality(
        profile=profile,
        affected=plan,
        project_root=project_root,
        runner=runner,
    )
    return int(result.exit_code)


def cmd_images_build(
    *,
    from_affected: Path,
    project_root: Path,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    dry_run: bool = False,
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
        print(
            json.dumps(
                {
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
                },
                indent=2,
            )
        )
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
    print(json.dumps(manifest, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="nexus",
        description="Nexus Harness CI / quality / image CLI",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    sub = parser.add_subparsers(dest="group", required=True)

    ci = sub.add_parser("ci", help="CI plan helpers")
    ci_sub = ci.add_subparsers(dest="ci_cmd", required=True)
    affected = ci_sub.add_parser(
        "affected", help="resolve affected plan from git range"
    )
    affected.add_argument("--base", required=True)
    affected.add_argument("--head", required=True)
    affected.add_argument("--output", type=Path, required=True)

    quality = sub.add_parser("quality", help="quality gate runners")
    quality_sub = quality.add_subparsers(dest="quality_cmd", required=True)
    qrun = quality_sub.add_parser("run", help="run quality profile from affected plan")
    qrun.add_argument("--profile", default="standard")
    qrun.add_argument("--from-affected", type=Path, required=True)

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

    frontend = sub.add_parser("frontend", help="frontend visual QA")
    frontend_sub = frontend.add_subparsers(dest="frontend_cmd", required=True)
    capture = frontend_sub.add_parser(
        "capture", help="capture Playwright visual evidence for a route"
    )
    capture.add_argument("--route", required=True)
    capture.add_argument("--task-id", default=None)
    return parser


def cmd_frontend_capture(
    *,
    route: str,
    project_root: Path,
    task_id: str | None = None,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    artifact_root: Path | None = None,
) -> int:
    from nexus_harness.devserver import FrontendConfig, FrontendConfigError
    from nexus_harness.playwright import PlaywrightError, capture_route
    from nexus_harness.safe import PathSafetyError
    from nexus_harness.state import load_task_state

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

    tid = (task_id or "adhoc").strip() or "adhoc"
    out_root = (
        Path(artifact_root)
        if artifact_root is not None
        else project_root / ".nexus" / "tasks" / tid / "evidence"
    )
    task_state = None
    state_file = project_root / ".nexus" / "tasks" / tid / "state.json"
    if state_file.is_file():
        try:
            task_state = load_task_state(state_file)
        except (OSError, ValueError, TypeError, KeyError):
            task_state = None

    try:
        result = capture_route(
            route,
            config=frontend,
            artifact_root=out_root,
            runner=runner,
            task_id=tid,
            task_state=task_state,
            project_root=project_root,
        )
    except (PlaywrightError, PathSafetyError) as exc:
        print(str(exc))
        return 2
    print(f"wrote playwright capture → {result.output_dir}")
    return 0 if result.ok else 1


def main(
    argv: Sequence[str] | None = None,
    *,
    git_diff: GitDiffFn | None = None,
    runner: Runner | None = None,
    profile_path: Path | None = None,
    artifact_root: Path | None = None,
) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return 2 if exc.code is None else int(exc.code)

    root = Path(args.project_root) if args.project_root else Path.cwd()

    if args.group == "ci" and args.ci_cmd == "affected":
        return cmd_ci_affected(
            base=args.base,
            head=args.head,
            output=Path(args.output),
            project_root=root,
            git_diff=git_diff,
            profile_path=profile_path,
        )
    if args.group == "quality" and args.quality_cmd == "run":
        return cmd_quality_run(
            profile=args.profile,
            from_affected=Path(args.from_affected),
            project_root=root,
            runner=runner,
        )
    if args.group == "images" and args.images_cmd == "build":
        return cmd_images_build(
            from_affected=Path(args.from_affected),
            project_root=root,
            runner=runner,
            profile_path=profile_path,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
    if args.group == "frontend" and getattr(args, "frontend_cmd", None) == "capture":
        return cmd_frontend_capture(
            route=args.route,
            task_id=getattr(args, "task_id", None),
            project_root=root,
            runner=runner,
            profile_path=profile_path,
            artifact_root=artifact_root,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
