# Nexus Harness v4 — Canonical Core & Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the canonical v4 source tree, inventory and safely consolidate the exported v3 harness without touching the original archive.

**Architecture:** Build a dependency-light Python 3.11+ core around TOML/JSON, move canonical policy and skill sources into one tree, record semantic migration decisions, and replace the blocked sync model with deterministic one-way rendering.

**Tech Stack:** Python 3.11+ standard library, Markdown, TOML, JSON, Git

**Spec:** `docs/superpowers/specs/2026-08-25-nexus-harness-v4-final-design.md`

## Global Constraints

- Python runtime floor is 3.11 so TOML is parsed with the standard-library `tomllib` module.
- Canonical machine configuration uses TOML/JSON; no YAML parser is introduced into the harness runtime.
- The original `nexus-harness-export-20260825-094238.tar.gz` is immutable; all destructive cleanup occurs only in a v4 working copy.
- No project-specific IP, SSH target, absolute project path, client secret or model name belongs in `core/constitution.md`.
- Generated `dist/` content is never edited by hand; drift is a validation failure.
- Tests use Python standard-library `unittest` unless a target project already has its own test runner.
- Every implementation task is performed test-first where behavior can be isolated.

---

## File Structure

- `src/nexus_harness/inventory.py` — content/hash inventory
- `src/nexus_harness/skills.py` — skill discovery and duplicate groups
- `src/nexus_harness/migrate.py` — dry-run-first cleanup
- `src/nexus_harness/adapters.py` — pure generated-output registry
- `src/nexus_harness/lockfile.py` — canonical/generated content hashes
- `src/nexus_harness/validate.py` — repository invariants
- `core/` — canonical governance source
- `skills/` — canonical Nexus skills
- `upstream/` — locked third-party sources
- `docs/migration/` — before/after evidence

---

### Task 1: Freeze v3 inventory and regression baseline

**Files:**
- Create: `tests/test_inventory.py`
- Create: `src/nexus_harness/inventory.py`
- Create: `docs/migration/v3-baseline.json`

**Interfaces:**
- Consumes: Exported v3 tree mounted as the migration source.
- Produces: `InventoryReport` and a reproducible JSON baseline used by later cleanup and release checks.

- [ ] **Step 1: Write the failing inventory test**

Create `tests/test_inventory.py`:

```python
import tempfile
import unittest
from pathlib import Path

from nexus_harness.inventory import scan_tree

class InventoryTests(unittest.TestCase):
    def test_scan_ignores_appledouble_and_counts_hash_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_text("same", encoding="utf-8")
            (root / "b").write_text("same", encoding="utf-8")
            (root / "._a").write_text("metadata", encoding="utf-8")

            report = scan_tree(root)

            self.assertEqual(report.file_count, 2)
            self.assertEqual(report.duplicate_file_count, 1)
            self.assertEqual(report.appledouble_count, 1)
```

- [ ] **Step 2: Run the inventory test and confirm RED**

Run: `python3 -m unittest tests.test_inventory -v`

Expected: `ModuleNotFoundError` for `nexus_harness.inventory`.

- [ ] **Step 3: Implement deterministic tree scanning**

Create `src/nexus_harness/inventory.py` with:

```python
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

@dataclass(frozen=True)
class InventoryReport:
    file_count: int
    duplicate_file_count: int
    appledouble_count: int
    total_bytes: int
    redundant_bytes: int

def scan_tree(root: Path) -> InventoryReport:
    hashes: dict[str, list[tuple[Path, int]]] = {}
    files = 0
    appledouble = 0
    total_bytes = 0

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name.startswith("._"):
            appledouble += 1
            continue
        data = path.read_bytes()
        size = len(data)
        digest = sha256(data).hexdigest()
        hashes.setdefault(digest, []).append((path, size))
        files += 1
        total_bytes += size

    duplicate_count = 0
    redundant_bytes = 0
    for group in hashes.values():
        if len(group) > 1:
            duplicate_count += len(group) - 1
            redundant_bytes += sum(size for _, size in group[1:])

    return InventoryReport(files, duplicate_count, appledouble, total_bytes, redundant_bytes)
```

- [ ] **Step 4: Run the inventory test and confirm GREEN**

Run: `PYTHONPATH=src python3 -m unittest tests.test_inventory -v`

Expected: PASS.

