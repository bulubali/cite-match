"""
test_citation_lock.py — 引用锁定与完整性测试

验证:
1. 引用锁机制: lock/unlock/is_locked
2. 锁定引用不可被注入修改
3. 锁定引用不可被删除
4. 注册表变更日志完整性
5. 快照与哈希一致性
"""
import sys
import os
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import (
    CitationPosition, CitationRecord, BibEntry, MatchResult,
    MatchStrategy, RegistrySnapshot, WorkflowPhase,
)
from citation_registry import (
    CitationRegistry, CitationIntegrityError, CitationLockError,
)
from state_machine import (
    CiteMatchStateMachine, TransitionError, PhaseGuard,
)


# ---- Fixtures ----

@pytest.fixture
def registry():
    return CitationRegistry()


@pytest.fixture
def populated_registry(registry):
    """预填充的注册表"""
    bib = BibEntry(
        citekey="Test2024PulseWave",
        entry_type="article",
        fields={
            "author": "Test, A. and Demo, B.",
            "year": "2024",
            "title": "Pulse Wave Analysis for BP Monitoring",
            "journal": "Nature Communications",
            "doi": "10.1038/test.2024.001",
        }
    )
    for i in range(5):
        pos = CitationPosition(
            line_number=5 + i * 3,
            column_start=40,
            column_end=45 + i,
            raw_text=f"[{i+1}]",
            is_in_table=False,
        )
        registry.register(f"test_key_{i}", pos, bib if i == 0 else None)
    return registry


# ---- Test: Lock/Unlock ----

class TestLockMechanism:
    """引用锁基础机制"""

    def test_lock_single_key(self, registry):
        """锁定单个引用"""
        registry.register("key1")
        registry.lock("key1")
        assert registry.is_locked("key1")

    def test_unlock_key(self, registry):
        """解锁引用"""
        registry.register("key1")
        registry.lock("key1")
        registry.unlock("key1")
        assert not registry.is_locked("key1")

    def test_lock_non_existent(self, registry):
        """锁定不存在的引用不抛异常"""
        registry.lock("nonexistent")
        assert registry.is_locked("nonexistent")

    def test_get_locked_keys(self, populated_registry):
        """获取所有锁定的引用"""
        populated_registry.lock("test_key_1")
        populated_registry.lock("test_key_3")
        locked = populated_registry.get_locked_keys()
        assert "test_key_1" in locked
        assert "test_key_3" in locked
        assert "test_key_0" not in locked

    def test_lock_persists_in_record(self, populated_registry):
        """锁定状态反映在 CitationRecord 中"""
        populated_registry.lock("test_key_2")
        record = populated_registry.get_record("test_key_2")
        assert record is not None
        assert record.is_locked is True


# ---- Test: Locked Item Protection ----

class TestLockedItemProtection:
    """锁定条目保护行为"""

    def test_mark_injected_raises_for_locked(self, populated_registry):
        """锁定引用无法标记为已注入"""
        populated_registry.lock("test_key_0")
        with pytest.raises(CitationLockError):
            populated_registry.mark_injected("test_key_0")

    def test_mark_injected_ok_for_unlocked(self, populated_registry):
        """未锁定引用可以标记为已注入"""
        populated_registry.mark_injected("test_key_2")
        assert populated_registry.get_record("test_key_2").is_injected

    def test_locked_keys_not_in_uninjected(self, populated_registry):
        """锁定的引用不出现在未注入列表"""
        populated_registry.lock("test_key_1")
        uninjected = populated_registry.get_uninjected_keys()
        assert "test_key_1" not in uninjected


# ---- Test: Change Log ----

class TestChangeLog:
    """变更日志完整性"""

    def test_register_logs_change(self, registry):
        """注册操作被记录"""
        registry.register("new_key")
        log = registry.get_change_log()
        assert len(log) > 0
        assert log[-1]["action"] == "register"
        assert log[-1]["citekey"] == "new_key"

    def test_lock_logs_change(self, registry):
        """锁定操作被记录"""
        registry.register("key_x")
        registry.lock("key_x")
        log = registry.get_change_log()
        lock_entries = [e for e in log if e["action"] == "lock"]
        assert len(lock_entries) > 0

    def test_total_records_tracked(self, registry):
        """变更日志中 total_records 随操作更新"""
        registry.register("a")
        assert registry.get_change_log()[-1]["total_records"] == 1
        registry.register("b")
        assert registry.get_change_log()[-1]["total_records"] == 2

    def test_change_callback(self, registry):
        """变更回调被触发"""
        calls = []
        registry.on_change(lambda entry: calls.append(entry))
        registry.register("cb_test")
        assert len(calls) == 1
        assert calls[0]["citekey"] == "cb_test"


