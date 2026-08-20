"""
test_phase_gate.py — Task 1: Phase Gate 状态控制测试

验证:
1. WorkflowGate 基本操作: start_phase / require_confirmation / approve
2. block_if_unapproved 正确阻断
3. 未确认不能进入下一 Phase
4. workflow_state.json 持久化
5. 所有 Gate 类型 (IF_CONFIRM, SUMMARY_CONFIRM, TABLE_CONFIRM, INJECTION_CONFIRM)
"""
import sys
import os
import json
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import WorkflowBlockedError
from phase_gate import WorkflowGate, GATE_PHASE_MAP


@pytest.fixture
def gate(tmp_path):
    """创建使用临时文件的新 WorkflowGate"""
    state_file = str(tmp_path / "workflow_state.json")
    return WorkflowGate(state_file=state_file)


class TestWorkflowGateBasic:
    """WorkflowGate 基本操作"""

    def test_initial_state(self, gate):
        assert gate.phase == 0
        assert not gate.is_waiting
        assert not gate.is_approved

    def test_start_phase(self, gate):
        gate.start_phase(1)
        assert gate.phase == 1
        assert not gate.is_waiting

    def test_require_confirmation(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        assert gate.is_waiting
        assert not gate.is_approved
        assert gate.confirmation_type == "IF_CONFIRM"

    def test_approve(self, gate):
        gate.start_phase(2)
        gate.require_confirmation("SUMMARY_CONFIRM")
        gate.approve()
        assert gate.is_approved

    def test_approve_type_mismatch_raises(self, gate):
        gate.start_phase(2)
        gate.require_confirmation("SUMMARY_CONFIRM")
        with pytest.raises(WorkflowBlockedError):
            gate.approve("IF_CONFIRM")  # wrong type

    def test_approve_without_require_raises(self, gate):
        gate.start_phase(1)
        with pytest.raises(WorkflowBlockedError):
            gate.approve()

    def test_deny(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.deny("Not enough budget")
        assert not gate.is_approved


class TestBlockUnapproved:
    """阻断未确认的 Phase 转换"""

    def test_block_if_unapproved_raises(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        # 未 approve → 阻断进入 Phase 2
        with pytest.raises(WorkflowBlockedError) as exc:
            gate.block_if_unapproved(2)
        assert "IF_CONFIRM" in exc.value.reason
        assert "approved=False" in exc.value.reason

    def test_block_if_approved_passes(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.approve()
        # 已 approve → 不阻断
        gate.block_if_unapproved(2)  # Should not raise

    def test_block_all_raises_when_unapproved(self, gate):
        gate.start_phase(3)
        gate.require_confirmation("TABLE_CONFIRM")
        with pytest.raises(WorkflowBlockedError):
            gate.block_all()

    def test_start_phase_blocked_by_unapproved_previous(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        # 未确认 → 不能 start_phase(2)
        with pytest.raises(WorkflowBlockedError):
            gate.start_phase(2)

    def test_start_phase_allowed_after_approve(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.approve()
        # 已确认 → 可以进入 Phase 2
        gate.start_phase(2)
        assert gate.phase == 2


class TestAllGateTypes:
    """所有 Gate 类型"""

    def test_if_confirm(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.approve()
        assert gate.is_approved

    def test_summary_confirm(self, gate):
        gate.start_phase(2)
        gate.require_confirmation("SUMMARY_CONFIRM")
        gate.approve()
        assert gate.is_approved

    def test_table_confirm(self, gate):
        gate.start_phase(3)
        gate.require_confirmation("TABLE_CONFIRM")
        gate.approve()
        assert gate.is_approved

    def test_injection_confirm(self, gate):
        gate.start_phase(5)
        gate.require_confirmation("INJECTION_CONFIRM")
        gate.approve()
        assert gate.is_approved

    def test_unknown_confirmation_type_raises(self, gate):
        gate.start_phase(1)
        with pytest.raises(ValueError, match="Unknown confirmation type"):
            gate.require_confirmation("UNKNOWN_TYPE")

    def test_gate_phase_map_coverage(self):
        """GATE_PHASE_MAP 包含所有类型"""
        assert "IF_CONFIRM" in GATE_PHASE_MAP
        assert "SUMMARY_CONFIRM" in GATE_PHASE_MAP
        assert "TABLE_CONFIRM" in GATE_PHASE_MAP
        assert "INJECTION_CONFIRM" in GATE_PHASE_MAP
        assert GATE_PHASE_MAP["IF_CONFIRM"] == 1
        assert GATE_PHASE_MAP["SUMMARY_CONFIRM"] == 2
        assert GATE_PHASE_MAP["TABLE_CONFIRM"] == 3


class TestStatePersistence:
    """状态持久化"""

    def test_state_saved_to_file(self, gate, tmp_path):
        state_file = str(tmp_path / "workflow_state.json")
        gate2 = WorkflowGate(state_file=state_file)
        gate2.start_phase(1)
        gate2.require_confirmation("IF_CONFIRM")

        assert os.path.exists(state_file)
        with open(state_file) as f:
            saved = json.load(f)
        assert saved["phase"] == 1
        assert saved["confirmation_type"] == "IF_CONFIRM"

    def test_state_loaded_from_file(self, tmp_path):
        state_file = str(tmp_path / "workflow_state.json")
        with open(state_file, 'w') as f:
            json.dump({
                "phase": 2,
                "waiting_confirmation": True,
                "confirmation_type": "SUMMARY_CONFIRM",
                "approved": False,
                "history": [],
            }, f)

        gate = WorkflowGate(state_file=state_file)
        assert gate.phase == 2
        assert gate.is_waiting
        assert gate.confirmation_type == "SUMMARY_CONFIRM"

    def test_corrupted_state_file(self, tmp_path):
        state_file = str(tmp_path / "workflow_state.json")
        with open(state_file, 'w') as f:
            f.write("not json")

        gate = WorkflowGate(state_file=state_file)
        assert gate.phase == 0  # 使用默认值


class TestHistory:
    """操作历史"""

    def test_history_records_actions(self, gate):
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.approve()

        history = gate.get_history()
        assert len(history) == 3
        assert history[0]["action"] == "start_phase"
        assert history[1]["action"] == "require_confirmation"
        assert history[2]["action"] == "approve"


class TestWorkflowSimulation:
    """模拟完整工作流"""

    def test_full_workflow_phases_1_through_5(self, gate):
        # Phase 1: IF
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        gate.approve()

        # Phase 2: Summary
        gate.start_phase(2)
        gate.require_confirmation("SUMMARY_CONFIRM")
        gate.approve()

        # Phase 3: Table
        gate.start_phase(3)
        gate.require_confirmation("TABLE_CONFIRM")
        gate.approve()

        # Phase 5: Injection
        gate.start_phase(5)
        gate.require_confirmation("INJECTION_CONFIRM")
        gate.approve()

        assert gate.phase == 5
        assert gate.is_approved


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