- [ ] **Step 5: Generate the v3 baseline artifact**

Run the inventory scanner against the extracted export and serialize its result to `docs/migration/v3-baseline.json`. Record the source archive SHA-256 in the same JSON so later migration reports prove which export was used.

Implementation contract:

```text
Generate the v3 baseline artifact
Run the inventory scanner against the extracted export and serialize its result to `docs/migration/v3-baseline.json`. Record the source archive SHA-256 in the same JSON so later migration reports prove which export was used.
```


- [ ] **Step 6: Commit the baseline scanner**

Run: `git add src/nexus_harness/inventory.py tests/test_inventory.py docs/migration/v3-baseline.json && git commit -m "chore: freeze v3 harness inventory"`.

---

### Task 2: Create canonical v4 repository skeleton and constitution

**Files:**
- Create: `core/constitution.md`
- Create: `core/policies/*.toml`
- Create: `core/workflow/*.toml`
- Create: `core/graph/*.toml`
- Create: `core/quality/*.toml`
- Create: `core/security/*.toml`
- Create: `core/project/*.toml`
- Create: `profiles/default.toml`
- Create: `src/nexus_harness/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: Final consolidated design and Python 3.11+.
- Produces: Canonical config loader and minimal constitution with no runtime/project leakage.

- [ ] **Step 1: Write the failing canonical-config test**

Create `tests/test_config.py`:

```python
import tempfile
import unittest
from pathlib import Path

from nexus_harness.config import load_toml

class ConfigTests(unittest.TestCase):
    def test_load_toml_returns_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.toml"
            path.write_text('[workflow]\nmandatory = true\n', encoding="utf-8")
            data = load_toml(path)
            self.assertTrue(data["workflow"]["mandatory"])
```

- [ ] **Step 2: Run the config test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_config -v`

Expected: import failure for `nexus_harness.config`.

- [ ] **Step 3: Implement standard-library TOML loading**

Create `src/nexus_harness/config.py`:

```python
from pathlib import Path
import tomllib

def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)
```

- [ ] **Step 4: Create the canonical constitution and policies**

Create `core/constitution.md` containing only the invariant workflow rules:

```text
NEXUS WORKFLOW IS MANDATORY.
For mutable engineering work:
1. classify before implementation;
2. create or link required GitHub work tracking;
3. define acceptance criteria with initial FAIL status;
4. execute lifecycle stages in order while allowing DAG parallelism inside a stage;
5. promote acceptance criteria only from fresh recorded evidence;
6. do not complete while completion gate fails;
7. do not ship without request or explicit approval;
8. never weaken quality/security policy or baseline to make a change pass.
```

Create TOML policy files matching the final spec. Keep values generic and project-neutral.

- [ ] **Step 5: Run config and policy smoke tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_config -v` and `python3 -c 'import tomllib, pathlib; [tomllib.load(p.open("rb")) for p in pathlib.Path("core").rglob("*.toml")]'`.

Expected: both commands exit 0.

- [ ] **Step 6: Commit canonical skeleton**

Run: `git add core profiles src/nexus_harness/config.py tests/test_config.py && git commit -m "feat: add canonical nexus core"`.

---

### Task 3: Implement skill inventory, exact-duplicate detection and semantic migration ledger

**Files:**
- Create: `src/nexus_harness/skills.py`
- Create: `tests/test_skills.py`
- Create: `docs/migration/skill-ledger.json`

**Interfaces:**
- Consumes: v3 inventory and the four current skill roots.
- Produces: Exact duplicate groups plus a durable migration decision record for every skill entrypoint.

- [ ] **Step 1: Write failing skill-group tests**

Create `tests/test_skills.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.skills import discover_skill_files, group_exact_duplicates

class SkillTests(unittest.TestCase):
    def test_groups_identical_skill_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("a/foo/SKILL.md", "b/foo/SKILL.md", "c/bar/SKILL.md"):
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("same" if "foo" in rel else "other", encoding="utf-8")
            files = discover_skill_files(root)
            groups = group_exact_duplicates(files)
            self.assertEqual(sorted(len(group) for group in groups), [2])
```

- [ ] **Step 2: Run the skill test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_skills -v`

Expected: import failure.

- [ ] **Step 3: Implement discovery and exact-hash grouping**

Create `src/nexus_harness/skills.py` with:

