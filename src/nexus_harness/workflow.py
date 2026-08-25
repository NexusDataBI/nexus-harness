from nexus_harness.completion import evaluate_completion
from nexus_harness.state import StageStatus, TaskState


def _is_mutable(state: TaskState) -> bool:
    return state.intent != "inspect"


def check_completion(state: TaskState) -> None:
    """Stage 8 is the done-gate: evaluate_completion must be READY_TO_SHIP."""
    result = evaluate_completion(state)
    if result.status != "READY_TO_SHIP":
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
