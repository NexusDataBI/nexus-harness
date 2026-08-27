# Task 1 Report — Final Nexus CLI

## Status

DONE

## Implemented

- `src/nexus_harness/cli.py` — unique argparse tree. Delegates to existing modules; no duplicated business rules.
- `src/nexus_harness/__main__.py` — thin `python3 -m nexus_harness` entry that calls `cli.main` and re-exports the previous command helpers.
- `scripts/nexus` — `PYTHONPATH` preserved; execs `python3 -m nexus_harness.cli`.
- Existing surface kept: `ci affected`, `quality run`, `images build`, `frontend capture`.
- New surface: `validate`, `build` (`compile_harness`), `install` (`atomic_install`), `workflow advance`, `project show`, `incidents classify|render`.
- `doctor` / `evals` listed in `--help`. Running them exits 2 with `not available yet` (JSON `status=unavailable`). No fake PASS.
- `--json` emits `dumps_report` / `safe_serialize` on stdout only. Human text stays in non-JSON mode (or stderr for errors).
- `incidents` is local/policy/render only: `authorize_remote_mutation=False`. No GitHub Issues.
- `tests/test_cli.py` extended (existing CliAffected/CliQuality/CliImages kept). Frontend smoke test now reads `cli.py`.
- `harness.lock` refreshed via `write_lock` after the engine file was added.

No push. No real GitHub/PostHog. Tasks 2–3 (`doctor`/`evals` modules) not implemented.

## TDD evidence

### RED

Command:

```text
PYTHONPATH=src python3 -m unittest tests.test_cli -v
```

Observed (existing ci/quality/images still passed):

```text
test_help_lists_core_commands ... FAIL
AssertionError: 'validate' not found in 'usage: nexus [-h] {ci,quality,images,frontend} ...'

test_wrapper_execs_module ... FAIL
AssertionError: 'python3 -m nexus_harness.cli' not found in '... exec python3 -m nexus_harness ...'

test_doctor_exits_unavailable_without_fake_pass ... FAIL
AssertionError: Regex didn't match: 'not (yet )?available|not implemented'

test_install_copies_source_to_target ... FAIL  (exit 2)
test_project_show_by_id_json ... FAIL          (exit 2)
test_workflow_advance_writes_next_stage ... FAIL (exit 2)

FAILED (failures=7, errors=4)
Ran 14 tests in 0.086s
```

Existing `CliAffectedTests` / `CliQualityTests` / `CliImagesTests` stayed OK during RED.

### GREEN

Command:

```text
PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_frontend_cli -v
```

Observed:

```text
Ran 27 tests in 0.519s
OK
```

Full suite (permissions `all`):

```text
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
Ran 799 tests in 3.097s
OK
```

Lock refresh:

```text
PYTHONPATH=src python3 -c "from pathlib import Path; from nexus_harness.lockfile import write_lock; write_lock(Path('.'))"
```

## Files changed

| Path                            | Action                              |
| ------------------------------- | ----------------------------------- |
| `src/nexus_harness/cli.py`      | created                             |
| `src/nexus_harness/__main__.py` | thin delegate to `cli.main`         |
| `scripts/nexus`                 | exec `python3 -m nexus_harness.cli` |
| `tests/test_cli.py`             | extended; existing classes kept     |
| `tests/test_frontend_cli.py`    | parser smoke reads `cli.py`         |
| `harness.lock`                  | engine hashes refreshed             |

## Self-review

- argparse only. Validate/compile/install/workflow/project/incidents logic stays in modules.
- `--json` uses `dumps_report`; secret keys in incident input are not copied into stdout.
- `incidents render` always passes `authorize_remote_mutation=False`. Injected GitHub mock is never called.
- `doctor`/`evals` do not fake PASS.
- `python3 -m nexus_harness` and `scripts/nexus` share the same tree.

## Concerns

`doctor` and `evals` are reserved stubs until Tasks 2–3. `build` compiles the full harness (`compile_harness`); it is in `--help` and dispatches, but has no dedicated CLI test beyond the help listing. `python3 -m unittest` printed an unrelated `--dry-run` usage line during discover; suite still OK.