```python
from collections import defaultdict
from hashlib import sha256
from pathlib import Path

def discover_skill_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("SKILL.md")
        if p.is_file() and not any(part.startswith("._") for part in p.parts)
    )

def group_exact_duplicates(files: list[Path]) -> list[list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        groups[sha256(path.read_bytes()).hexdigest()].append(path)
    return [group for group in groups.values() if len(group) > 1]
```

- [ ] **Step 4: Generate `skill-ledger.json` from the real export**

For every discovered `SKILL.md`, write one ledger object:

```json
{
  "name": "nexus-frontend",
  "sources": ["agents-skills/nexus-frontend/SKILL.md", "claude/skills/nexus-frontend/SKILL.md"],
  "relationship": "exact_duplicate",
  "decision": "canonicalize",
  "target": "skills/nexus-frontend/SKILL.md"
}
```

For divergent same-name groups use `relationship: "divergent"` and record the migration decision from the approved spec instead of deleting either source automatically.

- [ ] **Step 5: Run skill tests and ledger validation**

Run: `PYTHONPATH=src python3 -m unittest tests.test_skills -v` and a JSON parse of `docs/migration/skill-ledger.json`.

Expected: PASS.

- [ ] **Step 6: Commit skill migration ledger**

Run: `git add src/nexus_harness/skills.py tests/test_skills.py docs/migration/skill-ledger.json && git commit -m "chore: map skill consolidation"`.

---

### Task 4: Create canonical skills and upstream lock

**Files:**
- Create: `skills/nexus-workflow/SKILL.md`
- Create: `skills/nexus-quality/SKILL.md`
- Create: `skills/nexus-verify/SKILL.md`
- Create: `skills/nexus-handoff/SKILL.md`
- Create: `skills/nexus-ship/SKILL.md`
- Create: `skills/nexus-frontend/SKILL.md`
- Create: `skills/accessibility/SKILL.md`
- Create: `upstream/vendor-lock.json`
- Test: `tests/test_skill_contracts.py`

**Interfaces:**
- Consumes: `docs/migration/skill-ledger.json` and approved skill hierarchy.
- Produces: Seven canonical Nexus entry skills and a versioned upstream-source lock.

- [ ] **Step 1: Write failing canonical-skill contract test**

Create `tests/test_skill_contracts.py`:

```python
import unittest
from pathlib import Path

REQUIRED = {
    "nexus-workflow", "nexus-quality", "nexus-verify",
    "nexus-handoff", "nexus-ship", "nexus-frontend", "accessibility"
}

class SkillContractTests(unittest.TestCase):
    def test_canonical_skills_exist_once(self):
        root = Path("skills")
        names = {p.parent.name for p in root.glob("*/SKILL.md")}
        self.assertEqual(names, REQUIRED)
```

- [ ] **Step 2: Run contract test and confirm RED**

Run: `python3 -m unittest tests.test_skill_contracts -v`

Expected: missing canonical skills.

- [ ] **Step 3: Create the lifecycle skills from approved semantics**

Create the five lifecycle skills with explicit boundaries: `nexus-workflow` owns stage routing; `nexus-quality` owns profiles/ratchet/review selection; `nexus-verify` owns deterministic evidence; `nexus-handoff` serializes task continuation; `nexus-ship` owns commit/push/PR/merge/deploy gates. Do not duplicate TDD/debugging/worktree instructions from Superpowers.

Implementation contract:

```text
Create the lifecycle skills from approved semantics
Create the five lifecycle skills with explicit boundaries: `nexus-workflow` owns stage routing; `nexus-quality` owns profiles/ratchet/review selection; `nexus-verify` owns deterministic evidence; `nexus-handoff` serializes task continuation; `nexus-ship` owns commit/push/PR/merge/deploy gates. Do not duplicate TDD/debugging/worktree instructions from Superpowers.
```


- [ ] **Step 4: Create frontend and accessibility canonical skills**

Build `nexus-frontend` as a mode router (`implement`, `redesign`, `audit`, `explain`, `visual-validate`, `design-system`, `polish`) and merge the unique accessibility guidance into `accessibility`. Preserve Motion Principles and other approved specialist sources as routed references, not copied lifecycle text.

Implementation contract:

