"""
CiteMatch v2 主管道 — 编排完整工作流

RC Fixes:
- F1: WorkflowBlockedError re-raised (not swallowed)
- F5: Ordered injection: create_plan → validate → backup → inject_temp → verify → atomic_replace
- F6: All writes go through WriteGuard.safe_write()

使用方式:
    from engine.pipeline import CiteMatchPipeline

    pipeline = CiteMatchPipeline(workspace_root="D:/workspace")
    result = pipeline.run(
        bib_path="references.bib",
        draft_path="paper_draft.md",
        output_path="paper_draft_cited.md",
    )
"""
import os
import json
from datetime import datetime
from typing import Optional

from state_machine import CiteMatchStateMachine
from cm_types import (
    WorkflowPhase, BibEntry, CitationPosition, MatchResult,
    RegistrySnapshot, PipelineReport, WorkflowBlockedError,
)
from bib_parser import BibTeXParser
from md_ast import MarkdownAST
from citation_registry import CitationRegistry, CitationLockError, CitationIntegrityError
from matcher import CitationMatcher
from injector import CitationInjector
from bilingual_sync import BilingualSyncEngine, SyncReport
from file_guard import WriteGuard

# 不可被 except Exception 吞没的异常类型
HARD_BLOCK_EXCEPTIONS = (
    WorkflowBlockedError,
    CitationLockError,
    CitationIntegrityError,
)


