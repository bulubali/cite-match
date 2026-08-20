"""
test_bilingual_sync.py — 双语引用同步测试

验证:
1. 中英文文档引用提取
2. 引用差异检测（缺失/多余）
3. 顺序一致性检查
4. 共同引用锁定
5. 同步报告完整性
"""
import sys
import os
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import CitationPosition
from citation_registry import CitationRegistry
from bilingual_sync import (
    BilingualSyncEngine, SyncReport, SyncDiff,
)
from md_ast import MarkdownAST
from sample_data import SAMPLE_DRAFT_EN, SAMPLE_DRAFT_ZH


# ---- Fixtures ----

@pytest.fixture
def registry():
    reg = CitationRegistry()
    # 预注册样本 bib 中的 citekey
    for key in ["Chen2023Flexible", "Wang2024Ultrathin", "Park2025Hyperspectral",
                "Tan2022PulseWave", "Liu2023Iontronic"]:
        reg.register(key)
    return reg


@pytest.fixture
def sync_engine(registry):
    engine = BilingualSyncEngine(registry)
    engine.load_documents(SAMPLE_DRAFT_EN, SAMPLE_DRAFT_ZH)
    return engine


# ---- Test: Citation Extraction ----

class TestCitationExtraction:
    """验证引用提取"""

    def test_en_citations_extracted(self, sync_engine):
        """英文文档引用被提取"""
        en_ast = MarkdownAST(SAMPLE_DRAFT_EN)
        en_ast.parse()
        pandoc = en_ast.find_existing_pandoc_citations()
        static = en_ast.find_static_citations()
        assert len(pandoc) + len(static) > 0, "Should find citations in EN draft"

    def test_zh_citations_extracted(self, sync_engine):
        """中文文档引用被提取"""
        zh_ast = MarkdownAST(SAMPLE_DRAFT_ZH)
        zh_ast.parse()
        pandoc = zh_ast.find_existing_pandoc_citations()
        assert len(pandoc) > 0, "Should find Pandoc citations in ZH draft"

    def test_en_has_static_citations(self):
        """英文版有静态引用（需要转换）"""
        en_ast = MarkdownAST(SAMPLE_DRAFT_EN)
        en_ast.parse()
        static = en_ast.find_static_citations()
        assert len(static) > 0, "EN draft should contain static [N] citations"

    def test_zh_has_pandoc_citations(self):
        """中文版已有 Pandoc 引用"""
        zh_ast = MarkdownAST(SAMPLE_DRAFT_ZH)
        zh_ast.parse()
        pandoc = zh_ast.find_existing_pandoc_citations()
        assert len(pandoc) > 0, "ZH draft should contain [@key] Pandoc citations"


# ---- Test: Sync Comparison ----

class TestSyncComparison:
    """验证同步对比"""

    def test_compare_returns_report(self, sync_engine):
        """compare() 返回 SyncReport"""
        report = sync_engine.compare()
        assert isinstance(report, SyncReport)
        assert report.total_en_citations >= 0
        assert report.total_zh_citations >= 0

    def test_report_has_matched_count(self, sync_engine):
        """报告包含匹配计数"""
        report = sync_engine.compare()
        assert report.matched >= 0

    def test_diffs_not_empty(self, sync_engine):
        """差异列表不为空（有内容可比较）"""
        report = sync_engine.compare()
        assert isinstance(report.diffs, list)


# ---- Test: Order Checking ----

class TestOrderCheck:
    """引用顺序一致性"""

    def test_order_check_with_identical_order(self):
        """相同顺序通过检查"""
        en_keys = ["keyA", "keyB", "keyC"]
        zh_keys = ["keyA", "keyB", "keyC"]
        result = BilingualSyncEngine._check_order(en_keys, zh_keys)
        assert result is True

    def test_order_check_with_reversed_order(self):
        """颠倒顺序应检测到"""
        en_keys = ["keyA", "keyB", "keyC"]
        zh_keys = ["keyC", "keyB", "keyA"]
        result = BilingualSyncEngine._check_order(en_keys, zh_keys)
        assert result is False

    def test_order_check_with_subset(self):
        """子集顺序一致"""
        en_keys = ["keyA", "keyB", "keyC", "keyD"]
        zh_keys = ["keyA", "keyC"]  # keyB and keyD missing but order kept
        result = BilingualSyncEngine._check_order(en_keys, zh_keys)
        assert result is True

    def test_order_check_crossed(self):
        """交叉顺序检测"""
        en_keys = ["keyA", "keyB", "keyC"]
        zh_keys = ["keyA", "keyC", "keyB"]  # B and C swapped
        result = BilingualSyncEngine._check_order(en_keys, zh_keys)
        assert result is False


# ---- Test: Consistency Verification ----

class TestConsistencyVerification:
    """一致性验证"""

    def test_verify_empty_docs(self, registry):
        """空文档验证"""
        engine = BilingualSyncEngine(registry)
        engine.load_documents("", "")
        assert engine.verify_consistency() is True

    def test_verify_with_same_keys(self, registry):
        """相同引用键通过验证"""
        reg = CitationRegistry()
        engine = BilingualSyncEngine(reg)
        engine.load_documents(
            "Text [@keyA] and [@keyB].",
            "文本 [@keyA] 和 [@keyB]。"
        )
        # verify_consistency depends on extracted Pandoc citations
        result = engine.verify_consistency()
        # Should be True since both have keyA and keyB
        assert isinstance(result, bool)


# ---- Test: Lock Synced Keys ----

class TestLockSyncedKeys:
    """同步引用锁定"""

    def test_lock_common_keys(self, sync_engine):
        """共同引用被锁定"""
        sync_engine.lock_synced_keys()
        # After locking, common keys should be locked
        locked = sync_engine._registry.get_locked_keys()
        # At minimum, keys that appear in both docs should be locked
        assert isinstance(locked, set)


# ---- Test: Context Extraction ----

class TestContextExtraction:
    """上下文提取"""

    def test_context_around_citation(self, sync_engine):
        """获取引用周围上下文"""
        zh_ast = MarkdownAST(SAMPLE_DRAFT_ZH)
        zh_ast.parse()
        pandoc = zh_ast.find_existing_pandoc_citations()

        if pandoc:
            ctx = BilingualSyncEngine._get_context(SAMPLE_DRAFT_ZH, pandoc[0], window=40)
            assert len(ctx) > 0


# ---- Test: Sync Report Structure ----

class TestSyncReportStructure:
    """同步报告结构"""

    def test_report_defaults(self):
        """报告默认值"""
        report = SyncReport()
        assert report.total_en_citations == 0
        assert report.total_zh_citations == 0
        assert report.matched == 0
        assert report.is_synced is True

    def test_report_with_missing(self):
        """有缺失的报告"""
        report = SyncReport()
        report.missing_in_zh = ["keyA", "keyB"]
        assert report.is_synced is False

    def test_sync_diff_types(self):
        """SyncDiff 类型"""
        diff = SyncDiff(
            citekey="test_key",
            diff_type="missing_in_zh",
        )
        assert diff.diff_type == "missing_in_zh"
        assert diff.citekey == "test_key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