# ---- Test: Snapshot ----

class TestSnapshot:
    """快照功能"""

    def test_snapshot_captures_state(self, populated_registry):
        """快照捕获当前状态"""
        snap = populated_registry.snapshot()
        assert snap.total_citekeys == 5
        assert isinstance(snap.citekeys, list)
        assert len(snap.citekeys) == 5

    def test_snapshot_registry_not_empty(self, registry):
        """空注册表快照"""
        snap = registry.snapshot()
        assert snap.total_citekeys == 0
        assert snap.orphan_count == 0


# ---- Test: State Machine ----

class TestStateMachine:
    """状态机正确性"""

    def test_initial_state(self):
        """初始状态为 IDLE"""
        sm = CiteMatchStateMachine()
        assert sm.phase == WorkflowPhase.IDLE

    def test_valid_transitions(self):
        """合法状态转换"""
        sm = CiteMatchStateMachine()
        sm.transition_to(WorkflowPhase.LOADING_BIB)
        assert sm.phase == WorkflowPhase.LOADING_BIB
        sm.transition_to(WorkflowPhase.PARSING_BIB)
        assert sm.phase == WorkflowPhase.PARSING_BIB

    def test_invalid_transition_raises(self):
        """非法状态转换抛出异常"""
        sm = CiteMatchStateMachine()
        with pytest.raises(TransitionError):
            sm.transition_to(WorkflowPhase.MATCHING)  # 不能从 IDLE 跳到 MATCHING

    def test_full_workflow(self):
        """完整工作流状态转换"""
        sm = CiteMatchStateMachine()
        phases = [
            WorkflowPhase.LOADING_BIB,
            WorkflowPhase.PARSING_BIB,
            WorkflowPhase.LOADING_DRAFT,
            WorkflowPhase.PARSING_AST,
            WorkflowPhase.SCANNING_CITATIONS,
            WorkflowPhase.MATCHING,
            WorkflowPhase.INJECTING,
            WorkflowPhase.VERIFYING,
            WorkflowPhase.DONE,
        ]
        for phase in phases:
            sm.transition_to(phase)
        assert sm.is_done

    def test_abort(self):
        """中止工作流"""
        sm = CiteMatchStateMachine()
        sm.transition_to(WorkflowPhase.LOADING_BIB)
        sm.abort("Test abort")
        assert sm.is_error

    def test_reset(self):
        """重置状态机"""
        sm = CiteMatchStateMachine()
        sm.transition_to(WorkflowPhase.LOADING_BIB)
        sm.reset()
        assert sm.phase == WorkflowPhase.IDLE

    def test_history(self):
        """状态历史记录"""
        sm = CiteMatchStateMachine()
        sm.transition_to(WorkflowPhase.LOADING_BIB, "loading test.bib")
        sm.transition_to(WorkflowPhase.PARSING_BIB, "50 entries")
        history = sm.history_report()
        assert "LOADING_BIB" in history
        assert "PARSING_BIB" in history


# ---- Test: Hash Inmutation Detection ----

class TestHashConsistency:
    """哈希一致性"""

    def test_same_content_same_hash(self, registry):
        """相同内容产生相同哈希"""
        for k in ["a", "b", "c"]:
            registry.register(k, CitationPosition(
                line_number=1, column_start=1, column_end=5,
                raw_text="[1]", is_in_table=False))

        hash1 = registry.compute_hash()
        hash2 = registry.compute_hash()
        assert hash1 == hash2

    def test_different_content_different_hash(self, registry):
        """不同内容产生不同哈希"""
        registry.register("key_x")
        hash1 = registry.compute_hash()

        registry.register("key_y")
        hash2 = registry.compute_hash()
        assert hash1 != hash2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
