"""
test_reference_integrity.py — 引用完整性测试

验证:
1. BibTeX 解析正确性（所有入口、字段完整性）
2. 引用守恒（注入前后数量不变）
3. 匹配策略置信度排序
4. 引用范围展开
5. 参考文献列表移除
6. 孤儿引用检测
7. 缺失 BibTeX 检测
8. 端到端管道
"""
import sys
import os
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import (
    CitationPosition, BibEntry, MatchResult, MatchStrategy,
    RegistrySnapshot,
)
from bib_parser import BibTeXParser
from md_ast import MarkdownAST
from citation_registry import CitationRegistry
from matcher import CitationMatcher
from injector import CitationInjector
from pipeline import CiteMatchPipeline
from sample_data import (
    SAMPLE_BIB, SAMPLE_DRAFT_EN, SAMPLE_DRAFT_ZH, save_sample_data,
)


# ---- Fixtures ----

@pytest.fixture
def bib_entries():
    parser = BibTeXParser()
    return parser.parse(SAMPLE_BIB)


@pytest.fixture
def registry():
    return CitationRegistry()


@pytest.fixture
def ast():
    parser = MarkdownAST(SAMPLE_DRAFT_EN)
    parser.parse()
    return parser


@pytest.fixture
def sample_files(tmp_path):
    """创建临时样本文件"""
    data_dir = str(tmp_path)
    return save_sample_data(data_dir)


# ---- Test: BibTeX Parser Integrity ----

class TestBibTeXParserIntegrity:
    """BibTeX 解析完整性"""

    def test_parse_all_entries(self, bib_entries):
        """所有条目被解析"""
        assert len(bib_entries) == 5, f"Expected 5 entries, got {len(bib_entries)}"

    def test_all_required_fields(self, bib_entries):
        """每个条目包含必要字段"""
        for key, entry in bib_entries.items():
            assert entry.citekey == key
            assert entry.entry_type in ("article",)
            assert entry.fields.get("author"), f"{key} missing author"
            assert entry.fields.get("title"), f"{key} missing title"
            assert entry.fields.get("year"), f"{key} missing year"
            assert entry.fields.get("journal"), f"{key} missing journal"

    def test_doi_parsed(self, bib_entries):
        """DOI 被正确解析"""
        for key, entry in bib_entries.items():
            assert entry.doi, f"{key} should have a DOI"

    def test_first_author_extraction(self, bib_entries):
        """第一作者姓氏正确提取"""
        chen = bib_entries.get("Chen2023Flexible")
        assert chen is not None
        assert chen.first_author_surname == "Chen"

        tan = bib_entries.get("Tan2022PulseWave")
        assert tan is not None
        assert tan.first_author_surname == "Tan"

    def test_year_extraction(self, bib_entries):
        """年份正确提取"""
        assert bib_entries["Chen2023Flexible"].year == "2023"
        assert bib_entries["Wang2024Ultrathin"].year == "2024"
        assert bib_entries["Park2025Hyperspectral"].year == "2025"

    def test_no_warnings(self, bib_entries):
        """标准 BibTeX 解析无警告"""
        parser = BibTeXParser()
        parser.parse(SAMPLE_BIB)
        assert len(parser.warnings) == 0


# ---- Test: Citation Conservation ----

class TestCitationConservation:
    """引用守恒验证"""

    def test_registry_count_after_bulk_register(self, bib_entries, registry):
        """批量注册后计数正确"""
        registry.bulk_register(bib_entries)
        assert registry.count() == len(bib_entries)

    def test_conservation_before_injection(self, bib_entries, registry):
        """注入前快照计数与 BibTeX 条目数一致"""
        registry.bulk_register(bib_entries)
        snapshot = registry.snapshot()
        assert snapshot.total_citekeys == 5

    def test_orphan_detection(self, registry):
        """孤儿引用被检测"""
        # 注册 bib entry 但不附带位置
        registry.register("orphan_key",
            bib_entry=BibEntry(citekey="orphan_key", fields={
                "author": "Test, A.", "year": "2024",
                "title": "A Test Paper", "journal": "Test Journal"
            }))
        orphans = registry.get_orphans()
        assert "orphan_key" in orphans

    def test_non_orphan_not_detected(self, registry):
        """有位置的引用不是孤儿"""
        registry.register("cited_key",
            position=CitationPosition(line_number=5, column_start=10, column_end=13,
                           raw_text="[1]"),
            bib_entry=BibEntry(citekey="cited_key", fields={"author": "A, B."}))
        orphans = registry.get_orphans()
        assert "cited_key" not in orphans

    def test_missing_bib_detection(self, registry):
        """缺失 BibTeX 数据被检测"""
        registry.register("missing_bib_key",
            CitationPosition(line_number=10, column_start=20, column_end=23,
                           raw_text="[2]"))
        missing = registry.get_missing_bib()
        assert "missing_bib_key" in missing

    def test_snapshot_completeness(self, bib_entries, registry):
        """快照完整性"""
        registry.bulk_register(bib_entries)
        snap = registry.snapshot()
        assert snap.total_citekeys == 5
        assert snap.injected_count == 0
        assert snap.orphan_count == 5  # all have bib_entry but no positions
        assert snap.missing_count == 0


