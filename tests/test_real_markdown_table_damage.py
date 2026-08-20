"""
test_real_markdown_table_damage.py — Task 4: 真实 Markdown 表格保护测试

验证:
1. 表格引用默认阻止自动注入
2. 注入不产生断行
3. 管道符 | 数量不变
4. 表头不受影响
"""
import sys
import os
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import CitationPosition, MatchResult, MatchStrategy
from md_ast import MarkdownAST
from citation_registry import CitationRegistry
from injector import CitationInjector


SAMPLE_TABLE_DOC = """# Materials Comparison

## Performance Overview

| Material | Performance | Sensitivity | Reference |
|----------|-------------|-------------|-----------|
| PDMS | High | 85 kPa^-1 | [1] |
| Ecoflex | Medium | 45 kPa^-1 | [2] |
| Polyimide | Low | 12 kPa^-1 | [3] |

## Discussion

The results show PDMS has the best performance [4].
"""


class TestRealMarkdownTableDamage:
    """Task 4: 表格破坏防护测试"""

    def test_table_citation_blocked_by_default(self):
        """表格内引用默认被阻止"""
        ast = MarkdownAST(SAMPLE_TABLE_DOC)
        ast.parse()

        # 找表格内的引用
        static = ast.find_static_citations()
        table_cits = [c for c in static if c.is_in_table]
        body_cits = [c for c in static if not c.is_in_table]

        assert len(table_cits) > 0, "Should find citations inside table"
        assert len(body_cits) > 0, "Should find citations in body"

        # 默认: 表格引用不应被注入
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_TABLE_DOC)

        match = MatchResult(citekey="Paper2026", confidence=1.0,
                           strategy=MatchStrategy.MANUAL)

        # 只注入表格引用（不确认）
        injector.inject_candidates(
            [(table_cits[0], match)], auto_confirm=False)

        assert injector.has_table_citations(), \
            "Table citation should be DEFERRED (not injected)"

    def test_no_line_breaks_after_table_injection(self):
        """表格注入不产生断行"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_TABLE_DOC)

        # 手动构造正文引用注入（不触碰表格）
        ast = MarkdownAST(SAMPLE_TABLE_DOC)
        ast.parse()
        body_cits = [c for c in ast.find_static_citations() if not c.is_in_table]

        if body_cits:
            match = MatchResult(citekey="BodyPaper2026", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            result = injector.inject_candidates(
                [(body_cits[0], match)], auto_confirm=True)

            # 检查表格行数不变
            original_table_lines = [l for l in SAMPLE_TABLE_DOC.split('\n') if '|' in l]
            result_table_lines = [l for l in result.split('\n') if '|' in l]
            assert len(original_table_lines) == len(result_table_lines), \
                "Table line count should not change"

    def test_pipe_count_preserved(self):
        """每行的管道符数量不变"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_TABLE_DOC)

        ast = MarkdownAST(SAMPLE_TABLE_DOC)
        ast.parse()
        body_cits = [c for c in ast.find_static_citations() if not c.is_in_table]

        if body_cits:
            match = MatchResult(citekey="BodyPaper2026", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            result = injector.inject_candidates(
                [(body_cits[0], match)], auto_confirm=True)

            original_lines = SAMPLE_TABLE_DOC.split('\n')
            result_lines = result.split('\n')

            for i, (orig, res) in enumerate(zip(original_lines, result_lines)):
                if '|' in orig:
                    assert orig.count('|') == res.count('|'), \
                        f"Line {i+1}: pipe count changed from {orig.count('|')} to {res.count('|')}"

    def test_table_header_preserved(self):
        """表头完全不变"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_TABLE_DOC)

        ast = MarkdownAST(SAMPLE_TABLE_DOC)
        ast.parse()
        body_cits = [c for c in ast.find_static_citations() if not c.is_in_table]

        if body_cits:
            match = MatchResult(citekey="BodyPaper2026", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            result = injector.inject_candidates(
                [(body_cits[0], match)], auto_confirm=True)

            # 表头行
            header_line = "| Material | Performance | Sensitivity | Reference |"
            assert header_line in result, "Table header must be preserved exactly"

            # 分隔行
            separator = "|----------|-------------|-------------|-----------|"
            assert separator in result, "Table separator must be preserved exactly"

    def test_table_content_rows_preserved(self):
        """表格数据行不变"""
        injector = CitationInjector(CitationRegistry())
        injector.set_document(SAMPLE_TABLE_DOC)

        ast = MarkdownAST(SAMPLE_TABLE_DOC)
        ast.parse()
        body_cits = [c for c in ast.find_static_citations() if not c.is_in_table]

        if body_cits:
            match = MatchResult(citekey="BodyPaper2026", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            result = injector.inject_candidates(
                [(body_cits[0], match)], auto_confirm=True)

            for row in ["| PDMS | High | 85 kPa^-1 |", "| Ecoflex | Medium | 45 kPa^-1 |"]:
                assert row in result, f"Table row must be preserved: '{row}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
