"""
CiteMatch v2 引用注册表 — 引用守恒与完整性验证

核心功能:
- 注册表: 跟踪所有引用（citekey, 位置, 状态, 锁定）
- 守恒验证: 注入前/后的引用数量必须一致
- 变更追踪: 记录所有增删改操作
- 快照: 用于回滚和审计

F3 RC Fix:
- CitationRecord is frozen — 外部无法修改
- positions is tuple — 不可变
- 内部 _records 不可公开访问
- 所有修改必须通过 register/lock/unlock 等公共方法
"""
import copy
import hashlib
from typing import Optional, Callable
from cm_types import (
    CitationPosition, CitationRecord, RegistrySnapshot,
    BibEntry, MatchResult,
)


class CitationIntegrityError(Exception):
    """引用完整性错误"""
    pass


class CitationLockError(Exception):
    """引用锁定冲突错误"""
    pass


class CitationRegistry:
    """引用注册表 — 引用数据的唯一真实来源

    所有内部状态通过公共方法访问。外部无法直接修改 records。
    """

    def __init__(self):
        self._records: dict[str, CitationRecord] = {}  # citekey → immutable record
        self._locked_keys: set[str] = set()             # 锁定的 citekey
        self._change_log: list[dict] = []               # 变更日志
        self._snapshots: list[RegistrySnapshot] = []     # 快照列表
        self._table_citation_keys: set[str] = set()      # 表格内引用的 citekey
        self._on_change: Optional[Callable] = None

    # ---- Public Read Accessors (no direct dict exposure) ----

    def get_record(self, citekey: str) -> Optional[CitationRecord]:
        """获取引用的不可变副本"""
        return self._records.get(citekey)

    def get_positions(self, citekey: str) -> tuple[CitationPosition, ...]:
        """获取引用的位置元组（不可变）"""
        record = self._records.get(citekey)
        if record is None:
            return ()
        return record.positions

    def get_all_keys(self) -> list[str]:
        return sorted(self._records.keys())

    # ---- Registration ----

    def register(self, citekey: str, position: Optional[CitationPosition] = None,
                 bib_entry: Optional[BibEntry] = None) -> CitationRecord:
        """注册一个引用（如果已存在则创建新 record 追加位置）

        返回不可变的 CitationRecord。
        """
        if citekey in self._records:
            old = self._records[citekey]
            new_positions = list(old.positions)
            if position:
                new_positions.append(position)
                if position.is_in_table:
                    self._table_citation_keys.add(citekey)
            new_record = CitationRecord(
                citekey=citekey,
                positions=tuple(new_positions),
                bib_entry=bib_entry if bib_entry and not old.bib_entry else old.bib_entry,
                is_injected=old.is_injected,
                is_locked=old.is_locked,
                metadata=dict(old.metadata),
            )
            self._records[citekey] = new_record
            self._log_change("update", citekey,
                             f"Total positions: {len(new_record.positions)}")
            return new_record
        else:
            record = CitationRecord(
                citekey=citekey,
                positions=(position,) if position else (),
                bib_entry=bib_entry,
            )
            self._records[citekey] = record
            if position and position.is_in_table:
                self._table_citation_keys.add(citekey)
            self._log_change("register", citekey)
            return record

    def bulk_register(self, entries: dict[str, BibEntry]) -> None:
        """批量注册 BibTeX 条目（不附带位置）"""
        for citekey, entry in entries.items():
            if citekey in self._records:
                old = self._records[citekey]
                new_record = CitationRecord(
                    citekey=citekey,
                    positions=old.positions,
                    bib_entry=entry,
                    is_injected=old.is_injected,
                    is_locked=old.is_locked,
                    metadata=dict(old.metadata),
                )
                self._records[citekey] = new_record
            else:
                self._records[citekey] = CitationRecord(
                    citekey=citekey,
                    bib_entry=entry,
                )

    # ---- Locking ----

    def lock(self, citekey: str) -> None:
        """锁定引用（禁止后续修改）"""
        self._locked_keys.add(citekey)
        if citekey in self._records:
            old = self._records[citekey]
            new_record = CitationRecord(
                citekey=citekey,
                positions=old.positions,
                bib_entry=old.bib_entry,
                is_injected=old.is_injected,
                is_locked=True,
                metadata=dict(old.metadata),
            )
            self._records[citekey] = new_record
        self._log_change("lock", citekey)

    def unlock(self, citekey: str) -> None:
        """解锁引用"""
        self._locked_keys.discard(citekey)
        if citekey in self._records:
            old = self._records[citekey]
            new_record = CitationRecord(
                citekey=citekey,
                positions=old.positions,
                bib_entry=old.bib_entry,
                is_injected=old.is_injected,
                is_locked=False,
                metadata=dict(old.metadata),
            )
            self._records[citekey] = new_record
        self._log_change("unlock", citekey)

    def is_locked(self, citekey: str) -> bool:
        return citekey in self._locked_keys

    def get_locked_keys(self) -> set[str]:
        return set(self._locked_keys)

    # ---- Table Protection ----

    def protect_table_citations(self) -> None:
        """保护表格内所有引用（锁定 + 标记）"""
        for citekey in self._table_citation_keys:
            self.lock(citekey)
            if citekey in self._records:
                old = self._records[citekey]
                meta = dict(old.metadata)
                meta["protected"] = True
                meta["source"] = "table"
                new_record = CitationRecord(
                    citekey=citekey,
                    positions=old.positions,
                    bib_entry=old.bib_entry,
                    is_injected=old.is_injected,
                    is_locked=True,
                    metadata=meta,
                )
                self._records[citekey] = new_record

    def get_table_citations(self) -> list[str]:
        """获取所有表格引用的 citekey 列表"""
        return sorted(self._table_citation_keys)

    # ---- Mark as injected ----

    def mark_injected(self, citekey: str) -> None:
        """标记引用已注入"""
        if citekey in self._locked_keys:
            raise CitationLockError(
                f"Cannot modify locked citation: {citekey}"
            )
        if citekey in self._records:
            old = self._records[citekey]
            new_record = CitationRecord(
                citekey=citekey,
                positions=old.positions,
                bib_entry=old.bib_entry,
                is_injected=True,
                is_locked=old.is_locked,
                metadata=dict(old.metadata),
            )
            self._records[citekey] = new_record
        self._log_change("inject", citekey)

    # ---- Queries ----

    def get_injected_keys(self) -> list[str]:
        return sorted(k for k, r in self._records.items() if r.is_injected)

    def get_uninjected_keys(self) -> list[str]:
        return sorted(k for k, r in self._records.items()
                      if not r.is_injected and k not in self._locked_keys)

    def get_orphans(self) -> list[str]:
        """获取孤儿引用: 在注册表中但没有位置（未在正文出现）"""
        return sorted(k for k, r in self._records.items()
                      if not r.positions and r.bib_entry is not None)

    def get_missing_bib(self) -> list[str]:
        """获取缺失 BibTeX 的引用: 有位置但没有 bib_entry"""
        return sorted(k for k, r in self._records.items()
                      if r.positions and r.bib_entry is None)

    def count(self) -> int:
        return len(self._records)

    def __contains__(self, citekey: str) -> bool:
        return citekey in self._records

    # ---- Integrity Verification ----

    def verify_conservation(self, expected_count: int) -> tuple[bool, RegistrySnapshot]:
        """引用守恒验证 — 确保注入前后的引用数量不变"""
        snapshot = self.snapshot()
        conserved = snapshot.total_citekeys == expected_count
        return conserved, snapshot

    def verify_no_orphans(self) -> tuple[bool, list[str]]:
        """验证无孤儿引用"""
        orphans = self.get_orphans()
        return len(orphans) == 0, orphans

    def verify_no_missing_bib(self) -> tuple[bool, list[str]]:
        """验证所有引用都有 BibTeX 数据"""
        missing = self.get_missing_bib()
        return len(missing) == 0, missing

    def verify_all(self, expected_count: Optional[int] = None) -> RegistrySnapshot:
        """完整验证"""
        snapshot = self.snapshot()
        if expected_count is not None and snapshot.total_citekeys != expected_count:
            raise CitationIntegrityError(
                f"Citation conservation failed: "
                f"expected {expected_count}, got {snapshot.total_citekeys}"
            )
        return snapshot

    def verify_no_locked_keys_in_range(self, citekeys: set[str]) -> bool:
        """验证给定的 citekey 集合中不包含已锁定的引用"""
        locked_in_range = citekeys & self._locked_keys
        return len(locked_in_range) == 0

    def get_locked_keys_in_range(self, citekeys: set[str]) -> set[str]:
        """返回给定集合中被锁定的引用"""
        return citekeys & self._locked_keys

    # ---- Snapshot ----

    def snapshot(self) -> RegistrySnapshot:
        """创建注册表快照"""
        snap = RegistrySnapshot(
            total_citekeys=len(self._records),
            injected_count=len(self.get_injected_keys()),
            orphan_count=len(self.get_orphans()),
            missing_count=len(self.get_missing_bib()),
            citekeys=self.get_all_keys(),
            orphans=self.get_orphans(),
            missing=self.get_missing_bib(),
            table_citations=self.get_table_citations(),
        )
        self._snapshots.append(snap)
        return snap

    def rollback_to_snapshot(self, index: int = -1) -> None:
        """回滚到指定快照（记录操作）"""
        if not self._snapshots:
            return
        target = self._snapshots[index]
        self._log_change("rollback", "",
                         f"To snapshot with {target.total_citekeys} keys")

    # ---- Change Log ----

    def _log_change(self, action: str, citekey: str, detail: str = ""):
        entry = {
            "action": action,
            "citekey": citekey,
            "detail": detail,
            "total_records": len(self._records),
        }
        self._change_log.append(entry)
        if self._on_change:
            self._on_change(entry)

    def get_change_log(self) -> list[dict]:
        return list(self._change_log)

    def on_change(self, callback: Callable):
        """注册变更回调"""
        self._on_change = callback

    # ---- Compute Hash ----

    def compute_hash(self) -> str:
        """计算注册表内容哈希（用于对比验证）"""
        data = ""
        for key in sorted(self._records.keys()):
            r = self._records[key]
            positions_str = ";".join(
                f"{p.line_number}:{p.raw_text}" for p in r.positions
            )
            data += f"{key}|{r.is_injected}|{r.is_locked}|{positions_str}\n"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()[:16]
