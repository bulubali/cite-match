"""
CiteMatch v2.1 Phase Gate — Agent 工作流阶段状态控制

Task 1: 确保 Claude Skill 层不能跳过 Phase 确认步骤。

Gate 类型:
- IF_CONFIRM       — Phase 1: IF 门槛确认
- SUMMARY_CONFIRM  — Phase 2: References_Summary 确认
- TABLE_CONFIRM    — Phase 3: 表格注入确认
- INJECTION_CONFIRM — Phase 3→5: 注入执行确认
"""
import json
import os
from datetime import datetime
from typing import Optional
from cm_types import WorkflowBlockedError

# Gate type → Phase number mapping
GATE_PHASE_MAP = {
    "IF_CONFIRM": 1,
    "SUMMARY_CONFIRM": 2,
    "TABLE_CONFIRM": 3,
    "IF_UNKNOWN_REVIEW": 3,
    "FLOATING_CONFIRM": 4,
    "INJECTION_CONFIRM": 5,
    "EXPORT_CONFIRM": 6,
}


class WorkflowGate:
    """工作流门控 — 强制执行 Phase 确认步骤

    用法:
        gate = WorkflowGate(state_file="workflow_state.json")

        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        # ... 等待用户确认 ...
        gate.approve("IF_CONFIRM")
        gate.block_if_unapproved(2)  # 未通过则 raise
        gate.start_phase(2)
    """

    def __init__(self, state_file: str = "workflow_state.json"):
        self._state_file = state_file
        self._state: dict = {
            "phase": 0,
            "waiting_confirmation": False,
            "confirmation_type": "",
            "approved": False,
            "history": [],
            "context": {},
        }
        self._load()

    # ---- Public API ----

    def start_phase(self, phase: int) -> None:
        """进入新 Phase"""
        # 检查上一个 Phase 的确认是否完成
        if self._state["waiting_confirmation"] and not self._state["approved"]:
            raise WorkflowBlockedError(
                f"PHASE_GATE",
                f"Cannot start Phase {phase}: "
                f"Phase {self._state['phase']} still waiting for "
                f"'{self._state['confirmation_type']}' confirmation"
            )

        self._state["phase"] = phase
        self._state["waiting_confirmation"] = False
        self._state["confirmation_type"] = ""
        self._state["approved"] = False
        self._state["history"].append({
            "action": "start_phase",
            "phase": phase,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def require_confirmation(self, confirmation_type: str) -> None:
        """标记当前 Phase 需要用户确认"""
        if confirmation_type not in GATE_PHASE_MAP:
            raise ValueError(
                f"Unknown confirmation type: '{confirmation_type}'. "
                f"Must be one of: {list(GATE_PHASE_MAP.keys())}"
            )

        self._state["waiting_confirmation"] = True
        self._state["confirmation_type"] = confirmation_type
        self._state["approved"] = False
        self._state["history"].append({
            "action": "require_confirmation",
            "type": confirmation_type,
            "phase": self._state["phase"],
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def approve(self, confirmation_type: Optional[str] = None) -> None:
        """批准当前确认"""
        if confirmation_type and confirmation_type != self._state["confirmation_type"]:
            raise WorkflowBlockedError(
                "PHASE_GATE",
                f"Confirmation type mismatch: expected "
                f"'{self._state['confirmation_type']}', got '{confirmation_type}'"
            )

        if not self._state["waiting_confirmation"]:
            raise WorkflowBlockedError(
                "PHASE_GATE",
                "No pending confirmation to approve"
            )

        self._state["approved"] = True
        self._state["history"].append({
            "action": "approve",
            "type": self._state["confirmation_type"],
            "phase": self._state["phase"],
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def deny(self, reason: str = "") -> None:
        """拒绝当前确认"""
        self._state["approved"] = False
        self._state["history"].append({
            "action": "deny",
            "type": self._state["confirmation_type"],
            "reason": reason,
            "phase": self._state["phase"],
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def block_if_unapproved(self, target_phase: int) -> None:
        """如果当前确认未通过，阻止进入目标 Phase

        Raises:
            WorkflowBlockedError: 如果 waiting_confirmation=True 且 approved=False
        """
        if self._state["waiting_confirmation"] and not self._state["approved"]:
            raise WorkflowBlockedError(
                f"PHASE_GATE",
                f"Blocked: Phase {self._state['phase']} requires "
                f"'{self._state['confirmation_type']}' confirmation before "
                f"entering Phase {target_phase}. "
                f"Current status: approved={self._state['approved']}"
            )

    def block_all(self) -> None:
        """阻断所有未确认的 Phase — 用于安全关机"""
        if self._state["waiting_confirmation"] and not self._state["approved"]:
            raise WorkflowBlockedError(
                f"PHASE_GATE",
                f"Global block: Phase {self._state['phase']} has unapproved "
                f"'{self._state['confirmation_type']}'. All operations halted."
            )

    # ---- Queries ----

    @property
    def phase(self) -> int:
        return self._state["phase"]

    @property
    def is_waiting(self) -> bool:
        return self._state["waiting_confirmation"]

    @property
    def is_approved(self) -> bool:
        return self._state["approved"]

    @property
    def confirmation_type(self) -> str:
        return self._state["confirmation_type"]

    def can_proceed_to(self, target_phase: int) -> bool:
        """检查是否可以进入目标 Phase"""
        if self._state["waiting_confirmation"] and not self._state["approved"]:
            return False
        return True

    # ---- State Persistence ----

    def get_state(self) -> dict:
        """获取当前状态（只读副本）"""
        return json.loads(json.dumps(self._state, ensure_ascii=False))

    def set_context(self, context: dict) -> None:
        """Persist JSON-compatible workflow continuation data."""
        try:
            serializable = json.loads(json.dumps(context, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Workflow context must be JSON-compatible: {exc}")
        self._state["context"] = serializable
        self._save()

    def update_context(self, **updates) -> None:
        """Update and persist selected JSON-compatible context fields."""
        context = dict(self._state.get("context", {}))
        context.update(updates)
        self.set_context(context)

    @property
    def context(self) -> dict:
        return json.loads(json.dumps(
            self._state.get("context", {}), ensure_ascii=False
        ))

    def get_history(self) -> list[dict]:
        return list(self._state["history"])

    def reset(self) -> None:
        """重置 Gate 状态"""
        self._state = {
            "phase": 0,
            "waiting_confirmation": False,
            "confirmation_type": "",
            "approved": False,
            "history": [],
            "context": {},
        }
        self._save()

    def _save(self) -> None:
        """持久化到 workflow_state.json"""
        try:
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except OSError:
            pass  # 文件写入失败不阻断流程

    def _load(self) -> None:
        """从 workflow_state.json 加载状态"""
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 验证必要字段
                for key in ("phase", "waiting_confirmation", "confirmation_type",
                           "approved", "history", "context"):
                    if key in loaded:
                        self._state[key] = loaded[key]
            except (json.JSONDecodeError, OSError):
                pass  # 损坏的状态文件 → 使用默认值
