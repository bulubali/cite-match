"""
CiteMatch v2 文件写入守卫 — F6 RC Fix

所有文件写入必须经过 WriteGuard.safe_write()。
检查链:
  1. backup 存在?     → 无则 raise WriteBlockedError
  2. dry_run 完成?    → 无则 raise WriteBlockedError
  3. validator 通过?  → 无则 raise WriteBlockedError
  4. 路径白名单?      → 不在工作区则 raise WriteBlockedError
"""
import os
import shutil
from datetime import datetime
from typing import Optional, Callable
from cm_types import WriteBlockedError


class WriteGuard:
    """文件写入守卫 — F6 LLM 直接文件写入隔离

    用法:
        guard = WriteGuard(workspace_root="D:/workspace")
        guard.set_backup_path("draft_backup.md")
        guard.set_dry_run_completed()
        guard.set_validator(lambda: True)
        guard.safe_write(content, "draft.md")
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self._workspace_root = os.path.abspath(workspace_root) if workspace_root else None
        self._backup_path: Optional[str] = None
        self._dry_run_completed: bool = False
        self._validator: Optional[Callable[[], bool]] = None
        self._validator_passed: bool = False
        self._backup_created: bool = False

    # ---- Configuration ----

    def set_backup_path(self, path: str) -> None:
        """设置备份文件路径"""
        self._backup_path = os.path.abspath(path)

    def set_dry_run_completed(self) -> None:
        """标记 dry_run 已完成"""
        self._dry_run_completed = True

    def set_validator(self, validator: Callable[[], bool]) -> None:
        """设置验证器回调"""
        self._validator = validator

    # ---- Checks ----

    def _ensure_backup(self, target_path: str) -> None:
        """确保备份存在 — 如果未设置则自动创建"""
        if self._backup_path is None:
            # 自动创建备份路径（即使目标文件还不存在，也预留路径）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target_path + f".bak_{timestamp}"
            self._backup_path = backup_path
            if os.path.exists(target_path):
                shutil.copy2(target_path, backup_path)
                self._backup_created = True
        else:
            if not os.path.exists(self._backup_path):
                # backup path was set but file doesn't exist — try to create
                if os.path.exists(target_path):
                    shutil.copy2(target_path, self._backup_path)
                    self._backup_created = True

    def _check_backup(self) -> None:
        """检查 backup 是否就绪"""
        if self._backup_path is None:
            raise WriteBlockedError(
                "No backup path configured. Call set_backup_path() first."
            )
        # 备份路径已设但文件还未创建 — 在 _ensure_backup 中处理

    def _check_dry_run(self) -> None:
        """检查 dry_run 是否完成"""
        if not self._dry_run_completed:
            raise WriteBlockedError(
                "Dry run not completed. Run dry_run mode first to preview changes."
            )

    def _check_validator(self) -> None:
        """检查 validator 是否通过"""
        if self._validator is None:
            raise WriteBlockedError(
                "No validator configured. Call set_validator() first."
            )
        if not self._validator_passed:
            raise WriteBlockedError(
                "Validator has not passed. Run validate() first."
            )

    def _check_path(self, target_path: str) -> None:
        """检查目标路径是否在工作区内"""
        if self._workspace_root is None:
            return  # 无工作区限制时跳过

        abs_target = os.path.abspath(target_path)
        # 规范化路径比较
        try:
            common = os.path.commonpath([self._workspace_root, abs_target])
            if common != self._workspace_root:
                raise WriteBlockedError(
                    f"Target path '{target_path}' is outside workspace "
                    f"'{self._workspace_root}'. LLM cannot write outside workspace."
                )
        except ValueError:
            raise WriteBlockedError(
                f"Cannot resolve path: '{target_path}'"
            )

    # ---- Validation ----

    def validate(self) -> bool:
        """运行验证器"""
        if self._validator is None:
            return False
        try:
            self._validator_passed = self._validator()
            return self._validator_passed
        except Exception:
            self._validator_passed = False
            return False

    # ---- Write ----

    def safe_write(self, content: str, target_path: str) -> str:
        """安全写入文件 — 所有检查必须通过

        Args:
            content: 要写入的内容
            target_path: 目标文件路径

        Returns:
            实际写入的路径

        Raises:
            WriteBlockedError: 任何检查未通过
        """
        # 1. 路径白名单检查
        self._check_path(target_path)

        # 2. 备份检查 + 自动备份
        self._ensure_backup(target_path)

        # 3. dry_run 检查
        self._check_dry_run()

        # 4. validator 检查
        self._check_validator()

        # 所有检查通过 — 执行写入
        abs_target = os.path.abspath(target_path)
        os.makedirs(os.path.dirname(abs_target), exist_ok=True)
        with open(abs_target, 'w', encoding='utf-8') as f:
            f.write(content)

        return abs_target

    def safe_write_temp(self, content: str, target_path: str) -> str:
        """写入临时文件（不要求 dry_run/validator，用于 inject_temp 阶段）

        Returns:
            临时文件路径
        """
        self._check_path(target_path)
        self._ensure_backup(target_path)

        temp_path = target_path + ".temp"
        abs_temp = os.path.abspath(temp_path)
        os.makedirs(os.path.dirname(abs_temp), exist_ok=True)
        with open(abs_temp, 'w', encoding='utf-8') as f:
            f.write(content)

        return abs_temp

    def atomic_replace(self, temp_path: str, target_path: str) -> str:
        """原子替换 — 将临时文件替换为目标文件

        要求 safe_write_temp 先完成，然后 validate() 通过。
        """
        self._check_path(target_path)
        self._check_dry_run()
        self._check_validator()

        abs_temp = os.path.abspath(temp_path)
        abs_target = os.path.abspath(target_path)

        if not os.path.exists(abs_temp):
            raise WriteBlockedError(f"Temp file does not exist: {temp_path}")

        # 原子替换
        shutil.move(abs_temp, abs_target)
        return abs_target

    # ---- Status ----

    @property
    def backup_path(self) -> Optional[str]:
        return self._backup_path

    @property
    def is_dry_run_done(self) -> bool:
        return self._dry_run_completed

    @property
    def is_validator_passed(self) -> bool:
        return self._validator_passed

    @property
    def is_ready(self) -> bool:
        """是否满足所有写入条件"""
        return (
            self._backup_path is not None
            and self._dry_run_completed
            and self._validator_passed
        )

    def status_report(self) -> dict:
        return {
            "backup_path": self._backup_path,
            "backup_created": self._backup_created,
            "dry_run_completed": self._dry_run_completed,
            "validator_passed": self._validator_passed,
            "is_ready": self.is_ready,
            "workspace_root": self._workspace_root,
        }
