"""CLI entry: ``python3 -m nexus_harness`` delegates to ``nexus_harness.cli``."""

from nexus_harness.cli import (
    build_parser,
    cmd_ci_affected,
    cmd_frontend_capture,
    cmd_images_build,
    cmd_quality_run,
    main,
)

__all__ = [
    "build_parser",
    "cmd_ci_affected",
    "cmd_frontend_capture",
    "cmd_images_build",
    "cmd_quality_run",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