```text
Create frontend and accessibility canonical skills
Build `nexus-frontend` as a mode router (`implement`, `redesign`, `audit`, `explain`, `visual-validate`, `design-system`, `polish`) and merge the unique accessibility guidance into `accessibility`. Preserve Motion Principles and other approved specialist sources as routed references, not copied lifecycle text.
```


- [ ] **Step 5: Write upstream lock entries**

Create `upstream/vendor-lock.json` with one object per retained upstream source:

```json
{
  "schema_version": 1,
  "sources": [
    {
      "id": "design-motion-principles",
      "kind": "git",
      "repository": "kylezantos/design-motion-principles",
      "revision_kind": "content_sha256",
      "revision": "sha256 of the imported upstream directory calculated by the import command",
      "canonical_path": "upstream/design-motion-principles"
    }
  ]
}
```

The import command calculates and writes the real SHA-256 value in the same step that imports the upstream source. The committed lock must contain the computed value, not descriptive text.

- [ ] **Step 6: Run canonical skill tests**

Run: `python3 -m unittest tests.test_skill_contracts -v`.

Expected: PASS.

- [ ] **Step 7: Commit canonical skills**

Run: `git add skills upstream tests/test_skill_contracts.py && git commit -m "feat: canonicalize nexus skills"`.

---

### Task 5: Implement one-way compiler and harness lock

**Files:**
- Create: `src/nexus_harness/adapters.py`
- Create: `src/nexus_harness/runtime_claude.py`
- Create: `src/nexus_harness/runtime_cursor.py`
- Create: `src/nexus_harness/runtime_codex.py`
- Create: `src/nexus_harness/lockfile.py`
- Create: `tests/test_compile.py`
- Create: `harness.lock`
- Create: `dist/.gitkeep`

**Interfaces:**
- Consumes: Canonical core, skills and upstream lock.
- Produces: Deterministic `dist/` generation and content hashes used for drift detection.

- [ ] **Step 1: Write failing deterministic-compile test**

Create `tests/test_compile.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.adapters import render_all

class CompileTests(unittest.TestCase):
    def test_second_render_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = render_all(root)
            second = render_all(root)
            self.assertEqual(first, second)
```

- [ ] **Step 2: Run compile test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_compile -v`

Expected: import failure.

- [ ] **Step 3: Implement renderer registry with pure outputs**

Create `src/nexus_harness/adapters.py` with a pure renderer interface:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class RenderedFile:
    relative_path: str
    content: bytes

def render_all(root: Path) -> tuple[RenderedFile, ...]:
    from nexus_harness.runtime_claude import render as render_claude
    from nexus_harness.runtime_cursor import render as render_cursor
    from nexus_harness.runtime_codex import render as render_codex
    files = [*render_claude(root), *render_cursor(root), *render_codex(root)]
    return tuple(sorted(files, key=lambda item: item.relative_path))
```

Create temporary runtime modules that return an empty tuple until Plan 3 replaces them with real adapters; this task establishes only the deterministic compiler contract.

- [ ] **Step 4: Implement lockfile hashing**

Create `src/nexus_harness/lockfile.py` to SHA-256 canonical files, upstream lock and generated outputs. Serialize sorted JSON with `schema_version`, `canonical_hashes`, `generated_hashes` and `adapter_versions`.

Implementation contract:

```text
Implement lockfile hashing
Create `src/nexus_harness/lockfile.py` to SHA-256 canonical files, upstream lock and generated outputs. Serialize sorted JSON with `schema_version`, `canonical_hashes`, `generated_hashes` and `adapter_versions`.
```


- [ ] **Step 5: Run deterministic compile tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_compile -v` twice.

Expected: PASS both times and no changing generated hash.

- [ ] **Step 6: Commit compiler foundation**

Run: `git add src/nexus_harness/adapters.py src/nexus_harness/lockfile.py tests/test_compile.py harness.lock dist && git commit -m "feat: add one-way harness compiler"`.

---

### Task 6: Clean v3-only artifacts in the v4 working copy

**Files:**
- Create: `src/nexus_harness/migrate.py`
- Create: `tests/test_migrate.py`
- Create: `docs/migration/cleanup-report.json`

**Interfaces:**
- Consumes: Inventory report, skill ledger and canonical destinations.
- Produces: A dry-run-first cleanup engine that never modifies the source archive.

- [ ] **Step 1: Write failing dry-run safety test**

Create `tests/test_migrate.py`:

```python
import tempfile
import unittest
from pathlib import Path
from nexus_harness.migrate import cleanup_plan

