"""Parse command/argv into policy intent without executing anything."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import PurePosixPath

_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_PREFIX_WRAPPERS = frozenset(
    {
        "sudo",
        "doas",
        "env",
        "nice",
        "nohup",
        "command",
        "time",
        "timeout",
        "exec",
        "builtin",
    }
)
_COMPOSE_VALUE_FLAGS = frozenset(
    {
        "-f",
        "--file",
        "-p",
        "--project-name",
        "--project-directory",
        "--env-file",
        "--profile",
    }
)
_DOCKER_COMPOSE_OPS = frozenset({"up", "down", "restart", "pull", "push"})
_KUBECTL_OPS = frozenset({"apply", "delete", "rollout", "patch", "exec"})
_HELM_OPS = frozenset({"install", "upgrade", "uninstall"})
_SQL_CLIENTS = frozenset({"psql", "mysql", "mysqlsh", "sqlite3"})
_MAX_UNWRAP = 6

_SENSITIVE_RAW = re.compile(
    r"\b(?:ssh|scp|kubectl|helm)\b"
    r"|docker(?:-compose)?(?:\s+compose)?\b"
    r"|\brm\s+-[^\s]*[rR]"
    r"|\bmkfs"
    r"|\bdrop\s+table\b"
    r"|:\(\)\s*\{",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandIntent:
    executable: str
    argv: tuple[str, ...]
    subcommands: tuple[str, ...]
    raw: str
    parse_status: str
    shell_wrapper: str | None
    remote_target: str | None
    destructive_operation: str | None
    production_capable: bool


def _empty(raw: str) -> CommandIntent:
    return CommandIntent(
        executable="",
        argv=(),
        subcommands=(),
        raw=raw,
        parse_status="empty",
        shell_wrapper=None,
        remote_target=None,
        destructive_operation=None,
        production_capable=False,
    )


def _malformed(raw: str) -> CommandIntent:
    sensitive = bool(_SENSITIVE_RAW.search(raw or ""))
    return CommandIntent(
        executable="",
        argv=(),
        subcommands=(),
        raw=raw,
        parse_status="malformed",
        shell_wrapper=None,
        remote_target=None,
        destructive_operation="opaque" if sensitive else None,
        production_capable=sensitive,
    )


def _basename(token: str) -> str:
    name = PurePosixPath(token.replace("\\", "/")).name.lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return name


def _skip_leading_flags(
    tokens: list[str],
    *,
    start: int = 1,
    value_flags: frozenset[str] = frozenset(),
) -> int:
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return index + 1
        if token.startswith("-") and token != "-":
            if token in value_flags and "=" not in token and index + 1 < len(tokens):
                index += 2
                continue
            index += 1
            continue
        return index
    return index


def _first_non_flag(
    tokens: list[str],
    start: int = 1,
    value_flags: frozenset[str] = frozenset(),
) -> str | None:
    index = _skip_leading_flags(tokens, start=start, value_flags=value_flags)
    if index < len(tokens):
        return tokens[index]
    return None


def _extract_shell_script(tokens: list[str]) -> str | None:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-c", "-lc", "-cl"}:
            if index + 1 >= len(tokens):
                return None
            return tokens[index + 1]
        if (
            token.startswith("-")
            and not token.startswith("--")
            and len(token) > 1
            and "c" in token[1:]
        ):
            if index + 1 >= len(tokens):
                return None
            return tokens[index + 1]
        index += 1
    return None


def _strip_prefix_wrappers(tokens: list[str]) -> list[str]:
    remaining = list(tokens)
    guard = 0
    while remaining and guard < _MAX_UNWRAP:
        guard += 1
        exe = _basename(remaining[0])
        if exe not in _PREFIX_WRAPPERS:
            break
        remaining = remaining[1:]
        if exe in {"sudo", "doas"}:
            remaining = remaining[
                _skip_leading_flags(
                    remaining,
                    start=0,
                    value_flags=frozenset(
                        {"-u", "-g", "-h", "-C", "-D", "--user", "--group"}
                    ),
                ) :
            ]
            continue
        if exe == "env":
            while (
                remaining and "=" in remaining[0] and not remaining[0].startswith("-")
            ):
                remaining = remaining[1:]
            remaining = remaining[_skip_leading_flags(remaining, start=0) :]
            continue
        remaining = remaining[_skip_leading_flags(remaining, start=0) :]
    return remaining


def _unwrap(tokens: list[str]) -> tuple[list[str], str | None, str]:
    wrappers: list[str] = []
    current = list(tokens)
    for _ in range(_MAX_UNWRAP):
        current = _strip_prefix_wrappers(current)
        if not current:
            return current, wrappers[-1] if wrappers else None, "ok"
        exe = _basename(current[0])
        if exe not in _SHELLS:
            return current, wrappers[-1] if wrappers else None, "ok"
        script = _extract_shell_script(current)
        if script is None:
            return current, wrappers[-1] if wrappers else None, "ok"
        wrappers.append(exe)
        try:
            current = shlex.split(script, posix=True)
        except ValueError:
            return current, wrappers[-1] if wrappers else None, "malformed"
    return current, wrappers[-1] if wrappers else None, "ok"


def _verb_after_flags(tokens: list[str], value_flags: frozenset[str]) -> str | None:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            if index + 1 < len(tokens):
                return tokens[index + 1]
            return None
        if token.startswith("-") and token != "-":
            if token in value_flags and index + 1 < len(tokens):
                index += 2
                continue
            index += 1
            continue
        return token
    return None


def _rm_is_destructive(argv: tuple[str, ...]) -> bool:
    recursive = False
    for token in argv[1:]:
        if token in {"--recursive", "-R", "-r"}:
            recursive = True
            continue
        if token.startswith("--"):
            continue
        if token.startswith("-") and token != "-":
            letters = token[1:]
            if "r" in letters.lower() or "R" in letters:
                recursive = True
    return recursive


def _sql_destructive(argv: tuple[str, ...]) -> bool:
    lowered = [item.lower() for item in argv]
    for index, token in enumerate(lowered[:-1]):
        if token == "drop" and lowered[index + 1] == "table":
            return True
    for index, token in enumerate(argv[:-1]):
        if token in {"-c", "--command", "-e"} and index + 1 < len(argv):
            payload = argv[index + 1].lower()
            if re.search(r"\bdrop\s+table\b", payload):
                return True
    return False


def _classify(tokens: list[str], raw: str, wrapper: str | None) -> CommandIntent:
    argv = tuple(tokens)
    executable = _basename(tokens[0]) if tokens else ""
    remote_target = None
    subcommands: list[str] = []
    production = False

    if executable in {"ssh", "scp"}:
        remote_target = _first_non_flag(tokens)
        production = True
        subcommands = [executable]
    elif executable in {"docker-compose", "docker_compose"}:
        compose_op = _first_non_flag(tokens, value_flags=_COMPOSE_VALUE_FLAGS)
        subcommands = ["compose"] + ([compose_op] if compose_op else [])
        production = compose_op in _DOCKER_COMPOSE_OPS
    elif executable == "docker":
        rest_index = _skip_leading_flags(
            tokens,
            value_flags=frozenset({"-H", "--host", "-c", "--context"}),
        )
        if rest_index < len(tokens) and tokens[rest_index] == "compose":
            compose_op = _first_non_flag(
                tokens,
                start=rest_index + 1,
                value_flags=_COMPOSE_VALUE_FLAGS,
            )
            subcommands = ["compose"] + ([compose_op] if compose_op else [])
            production = compose_op in _DOCKER_COMPOSE_OPS
    elif executable == "kubectl":
        kubectl_op = _verb_after_flags(
            tokens,
            value_flags=frozenset(
                {
                    "-n",
                    "--namespace",
                    "--context",
                    "--kubeconfig",
                    "-f",
                    "--filename",
                }
            ),
        )
        subcommands = [kubectl_op] if kubectl_op else []
        production = kubectl_op in _KUBECTL_OPS
    elif executable == "helm":
        helm_op = _first_non_flag(tokens)
        subcommands = [helm_op] if helm_op else []
        production = helm_op in _HELM_OPS

    destructive = None
    if executable == "rm" and _rm_is_destructive(argv):
        destructive = "rm"
    elif executable.startswith("mkfs"):
        destructive = "mkfs"
        production = True
    elif executable == "format":
        destructive = "format"
        production = True
    elif executable in _SQL_CLIENTS and _sql_destructive(argv):
        destructive = "drop_table"
    elif ":(){" in raw.replace(" ", ""):
        destructive = "fork_bomb"

    return CommandIntent(
        executable=executable,
        argv=argv,
        subcommands=tuple(item for item in subcommands if item),
        raw=raw,
        parse_status="ok",
        shell_wrapper=wrapper,
        remote_target=remote_target,
        destructive_operation=destructive,
        production_capable=production,
    )


def parse_command_intent(
    command: str | None = None,
    argv: list[str] | tuple[str, ...] | None = None,
) -> CommandIntent:
    raw = command if isinstance(command, str) else ""
    if isinstance(argv, (list, tuple)) and argv:
        tokens = [str(item) for item in argv if str(item)]
        if not raw:
            raw = " ".join(tokens)
        if not tokens:
            return _empty(raw)
        unwrapped, wrapper, status = _unwrap(tokens)
        if status == "malformed":
            return _malformed(raw)
        if not unwrapped:
            return _empty(raw)
        return _classify(unwrapped, raw, wrapper)

    if not isinstance(command, str) or not command.strip():
        return _empty(raw)
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return _malformed(command)
    if not tokens:
        return _empty(command)
    unwrapped, wrapper, status = _unwrap(tokens)
    if status == "malformed":
        return _malformed(command)
    if not unwrapped:
        return _empty(command)
    return _classify(unwrapped, command, wrapper)


def parse_tool_command(tool_input: dict) -> CommandIntent:
    argv_raw = tool_input.get("argv") or tool_input.get("args")
    argv: list[str] | None = None
    if isinstance(argv_raw, (list, tuple)) and argv_raw:
        argv = [str(item) for item in argv_raw]
    command = tool_input.get("command") or tool_input.get("cmd")
    command_text = command if isinstance(command, str) else None
    return parse_command_intent(command_text, argv)
