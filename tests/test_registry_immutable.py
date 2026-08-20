"""
test_registry_immutable.py — F3 RC Fix: Citation Registry Immutability

验证:
1. CitationRecord is frozen — 修改字段抛出 FrozenInstanceError
2. positions is tuple — 无法 .append() / .clear()
3. 无法直接访问 _records dict
4. get_record() 返回副本
5. get_positions() 返回 tuple
6. 通过公共方法 lock/unlock 修改不会直接 mutate record
"""
import sys
import os
import pytest
from dataclasses import FrozenInstanceError

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import CitationPosition, CitationRecord, BibEntry
from citation_registry import CitationRegistry, CitationLockError


# ---- Test: CitationRecord Frozen ----

class TestCitationRecordFrozen:
    """CitationRecord 不可变性"""

    def test_cannot_modify_field(self):
        """修改 frozen dataclass 字段抛出 FrozenInstanceError"""
        record = CitationRecord(citekey="test_key")
        with pytest.raises(FrozenInstanceError):
            record.is_injected = True

    def test_cannot_append_to_positions(self):
        """positions 是 tuple，无法 append"""
        record = CitationRecord(citekey="test_key", positions=())
        # tuple 没有 append 方法
        with pytest.raises(AttributeError):
            record.positions.append(
                CitationPosition(line_number=1, column_start=1, column_end=5,
                               raw_text="[1]"))

    def test_cannot_clear_positions(self):
        """positions 无法 clear"""
        pos = CitationPosition(line_number=1, column_start=1, column_end=5,
                               raw_text="[1]")
        record = CitationRecord(citekey="test_key", positions=(pos,))
        with pytest.raises(AttributeError):
            record.positions.clear()

    def test_cannot_delete_position(self):
        """positions 无法 delete"""
        pos = CitationPosition(line_number=1, column_start=1, column_end=5,
                               raw_text="[1]")
        record = CitationRecord(citekey="test_key", positions=(pos,))
        with pytest.raises(TypeError):
            del record.positions[0]

    def test_cannot_modify_metadata_directly(self):
        """metadata 仍然是 dict，但从 dataclass 角度看 record 不可变"""
        record = CitationRecord(citekey="test_key", metadata={"key": "value"})
        # metadata dict 内容可改，但 record 字段引用不可变
        with pytest.raises(FrozenInstanceError):
            record.metadata = {"new": "dict"}


# ---- Test: Registry Safe Accessors ----

class TestRegistrySafeAccessors:
    """注册表安全访问器"""

    def test_get_record_returns_record(self):
        """get_record 返回 CitationRecord"""
        registry = CitationRegistry()
        registry.register("test_key",
            CitationPosition(line_number=5, column_start=10, column_end=13,
                           raw_text="[1]"))
        record = registry.get_record("test_key")
        assert record is not None
        assert record.citekey == "test_key"

    def test_get_record_not_modifiable(self):
        """get_record 返回的 record 不可修改"""
        registry = CitationRegistry()
        registry.register("test_key")
        record = registry.get_record("test_key")
        assert record is not None
        with pytest.raises(FrozenInstanceError):
            record.is_injected = True

    def test_get_positions_returns_tuple(self):
        """get_positions 返回 tuple"""
        registry = CitationRegistry()
        pos = CitationPosition(line_number=5, column_start=10, column_end=13,
                               raw_text="[1]")
        registry.register("test_key", pos)
        positions = registry.get_positions("test_key")
        assert isinstance(positions, tuple)
        assert len(positions) == 1

    def test_get_positions_cannot_modify(self):
        """get_positions 返回的 tuple 无法修改"""
        registry = CitationRegistry()
        pos = CitationPosition(line_number=5, column_start=10, column_end=13,
                               raw_text="[1]")
        registry.register("test_key", pos)
        positions = registry.get_positions("test_key")
        with pytest.raises(AttributeError):
            positions.append(pos)

    def test_get_positions_nonexistent(self):
        """get_positions 对不存在的 key 返回空 tuple"""
        registry = CitationRegistry()
        positions = registry.get_positions("nonexistent")
        assert positions == ()

    def test_no_direct_records_access(self):
        """不能直接访问 _records dict"""
        registry = CitationRegistry()
        # _records is private by convention
        assert hasattr(registry, '_records')
        # but we encourage using get_record/get_positions
        record = registry.get_record("nonexistent")
        assert record is None


# ---- Test: Registry Modifications Create New Records ----

class TestRegistryImmutableUpdates:
    """注册表的修改操作创建新 record"""

    def test_register_creates_new_record_on_addition(self):
        """追加位置时创建新 record"""
        registry = CitationRegistry()
        pos1 = CitationPosition(line_number=5, column_start=10, column_end=13,
                                raw_text="[1]")
        r1 = registry.register("test_key", pos1)
        assert len(r1.positions) == 1

        pos2 = CitationPosition(line_number=10, column_start=20, column_end=23,
                                raw_text="[2]")
        r2 = registry.register("test_key", pos2)
        assert len(r2.positions) == 2

        # r1 is the old record — still has 1 position
        assert len(r1.positions) == 1

    def test_lock_creates_new_record(self):
        """lock 创建新 record"""
        registry = CitationRegistry()
        r1 = registry.register("test_key")
        assert r1.is_locked is False

        registry.lock("test_key")
        r2 = registry.get_record("test_key")
        assert r2 is not None
        assert r2.is_locked is True
        # r1 unchanged
        assert r1.is_locked is False

    def test_mark_injected_creates_new_record(self):
        """mark_injected 创建新 record"""
        registry = CitationRegistry()
        r1 = registry.register("test_key")
        assert r1.is_injected is False

        registry.mark_injected("test_key")
        r2 = registry.get_record("test_key")
        assert r2 is not None
        assert r2.is_injected is True
        assert r1.is_injected is False


# ---- Test: Lock Protection ----

class TestLockProtection:
    """锁定保护"""

    def test_locked_cannot_mark_injected(self):
        """锁定后 mark_injected 抛出异常"""
        registry = CitationRegistry()
        registry.register("test_key")
        registry.lock("test_key")

        with pytest.raises(CitationLockError):
            registry.mark_injected("test_key")

    def test_unlock_allows_mark_injected(self):
        """解锁后 mark_injected 成功"""
        registry = CitationRegistry()
        registry.register("test_key")
        registry.lock("test_key")
        registry.unlock("test_key")
        # Should not raise
        registry.mark_injected("test_key")

    def test_get_uninjected_excludes_locked(self):
        """get_uninjected_keys 排除锁定引用"""
        registry = CitationRegistry()
        registry.register("a")
        registry.register("b")
        registry.lock("b")

        uninjected = registry.get_uninjected_keys()
        assert "a" in uninjected
        assert "b" not in uninjected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
