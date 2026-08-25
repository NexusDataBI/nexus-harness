from __future__ import annotations

import argparse
import json
from pathlib import Path

from nexus_harness.memory.doctor import memory_doctor
from nexus_harness.memory.lifecycle import verify_memory
from nexus_harness.memory.models import MemoryStatus
from nexus_harness.memory.portfolio import init_portfolio_vault
from nexus_harness.memory.retrieval import MemoryQueryContext, search_memory
from nexus_harness.memory.store import (
    init_project_memory,
    load_project_memories,
    read_memory,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(
        prog="memory",
        description="Local Nexus Memory commands. No remote sync.",
    )
    parser.add_argument("--root", type=Path, default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show local memory counts")
    search = sub.add_parser("search", help="search local project memory")
    search.add_argument("query", nargs="+")
    show = sub.add_parser("show", help="show one local memory record")
    show.add_argument("memory_id")
    sub.add_parser("candidates", help="list local candidate memories")
    verify = sub.add_parser("verify", help="verify a local candidate at a commit")
    verify.add_argument("memory_id")
    verify.add_argument("--commit", required=True)
    sub.add_parser("doctor", help="report local memory health")
    sub.add_parser("init-project", help="initialize project memory directories")
    init_vault = sub.add_parser("init-vault", help="initialize a local portfolio vault")
    init_vault.add_argument("path", type=Path)

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code is None else int(exc.code)

    root = Path(args.root) if args.root is not None else Path.cwd()
    command = args.command
    if command == "status":
        records = load_project_memories(root)
        counts = {status.value: 0 for status in MemoryStatus}
        for record in records:
            counts[record.status.value] += 1
        print(json.dumps({"project_records": len(records), "by_status": counts}))
        return 0
    if command == "search":
        query = " ".join(args.query)
        hits = search_memory(
            root,
            query,
            MemoryQueryContext(project_id=root.name),
        )
        print(json.dumps([{"id": hit.record.id, "score": hit.score} for hit in hits]))
        return 0
    if command == "show":
        record = read_memory(root, args.memory_id)
        print(json.dumps(record.to_json_dict(), indent=2))
        return 0
    if command == "candidates":
        records = [
            record
            for record in load_project_memories(root)
            if record.status == MemoryStatus.CANDIDATE
        ]
        print(json.dumps([record.to_json_dict() for record in records], indent=2))
        return 0
    if command == "verify":
        record = verify_memory(root, args.memory_id, current_commit=args.commit)
        print(json.dumps(record.to_json_dict(), indent=2))
        return 0
    if command == "doctor":
        report = memory_doctor(root)
        print(
            json.dumps(
                {
                    "gate": report.gate,
                    "project_records": report.project_records,
                    "portfolio_records": report.portfolio_records,
                    "stale_records": report.stale_records,
                    "findings": [
                        {
                            "code": item.code,
                            "severity": item.severity,
                            "memory_id": item.memory_id,
                            "path": item.path,
                            "message": item.message,
                        }
                        for item in report.findings
                    ],
                },
                indent=2,
            )
        )
        return 0 if report.gate == "PASS" else 1
    if command == "init-project":
        path = init_project_memory(root)
        print(str(path))
        return 0
    if command == "init-vault":
        path = init_portfolio_vault(args.path)
        print(str(path))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