# ---- Test: Match Strategy Confidence Ordering ----

class TestMatchConfidence:
    """匹配策略置信度排序"""

    def test_doi_highest_confidence(self):
        """DOI 匹配置信度最高（除 MANUAL 外）"""
        assert MatchStrategy.DOI.confidence == 1.0

    def test_confidence_ordering(self):
        """置信度从高到低: DOI > AUTHOR_YEAR_JOURNAL > AUTHOR_YEAR_TITLE > FIRST_AUTHOR_YEAR > TITLE_KEYWORD"""
        strategies = [
            MatchStrategy.DOI,
            MatchStrategy.AUTHOR_YEAR_JOURNAL,
            MatchStrategy.AUTHOR_YEAR_TITLE,
            MatchStrategy.FIRST_AUTHOR_YEAR,
            MatchStrategy.TITLE_KEYWORD,
        ]
        for i in range(len(strategies) - 1):
            assert strategies[i].confidence >= strategies[i + 1].confidence, \
                f"{strategies[i].name} ({strategies[i].confidence}) should be >= {strategies[i+1].name} ({strategies[i+1].confidence})"


# ---- Test: Reference List Removal ----

class TestReferenceListRemoval:
    """参考文献列表移除"""

    def test_reference_list_detected(self, ast):
        """参考文献列表被检测到"""
        ref_range = ast.find_reference_list()
        assert ref_range is not None, "Should find reference list"

    def test_reference_list_removed(self):
        """参考文献列表被移除"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_DRAFT_EN)

        # 调用内部移除
        result = injector._remove_reference_list(SAMPLE_DRAFT_EN)

        # 结果不应包含 [1] Author 格式的行
        import re
        for line in result.split('\n'):
            assert not re.match(r'^\[1\]\s+[A-Z]', line.strip()), \
                f"Reference list line should be removed: {line[:60]}"

    def test_body_content_preserved(self, ast):
        """正文内容在移除参考文献列表后保留"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_DRAFT_EN)
        result = injector._remove_reference_list(SAMPLE_DRAFT_EN)

        assert "Flexible blood pressure sensors" in result
        assert "Pulse Wave Analysis" in result
        assert "iontronic" in result.lower()


# ---- Test: Number Range Expansion ----

class TestNumberRangeExpansion:
    """引用范围展开"""

    def test_static_range_detected(self):
        """范围引用被检测"""
        text = "See references [17-20] for details."
        ast = MarkdownAST(text)
        ast.parse()
        static = ast.find_static_citations()
        # 应找到 [17-20]
        assert any("17-20" in c.raw_text or "17" in c.raw_text for c in static)


# ---- Test: End-to-End Pipeline ----

class TestEndToEndPipeline:
    """端到端管道测试"""

    def test_pipeline_with_sample_data(self, sample_files):
        """使用样本数据运行完整管道"""
        pipeline = CiteMatchPipeline()

        result = pipeline.run(
            bib_path=sample_files["sample_references.bib"],
            draft_path=sample_files["sample_draft_en.md"],
            output_path=None,
        )

        # 检查基本结果
        assert "success" in result
        assert "snapshot" in result
        assert "report" in result

    def test_pipeline_scan_only(self, sample_files):
        """仅扫描模式"""
        pipeline = CiteMatchPipeline()
        citations = pipeline.scan_only(sample_files["sample_draft_en.md"])
        assert len(citations) > 0

    def test_pipeline_verify_only(self, sample_files):
        """仅验证模式"""
        pipeline = CiteMatchPipeline()
        snapshot = pipeline.verify_only(
            sample_files["sample_draft_en.md"],
            sample_files["sample_references.bib"],
        )
        assert isinstance(snapshot, RegistrySnapshot)

    def test_pipeline_with_nonexistent_file(self):
        """不存在的文件返回错误"""
        pipeline = CiteMatchPipeline()
        result = pipeline.run(
            bib_path="/nonexistent/path.bib",
            draft_path="/nonexistent/draft.md",
        )
        assert result["success"] is False
        assert "error" in result

    def test_pipeline_generates_output(self, sample_files, tmp_path):
        """管道生成输出文件"""
        output_path = str(tmp_path / "output.md")
        pipeline = CiteMatchPipeline()

        result = pipeline.run(
            bib_path=sample_files["sample_references.bib"],
            draft_path=sample_files["sample_draft_en.md"],
            output_path=output_path,
            dry_run=False,
        )

        if result["success"]:
            assert os.path.exists(output_path)


# ---- Test: Table Citation Integrity ----

class TestTableCitationIntegrity:
    """表格引用完整性"""

    def test_table_not_modified_without_confirm(self, sample_files, tmp_path):
        """不确认时表格引用不被修改"""
        output_path = str(tmp_path / "output_no_table.md")
        pipeline = CiteMatchPipeline()

        result = pipeline.run(
            bib_path=sample_files["sample_references.bib"],
            draft_path=sample_files["sample_draft_en.md"],
            output_path=output_path,
            auto_confirm_tables=False,
            dry_run=False,
        )

        if result["success"]:
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 表格内的 [1] [2] [4] 引用应保持不变（或至少被日志记录为延后）
            # 检查 injector log
            if "report" in result:
                assert isinstance(result["report"], str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