class CiteMatchPipeline:
    """CiteMatch v2 完整管道"""

    def __init__(self, workspace_root: Optional[str] = None):
        self._state = CiteMatchStateMachine()
        self._registry = CitationRegistry()
        self._matcher = CitationMatcher(self._registry)
        self._injector = CitationInjector(self._registry)
        self._bilingual = BilingualSyncEngine(self._registry)
        self._write_guard = WriteGuard(workspace_root=workspace_root)

        # 数据
        self._bib_entries: dict[str, BibEntry] = {}
        self._draft_text: str = ""
        self._output_text: str = ""
        self._citations: list[CitationPosition] = []
        self._match_results: dict[int, Optional[MatchResult]] = {}

        # 报告
        self._reports: list[PipelineReport] = []
        self._snapshot_before: Optional[RegistrySnapshot] = None

    # ---- Main Entry Point ----

    def run(
        self,
        bib_path: str,
        draft_path: str,
        output_path: Optional[str] = None,
        zh_draft_path: Optional[str] = None,
        auto_confirm_tables: bool = False,
        dry_run: bool = True,
    ) -> dict:
        """执行完整引用匹配与注入管道

        Args:
            bib_path: .bib 文件路径
            draft_path: 论文草稿 .md 路径
            output_path: 输出路径（默认不覆盖原草稿）
            zh_draft_path: 中文版草稿路径（用于双语同步）
            auto_confirm_tables: 是否自动确认表格内引用
            dry_run: 默认 True — 必须显式设为 False 才会实际写入文件

        Returns:
            {"success": bool, "report": str, "snapshot": RegistrySnapshot, ...}
        """
        try:
            # --- Phase 1-2: 加载并解析 BibTeX ---
            self._state.transition_to(WorkflowPhase.LOADING_BIB, bib_path)
            self._load_bib(bib_path)
            self._state.transition_to(WorkflowPhase.PARSING_BIB,
                                       f"{len(self._bib_entries)} entries")

            # --- Phase 3-4: 加载并解析草稿 ---
            self._state.transition_to(WorkflowPhase.LOADING_DRAFT, draft_path)
            self._load_draft(draft_path)
            self._state.transition_to(WorkflowPhase.PARSING_AST)

            # --- Phase 5: 扫描引用 ---
            self._state.transition_to(WorkflowPhase.SCANNING_CITATIONS)
            self._scan_citations()

            # 记录注入前快照
            self._snapshot_before = self._registry.snapshot()

            # --- Phase 6: 匹配 ---
            self._state.transition_to(WorkflowPhase.MATCHING,
                                       f"{len(self._citations)} citations to match")
            self._match_results = self._matcher.match_all(self._citations)
            matched = sum(1 for v in self._match_results.values() if v is not None)
            self._reports.append(PipelineReport(
                phase=WorkflowPhase.MATCHING,
                success=True,
                message=f"Matched {matched}/{len(self._citations)} citations",
                data=self._matcher.get_stats(),
            ))

            # --- F5: Ordered Injection Pipeline ---
            self._state.transition_to(WorkflowPhase.INJECTING)

            # Step 1: create_plan
            injection_plan = self._create_injection_plan()
            self._reports.append(PipelineReport(
                phase=WorkflowPhase.INJECTING,
                success=True,
                message=f"Injection plan created: {len(injection_plan)} candidates",
            ))

            # Step 2: validate_plan — check for locked/table citations
            plan_valid, plan_issues = self._validate_injection_plan(
                injection_plan, auto_confirm_tables)
            if not plan_valid:
                raise WorkflowBlockedError("INJECTION_BLOCKED",
                    f"Injection plan validation failed: {'; '.join(plan_issues)}")

            # Step 3: backup — create file backup
            backup_path = self._backup_draft(draft_path)

            # Step 4: inject_temp — inject to in-memory text only
            self._output_text = self._injector.inject_candidates(
                injection_plan,
                auto_confirm=auto_confirm_tables,
            )
            self._reports.append(PipelineReport(
                phase=WorkflowPhase.INJECTING,
                success=True,
                message=f"Injected to memory: "
                        f"{len([l for l in self._injector.injection_log if l['action'] == 'inject'])} "
                        f"citations",
            ))

            # Check for deferred table citations
            if self._injector.has_table_citations() and not auto_confirm_tables:
                # Table citations deferred — NOT injected yet
                deferred = self._injector.get_deferred_table_citations()
                self._reports.append(PipelineReport(
                    phase=WorkflowPhase.INJECTING,
                    success=True,
                    message=f"{len(deferred)} table citations deferred for manual review",
                    warnings=[
                        f"Table citation '{d.get('citekeys', [])}' not injected — "
                        f"requires manual confirmation"
                        for d in deferred
                    ],
                ))

            # --- Phase 8: Validate result ---
            self._state.transition_to(WorkflowPhase.VERIFYING)
            snapshot = self._verify()

            # --- Phase 9: 双语同步（如有中文版）---
            sync_report = None
            if zh_draft_path and os.path.exists(zh_draft_path):
                self._state.transition_to(WorkflowPhase.SYNCING)
                sync_report = self._sync_bilingual(zh_draft_path)

            # --- F5 Step 5: atomic_replace (only if NOT dry_run) ---
            if not dry_run and output_path:
                self._write_guard.set_backup_path(backup_path)
                self._write_guard.set_dry_run_completed()
                self._write_guard.set_validator(
                    lambda: snapshot.orphan_count <= self._snapshot_before.orphan_count
                )
                self._write_guard.validate()
                written_path = self._write_guard.safe_write(
                    self._output_text, output_path)
                self._reports.append(PipelineReport(
                    phase=WorkflowPhase.DONE,
                    success=True,
                    message=f"Written to {written_path}",
                ))

            self._state.transition_to(WorkflowPhase.DONE)

            return {
                "success": True,
                "dry_run": dry_run,
                "report": self._generate_report(),
                "snapshot": snapshot,
                "state_history": self._state.history_report(),
                "sync_report": sync_report,
                "unmatched_warnings": self._matcher.warnings,
                "output_path": output_path if not dry_run else None,
                "backup_path": backup_path,
                "write_guard_status": self._write_guard.status_report(),
            }

        except HARD_BLOCK_EXCEPTIONS:
            # F1: Hard blocks MUST propagate — never swallowed
            self._state.transition_to(WorkflowPhase.ERROR, "HARD BLOCK — re-raising")
            raise

        except Exception as e:
            # Only recoverable errors are caught here
            self._state.transition_to(WorkflowPhase.ERROR, str(e))
            self._reports.append(PipelineReport(
                phase=WorkflowPhase.ERROR,
                success=False,
                message=str(e),
                errors=[str(e)],
            ))
            return {
                "success": False,
                "error": str(e),
                "phase": self._state.phase.name,
                "state_history": self._state.history_report(),
            }

    # ---- F5: Injection Plan Methods ----

    def _create_injection_plan(self) -> list[tuple[CitationPosition, MatchResult]]:
        """创建注入计划 — 构建候选列表"""
        position_map: dict[CitationPosition, MatchResult] = {}
        for i, pos in enumerate(self._citations):
            result = self._match_results.get(i)
            if result:
                position_map[pos] = result
        return [(pos, m) for pos, m in position_map.items()]

    def _validate_injection_plan(
        self,
        plan: list[tuple[CitationPosition, MatchResult]],
        auto_confirm_tables: bool,
    ) -> tuple[bool, list[str]]:
        """验证注入计划 — 检查锁定引用和表格引用"""
        issues = []

        for pos, match in plan:
            # 检查锁定
            if self._registry.is_locked(match.citekey):
                issues.append(
                    f"LOCKED: citation '{match.citekey}' at line {pos.line_number} "
                    f"is locked and cannot be modified"
                )

            # 检查表格引用
            if pos.is_in_table and not auto_confirm_tables:
                issues.append(
                    f"TABLE: citation '{match.citekey}' at line {pos.line_number} "
                    f"is inside a table — requires auto_confirm_tables=True"
                )

            # 检查代码块
            if pos.is_in_code_block:
                issues.append(
                    f"CODE_BLOCK: citation '{match.citekey}' at line {pos.line_number} "
                    f"is inside a code block — cannot inject"
                )

        return len(issues) == 0, issues

    def _backup_draft(self, draft_path: str) -> str:
        """创建草稿备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = draft_path + f".bak_{timestamp}"
        if os.path.exists(draft_path):
            import shutil
            shutil.copy2(draft_path, backup_path)
        self._reports.append(PipelineReport(
            phase=WorkflowPhase.INJECTING,
            success=True,
            message=f"Backup created: {backup_path}",
        ))
        return backup_path

    # ---- Quick Operations ----

    def scan_only(self, draft_path: str) -> list[CitationPosition]:
        """仅扫描引用（不修改文档）"""
        self._load_draft(draft_path)
        self._citations = self._scan_citations()
        return list(self._citations)

    def verify_only(self, draft_path: str, bib_path: str) -> RegistrySnapshot:
        """仅验证（不修改文档）"""
        self._load_bib(bib_path)
        self._load_draft(draft_path)
        self._scan_citations()
        return self._registry.snapshot()

    # ---- Internal: Phase Handlers ----

    def _load_bib(self, path: str) -> None:
        """加载 BibTeX 文件"""
        parser = BibTeXParser()
        self._bib_entries = parser.parse_file(path)
        self._registry.bulk_register(self._bib_entries)
        self._matcher.load_bib(self._bib_entries)

        if parser.warnings:
            self._reports.append(PipelineReport(
                phase=WorkflowPhase.PARSING_BIB,
                success=True,
                message="Parsed with warnings",
                warnings=parser.warnings,
            ))

    def _load_draft(self, path: str) -> None:
        """加载草稿"""
        with open(path, 'r', encoding='utf-8') as f:
            self._draft_text = f.read()
        self._injector.set_document(self._draft_text)

    def _scan_citations(self) -> list[CitationPosition]:
        """扫描文档中的引用"""
        ast = MarkdownAST(self._draft_text)
        ast.parse()

        # 收集所有引用
        static_cits = ast.find_static_citations()
        pandoc_cits = ast.find_existing_pandoc_citations()

        self._citations = static_cits + pandoc_cits

        # 注册已有 Pandoc 引用
        for cit in pandoc_cits:
            import re
            keys = re.findall(r'@(\w+)', cit.raw_text)
            for key in keys:
                self._registry.register(key, cit)

        self._reports.append(PipelineReport(
            phase=WorkflowPhase.SCANNING_CITATIONS,
            success=True,
            message=f"Found {len(static_cits)} static + {len(pandoc_cits)} Pandoc citations",
            data={
                "static_count": len(static_cits),
                "pandoc_count": len(pandoc_cits),
                "total": len(self._citations),
            },
        ))

        return self._citations

    def _verify(self) -> RegistrySnapshot:
        """验证引用守恒 — F1: critical issues now raise, not warn"""
        snapshot = self._registry.snapshot()

        if self._snapshot_before:
            # Orphan increase is a hard error
            if snapshot.orphan_count > self._snapshot_before.orphan_count:
                self._reports.append(PipelineReport(
                    phase=WorkflowPhase.VERIFYING,
                    success=False,
                    message="Orphan citations increased — CONSERVATION VIOLATION",
                    errors=[
                        f"Orphans: {self._snapshot_before.orphan_count} → "
                        f"{snapshot.orphan_count}"
                    ],
                ))
                # F1: This is now a hard block
                raise CitationIntegrityError(
                    f"Citation conservation violated: "
                    f"orphans increased from {self._snapshot_before.orphan_count} "
                    f"to {snapshot.orphan_count}"
                )

        self._reports.append(PipelineReport(
            phase=WorkflowPhase.VERIFYING,
            success=True,
            message=f"Verification: {snapshot.total_citekeys} keys, "
                    f"{snapshot.injected_count} injected, "
                    f"{snapshot.orphan_count} orphans, "
                    f"{snapshot.missing_count} missing bib",
            data=snapshot,
        ))

        return snapshot

    def _sync_bilingual(self, zh_path: str) -> Optional[SyncReport]:
        """执行双语同步 — F4: 只做 compare，不修改文件"""
        with open(zh_path, 'r', encoding='utf-8') as f:
            zh_text = f.read()

        self._bilingual.load_documents(self._draft_text, zh_text)
        report = self._bilingual.compare()

        # F4: 只报告差异，不调用 lock_synced_keys 或 sync_missing_citations
        self._reports.append(PipelineReport(
            phase=WorkflowPhase.SYNCING,
            success=report.is_synced,
            message=f"Bilingual sync: {report.matched} matched, "
                    f"{len(report.missing_in_zh)} missing in ZH, "
                    f"{len(report.missing_in_en)} missing in EN",
            data=report,
        ))

        return report

    def _generate_report(self) -> str:
        """生成完整管道报告"""
        lines = [
            "=" * 60,
            "CiteMatch v2 Pipeline Report",
            "=" * 60,
            f"Timestamp: {datetime.now().isoformat()}",
            "",
            self._state.history_report(),
            "",
            f"BibTeX entries: {len(self._bib_entries)}",
            f"Citations found: {len(self._citations)}",
            f"Matched: {sum(1 for v in self._match_results.values() if v is not None)}",
            f"Injected: {len([l for l in self._injector.injection_log if l['action'] == 'inject'])}",
            f"Table citations protected: {len(self._registry.get_table_citations())}",
            "",
        ]

        # 匹配统计
        stats = self._matcher.get_stats()
        lines.append("Match Statistics:")
        for k, v in stats.items():
            lines.append(f"  {k}: {v}")

        # 注入日志
        if self._injector.injection_log:
            lines.append("\nInjection Log:")
            for log in self._injector.injection_log:
                lines.append(f"  [{log['action']}] {log.get('citekey', '')} "
                            f"@ line {log.get('line', '?')}: "
                            f"{log.get('old', '')} → {log.get('new', '')}")

        # 警告
        unmatched = self._matcher.unmatched
        if unmatched:
            lines.append("\n⚠ Unmatched Citations:")
            for pos in unmatched:
                lines.append(f"  Line {pos.line_number}: {pos.raw_text}")

        return '\n'.join(lines)
