from collections.abc import Callable

from nexus_harness.state import StageStatus, TaskState


def _is_mutable(state: TaskState) -> bool:
    return state.intent != "inspect"


def check_completion(
    state: TaskState,
    completion_check: Callable[[TaskState], bool] | None = None,
) -> None:
    """Stub completion gate. Task 7 replaces this with completion.py."""
    if completion_check is not None:
        if completion_check(state) is False:
            raise ValueError("completion gate not satisfied")
        return
    if not state.acceptance or any(item.status != "PASS" for item in state.acceptance):
        raise ValueError("completion gate not satisfied")


def advance_stage(
    state: TaskState,
    target_stage: int,
    completion_check: Callable[[TaskState], bool] | None = None,
) -> TaskState:
    if target_stage != state.stage + 1 or target_stage < 0 or target_stage > 9:
        raise ValueError(
            f"illegal transition from stage {state.stage} to {target_stage}"
        )
    if target_stage == 5 and _is_mutable(state) and not state.acceptance:
        raise ValueError("cannot enter implement without acceptance")
    if target_stage == 8:
        check_completion(state, completion_check)
    state.stage_status[str(state.stage)] = StageStatus.PASS
    state.stage = target_stage
    return state
