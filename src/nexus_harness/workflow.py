from nexus_harness.state import StageStatus, TaskState


def _is_mutable(state: TaskState) -> bool:
    return state.intent != "inspect"


def check_completion(state: TaskState) -> None:
    """Stub completion gate. Task 7 replaces this with completion.py."""
    if not state.acceptance or any(item.status != "PASS" for item in state.acceptance):
        raise ValueError("completion gate not satisfied")


def advance_stage(state: TaskState, target_stage: int) -> TaskState:
    if target_stage != state.stage + 1 or target_stage < 0 or target_stage > 9:
        raise ValueError(
            f"illegal transition from stage {state.stage} to {target_stage}"
        )
    if target_stage == 5 and _is_mutable(state) and not state.acceptance:
        raise ValueError("cannot enter implement without acceptance")
    if target_stage == 8:
        check_completion(state)
    state.stage_status[str(state.stage)] = StageStatus.PASS
    state.stage = target_stage
    return state
