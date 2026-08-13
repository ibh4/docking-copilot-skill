"""工作流状态机：JobState 与合法转移表。"""

from __future__ import annotations

from app.schemas import JobState

#: 运行中状态 → 后继状态集合（SUCCESS/FAILED/CANCELLED 为终态）
TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.CREATED: {JobState.VALIDATING, JobState.FAILED, JobState.CANCELLED},
    JobState.VALIDATING: {
        JobState.PREPARING_LIGAND, JobState.PREPARING_RECEPTOR,
        JobState.FAILED, JobState.CANCELLED,
    },
    JobState.PREPARING_LIGAND: {
        JobState.PREPARING_RECEPTOR, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.PREPARING_RECEPTOR: {
        JobState.VALIDATING_BOX, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.VALIDATING_BOX: {
        JobState.DOCKING, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.DOCKING: {JobState.PARSING, JobState.FAILED, JobState.CANCELLED},
    JobState.PARSING: {JobState.ANALYZING, JobState.FAILED, JobState.CANCELLED},
    JobState.ANALYZING: {
        JobState.PACKAGING, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.PACKAGING: {
        JobState.SUCCESS, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.SUCCESS: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}

#: 各运行状态对应的进度百分比（job.json 展示用）
STATE_PROGRESS: dict[JobState, int] = {
    JobState.CREATED: 0,
    JobState.VALIDATING: 5,
    JobState.PREPARING_LIGAND: 15,
    JobState.PREPARING_RECEPTOR: 30,
    JobState.VALIDATING_BOX: 45,
    JobState.DOCKING: 55,
    JobState.PARSING: 75,
    JobState.ANALYZING: 85,
    JobState.PACKAGING: 95,
    JobState.SUCCESS: 100,
    JobState.FAILED: 100,
    JobState.CANCELLED: 100,
}


def can_transition(current: JobState, target: JobState) -> bool:
    return target in TRANSITIONS.get(current, set())


def assert_transition(current: JobState, target: JobState) -> None:
    if not can_transition(current, target):
        raise ValueError(
            f"illegal job state transition: {current.value} -> {target.value}"
        )
