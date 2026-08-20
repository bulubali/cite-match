"""
CiteMatch v2 状态机 — 工作流阶段控制

状态转换规则:
  IDLE → LOADING_BIB → PARSING_BIB → LOADING_DRAFT → PARSING_AST
  → SCANNING_CITATIONS → MATCHING → INJECTING → VERIFYING
  → [SYNCING] → DONE

任何阶段发生致命错误 → ERROR
"""
from enum import Enum
from typing import Optional, Callable
from cm_types import WorkflowPhase, PipelineReport


class TransitionError(Exception):
    """非法状态转换异常"""
    pass


class PhaseGuard:
    """阶段守卫 — 确保状态转换合法性"""

    _transitions: dict[WorkflowPhase, set[WorkflowPhase]] = {
        WorkflowPhase.IDLE:              {WorkflowPhase.LOADING_BIB, WorkflowPhase.ERROR},
        WorkflowPhase.LOADING_BIB:       {WorkflowPhase.PARSING_BIB, WorkflowPhase.ERROR},
        WorkflowPhase.PARSING_BIB:       {WorkflowPhase.LOADING_DRAFT, WorkflowPhase.ERROR},
        WorkflowPhase.LOADING_DRAFT:     {WorkflowPhase.PARSING_AST, WorkflowPhase.ERROR},
        WorkflowPhase.PARSING_AST:       {WorkflowPhase.SCANNING_CITATIONS, WorkflowPhase.ERROR},
        WorkflowPhase.SCANNING_CITATIONS:{WorkflowPhase.MATCHING, WorkflowPhase.ERROR},
        WorkflowPhase.MATCHING:          {WorkflowPhase.INJECTING, WorkflowPhase.ERROR},
        WorkflowPhase.INJECTING:         {WorkflowPhase.VERIFYING, WorkflowPhase.ERROR},
        WorkflowPhase.VERIFYING:         {WorkflowPhase.SYNCING, WorkflowPhase.DONE, WorkflowPhase.ERROR},
        WorkflowPhase.SYNCING:           {WorkflowPhase.DONE, WorkflowPhase.ERROR},
        WorkflowPhase.DONE:              set(),   # 终态
        WorkflowPhase.ERROR:             {WorkflowPhase.IDLE},  # 只能重置
    }

    @classmethod
    def can_transition(cls, from_phase: WorkflowPhase, to_phase: WorkflowPhase) -> bool:
        return to_phase in cls._transitions.get(from_phase, set())

    @classmethod
    def validate(cls, from_phase: WorkflowPhase, to_phase: WorkflowPhase) -> None:
        if not cls.can_transition(from_phase, to_phase):
            raise TransitionError(
                f"Illegal transition: {from_phase.name} → {to_phase.name}"
            )


class CiteMatchStateMachine:
    """CiteMatch 工作流状态机"""

    def __init__(self):
        self._phase: WorkflowPhase = WorkflowPhase.IDLE
        self._history: list[tuple[WorkflowPhase, str]] = []  # (phase, note)
        self._on_phase_change: Optional[Callable] = None
        self._abort_flag: bool = False

    # ---- Properties ----

    @property
    def phase(self) -> WorkflowPhase:
        return self._phase

    @property
    def is_done(self) -> bool:
        return self._phase == WorkflowPhase.DONE

    @property
    def is_error(self) -> bool:
        return self._phase == WorkflowPhase.ERROR

    @property
    def is_running(self) -> bool:
        return self._phase not in (WorkflowPhase.IDLE, WorkflowPhase.DONE, WorkflowPhase.ERROR)

    # ---- Phase transitions ----

    def transition_to(self, target: WorkflowPhase, note: str = "") -> PipelineReport:
        """执行状态转换，返回当前阶段报告"""
        if self._abort_flag and target != WorkflowPhase.ERROR:
            target = WorkflowPhase.ERROR
            note = "Aborted by user"

        PhaseGuard.validate(self._phase, target)
        old = self._phase
        self._phase = target
        self._history.append((target, note))

        if self._on_phase_change:
            self._on_phase_change(target)

        return PipelineReport(
            phase=target,
            success=target != WorkflowPhase.ERROR,
            message=f"{old.name} → {target.name}" + (f": {note}" if note else ""),
        )

    def abort(self, reason: str = "User aborted"):
        """中止工作流"""
        self._abort_flag = True
        return self.transition_to(WorkflowPhase.ERROR, reason)

    def reset(self):
        """重置状态机到 IDLE"""
        self._phase = WorkflowPhase.IDLE
        self._history.clear()
        self._abort_flag = False

    def on_phase_change(self, callback: Callable):
        """注册阶段变更回调"""
        self._on_phase_change = callback

    def history_report(self) -> str:
        """生成状态历史报告"""
        lines = ["State Machine History:"]
        for i, (phase, note) in enumerate(self._history, 1):
            note_str = f" — {note}" if note else ""
            lines.append(f"  {i}. {phase.name}{note_str}")
        return "\n".join(lines)