class MigrationTests(unittest.TestCase):
    def test_cleanup_plan_marks_appledouble_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "._junk"
            target.write_text("x", encoding="utf-8")
            plan = cleanup_plan(root)
            self.assertEqual(plan[0]["action"], "delete")
            self.assertTrue(target.exists())
```

- [ ] **Step 2: Run migration test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_migrate -v`

Expected: import failure.

- [ ] **Step 3: Implement cleanup planning**

Implement `cleanup_plan(root)` to mark AppleDouble files, `.bak`, stale sync logs/circuit-breaker files and exact duplicate generated skill copies. The function returns actions only; `apply_cleanup(plan, root)` must reject paths outside the supplied root.

Implementation contract:

```text
Implement cleanup planning
Implement `cleanup_plan(root)` to mark AppleDouble files, `.bak`, stale sync logs/circuit-breaker files and exact duplicate generated skill copies. The function returns actions only; `apply_cleanup(plan, root)` must reject paths outside the supplied root.
```


- [ ] **Step 4: Generate and inspect the cleanup report**

Run migration in `--dry-run` mode against the v4 working copy and write `docs/migration/cleanup-report.json`. Confirm the report contains no path from the immutable source archive and no canonical target under `core/`, `skills/`, `upstream/`, `src/` or `tests/`.

Implementation contract:

```text
Generate and inspect the cleanup report
Run migration in `--dry-run` mode against the v4 working copy and write `docs/migration/cleanup-report.json`. Confirm the report contains no path from the immutable source archive and no canonical target under `core/`, `skills/`, `upstream/`, `src/` or `tests/`.
```


- [ ] **Step 5: Apply cleanup only to the isolated v4 working copy**

Execute the generated plan with the explicit working-copy root. Re-run inventory and store before/after counts in the cleanup report.

- [ ] **Step 6: Run migration safety tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_migrate -v`.

Expected: PASS.

- [ ] **Step 7: Commit cleanup engine and report**

Run: `git add src/nexus_harness/migrate.py tests/test_migrate.py docs/migration/cleanup-report.json && git commit -m "chore: clean legacy harness artifacts"`.

---

### Task 7: Add canonical validation entrypoint

**Files:**
- Create: `src/nexus_harness/validate.py`
- Create: `tests/test_validate.py`
- Create: `scripts/validate`

**Interfaces:**
- Consumes: Canonical core, skills, compiler lock and migration reports.
- Produces: A single validation command used by all later plans and CI.

- [ ] **Step 1: Write failing validator test**

Create `tests/test_validate.py`:

```python
import unittest
from pathlib import Path
from nexus_harness.validate import validate_repository

class ValidateTests(unittest.TestCase):
    def test_repository_has_no_appledouble_or_generated_drift(self):
        result = validate_repository(Path("."))
        self.assertEqual(result.errors, ())
```

- [ ] **Step 2: Run validator test and confirm RED**

Run: `PYTHONPATH=src python3 -m unittest tests.test_validate -v`

Expected: import failure.

- [ ] **Step 3: Implement validator checks**

Implement checks for parseable TOML/JSON, canonical skill uniqueness, absence of AppleDouble/`.bak`, no absolute client/project paths in global config, no IP/SSH production target in core, no model names in constitution, upstream lock completeness and generated hash drift.

Implementation contract:

```text
Implement validator checks
Implement checks for parseable TOML/JSON, canonical skill uniqueness, absence of AppleDouble/`.bak`, no absolute client/project paths in global config, no IP/SSH production target in core, no model names in constitution, upstream lock completeness and generated hash drift.
```


- [ ] **Step 4: Create shell entrypoint**

Create executable `scripts/validate`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$ROOT/src" exec python3 -m nexus_harness.validate "$ROOT"
```

- [ ] **Step 5: Run full Plan 1 verification**

Run: `python3 -m unittest discover -s tests -p 'test_*.py' -v` and `scripts/validate`.

Expected: PASS and exit 0.

- [ ] **Step 6: Commit Plan 1 completion**

Run: `git add src/nexus_harness/validate.py tests/test_validate.py scripts/validate && git commit -m "feat: validate canonical harness"`.

---
