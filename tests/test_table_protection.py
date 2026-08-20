"""
test_table_protection.py — 表格引用保护测试

验证 CiteMatch v2 对 Markdown 表格内引用的保护机制:
1. 表格内引用被正确识别
2. 表格内引用默认不自动注入
3. 表格内引用在手动确认后可注入
4. 对表格引用的修改记录到日志
"""
import sys
import os
import pytest

# 添加引擎目录到 sys.path
ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import CitationPosition, MatchResult, MatchStrategy, BibEntry
from md_ast import MarkdownAST
from citation_registry import CitationRegistry, CitationLockError
from injector import CitationInjector
from sample_data import SAMPLE_DRAFT_EN, SAMPLE_BIB


# ---- Fixtures ----

@pytest.fixture
def registry():
    return CitationRegistry()


@pytest.fixture
def injector(registry):
    return CitationInjector(registry)


@pytest.fixture
def ast():
    parser = MarkdownAST(SAMPLE_DRAFT_EN)
    parser.parse()
    return parser


@pytest.fixture
def table_positions(ast):
    """查找表格内的引用"""
    all_cits = ast.find_static_citations()
    return [c for c in all_cits if c.is_in_table]


@pytest.fixture
def body_positions(ast):
    """查找正文（非表格/代码块）中的引用"""
    all_cits = ast.find_static_citations()
    return [c for c in all_cits
            if not c.is_in_table and not c.is_in_code_block]


# ---- Test: Table Detection ----

class TestTableDetection:
    """验证 Markdown 表格检测"""

    def test_table_region_detected(self, ast):
        """表格区域被正确识别"""
        assert len(ast._table_regions) > 0, "Should detect at least one table"

    def test_table_citations_identified(self, table_positions):
        """表格内引用被正确标记"""
        assert len(table_positions) > 0, "Should find citations inside the table"
        for pos in table_positions:
            assert pos.is_in_table, f"Citation at line {pos.line_number} should be marked as in-table"
            assert "Reference" in pos.section or pos.section == "" or "Signal Processing" in pos.section

    def test_body_citations_not_in_table(self, body_positions):
        """正文引用不被标记为表格"""
        for pos in body_positions:
            assert not pos.is_in_table, (
                f"Citation at line {pos.line_number} '{pos.raw_text}' "
                f"should NOT be marked as in-table"
            )


# ---- Test: Table Protection in Registry ----

class TestTableRegistryProtection:
    """验证引用注册表的表格保护"""

    def test_table_keys_tracked(self, registry):
        """表格引用在注册表中被追踪"""
        table_key = "ref_table_1"
        reg = registry.register(table_key,
            CitationPosition(line_number=10, column_start=50, column_end=53,
                           raw_text="[1]", is_in_table=True))
        assert table_key in registry.get_table_citations()

    def test_protect_table_locks_keys(self, registry):
        """protect_table_citations 锁定所有表格引用"""
        for i in range(3):
            registry.register(f"table_key_{i}",
                CitationPosition(line_number=8 + i, column_start=40, column_end=43,
                               raw_text=f"[{i+1}]", is_in_table=True))

        registry.protect_table_citations()

        for i in range(3):
            assert registry.is_locked(f"table_key_{i}"), \
                f"table_key_{i} should be locked after protect_table_citations()"

    def test_body_citations_not_locked_by_table_protection(self, registry):
        """正文引用不被表格保护影响"""
        registry.register("body_key",
            CitationPosition(line_number=5, column_start=30, column_end=33,
                           raw_text="[1]", is_in_table=False))

        registry.protect_table_citations()
        assert not registry.is_locked("body_key")


# ---- Test: Injection Protection ----

class TestInjectionTableProtection:
    """验证注入器的表格保护行为"""

    def test_table_citation_blocked(self, injector):
        """表格内引用被阻止自动注入"""
        injector.set_document(SAMPLE_DRAFT_EN)

        table_pos = CitationPosition(
            line_number=21, column_start=30, column_end=33,
            raw_text="[1]", is_in_table=True, section="Signal Processing")

        match = MatchResult(
            citekey="Chen2023Flexible",
            confidence=1.0,
            strategy=MatchStrategy.DOI)

        result = injector.inject_candidates(
            [(table_pos, match)], auto_confirm=False)

        # 检查是否被延后
        assert injector.has_table_citations(), "Should defer table citation"
        deferred = injector.get_deferred_table_citations()
        assert len(deferred) > 0
        assert any("Chen2023Flexible" in str(d) for d in deferred)

    def test_body_citation_not_blocked(self, injector):
        """正文引用不被阻止"""
        injector.set_document(SAMPLE_DRAFT_EN)

        body_pos = CitationPosition(
            line_number=7, column_start=50, column_end=53,
            raw_text="[1]", is_in_table=False)

        match = MatchResult(
            citekey="Chen2023Flexible",
            confidence=1.0,
            strategy=MatchStrategy.DOI)

        result = injector.inject_candidates(
            [(body_pos, match)], auto_confirm=False)

        # 正文引用应该被注入
        assert len(injector.injection_log) > 0
        injected = [log for log in injector.injection_log if log["action"] == "inject"]
        assert len(injected) > 0, "Body citation should be injected"

    def test_table_citation_auto_confirm(self, injector):
        """auto_confirm=True 时表格引用也被注入"""
        injector.set_document(SAMPLE_DRAFT_EN)

        table_pos = CitationPosition(
            line_number=21, column_start=30, column_end=33,
            raw_text="[1]", is_in_table=True)

        match = MatchResult(
            citekey="Chen2023Flexible",
            confidence=1.0,
            strategy=MatchStrategy.MANUAL)

        result = injector.inject_candidates(
            [(table_pos, match)], auto_confirm=True)

        injected = [log for log in injector.injection_log if log["action"] == "inject"]
        assert len(injected) > 0, "Table citation should be injected with auto_confirm=True"


# ---- Test: Locked Citation Protection ----

class TestLockedCitationProtection:
    """验证锁定引用不可修改"""

    def test_locked_citation_blocked(self, injector, registry):
        """锁定的引用被阻止注入"""
        injector.set_document(SAMPLE_DRAFT_EN)

        # 先注册并锁定
        registry.register("locked_key",
            CitationPosition(line_number=10, column_start=50, column_end=53,
                           raw_text="[1]", is_in_table=False))
        registry.lock("locked_key")

        pos = CitationPosition(line_number=10, column_start=50, column_end=53,
                               raw_text="[1]", is_in_table=False)
        match = MatchResult(citekey="locked_key", confidence=1.0,
                           strategy=MatchStrategy.MANUAL)

        injector.inject_candidates([(pos, match)], auto_confirm=True)

        skipped = [log for log in injector.injection_log if log["action"] == "skip_locked"]
        assert len(skipped) > 0, "Locked citation should be skipped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
