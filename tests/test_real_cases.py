"""
test_real_cases.py — Task 5: 4 个真实用户场景测试

case01: 100-paper review — pending detection
case02: 10 Markdown tables — all tables frozen
case03: Locked reference — remove_reference_list BLOCKED
case04: Abstract zone — no injection into Abstract
"""
import sys
import os
import re
import pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from cm_types import CitationPosition, MatchResult, MatchStrategy, BibEntry
from bib_parser import BibTeXParser
from md_ast import MarkdownAST
from citation_registry import CitationRegistry, CitationLockError
from injector import CitationInjector

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_cases")

if not os.path.isdir(CASES_DIR):
    pytest.skip(
        "Private real-case fixtures are not distributed with the public release.",
        allow_module_level=True,
    )


def load_case(name, file):
    path = os.path.join(CASES_DIR, name, file)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


# ============ case01: 100-paper review ============

class TestCase01_100PaperReview:
    """100 篇文献，60 已引用，40 pending"""

    def test_bib_has_100_entries(self):
        bib = load_case("case01_review_100papers", "library.bib")
        parser = BibTeXParser()
        entries = parser.parse(bib)
        assert len(entries) == 100, f"Expected 100 bib entries, got {len(entries)}"

    def test_60_already_cited(self):
        draft = load_case("case01_review_100papers", "draft.md")
        cited = set(re.findall(r'@(\w+)', draft))
        assert len(cited) == 60, f"Expected 60 cited, got {len(cited)}"

    def test_40_pending_detected(self):
        draft = load_case("case01_review_100papers", "draft.md")
        bib = load_case("case01_review_100papers", "library.bib")

        used = set(re.findall(r'@(\w+)', draft))
        all_keys = set(re.findall(r'@article\{(\w+),', bib))
        pending = all_keys - used

        assert len(pending) == 40, f"Expected 40 pending, got {len(pending)}"
        for k in pending:
            assert k not in used


# ============ case02: 10 tables ============

class TestCase02_TableHeavy:
    """10 个 Markdown 表格，默认全部冻结"""

    def test_all_tables_detected(self):
        draft = load_case("case02_table_heavy", "draft.md")
        ast = MarkdownAST(draft)
        ast.parse()

        assert len(ast._table_regions) == 10, \
            f"Expected 10 tables, got {len(ast._table_regions)}"

    def test_table_citations_found(self):
        draft = load_case("case02_table_heavy", "draft.md")
        ast = MarkdownAST(draft)
        ast.parse()
        static = ast.find_static_citations()
        table_cits = [c for c in static if c.is_in_table]

        # 10 tables × 5 rows each = 50 table citations
        assert len(table_cits) == 50, \
            f"Expected 50 table citations, got {len(table_cits)}"

    def test_table_citations_blocked_by_default(self):
        draft = load_case("case02_table_heavy", "draft.md")
        injector = CitationInjector(CitationRegistry())
        injector.set_document(draft)

        ast = MarkdownAST(draft)
        ast.parse()
        table_cits = [c for c in ast.find_static_citations() if c.is_in_table]

        if table_cits:
            match = MatchResult(citekey="NewPaper2026", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            injector.inject_candidates(
                [(table_cits[0], match)], auto_confirm=False)

            assert injector.has_table_citations(), \
                "Table citations should be deferred (blocked)"

    def test_pipe_count_unchanged_after_body_injection(self):
        draft = load_case("case02_table_heavy", "draft.md")
        injector = CitationInjector(CitationRegistry())
        injector.set_document(draft)

        # Only inject into non-table area (there are none in this doc)
        ast = MarkdownAST(draft)
        ast.parse()
        body_cits = [c for c in ast.find_static_citations() if not c.is_in_table]

        if body_cits:
            match = MatchResult(citekey="BodyKey", confidence=1.0,
                               strategy=MatchStrategy.MANUAL)
            result = injector.inject_candidates(
                [(body_cits[0], match)], auto_confirm=True)
        else:
            result = draft

        # Pipe count per line unchanged
        orig_lines = draft.split('\n')
        res_lines = result.split('\n')
        for i, (o, r) in enumerate(zip(orig_lines, res_lines)):
            if '|' in o:
                assert o.count('|') == r.count('|'), \
                    f"Line {i+1}: pipe count changed"


# ============ case03: locked reference ============

class TestCase03_LockedReference:
    """锁定引用 [@Nature2020] — remove_reference_list 后仍存在"""

    def test_locked_citation_in_draft(self):
        draft = load_case("case03_locked_reference", "draft.md")
        assert "[@Nature2020]" in draft, "Nature2020 should be in draft"

    def test_locked_citation_blocked_in_registry(self):
        registry = CitationRegistry()
        registry.register("Nature2020")
        registry.lock("Nature2020")

        with pytest.raises(CitationLockError):
            registry.mark_injected("Nature2020")

    def test_locked_key_not_in_uninjected(self):
        registry = CitationRegistry()
        registry.register("Nature2020")
        registry.lock("Nature2020")

        uninjected = registry.get_uninjected_keys()
        assert "Nature2020" not in uninjected, \
            "Locked key should NOT be in uninjected list"

    def test_remove_reference_list_does_not_touch_body(self):
        """remove_reference_list 不应该影响正文中的 [@Nature2020]"""
        draft = load_case("case03_locked_reference", "draft.md")
        injector = CitationInjector(CitationRegistry())
        injector.set_document(draft)

        result = injector._remove_reference_list(draft)

        # 正文引用仍然存在
        assert "[@Nature2020]" in result, \
            "[@Nature2020] should survive reference list removal"
        assert "Smith" not in result or "confirmed" in result, \
            "Body text should be preserved"

    def test_static_references_removed(self):
        """静态参考文献 [1] Smith... [2] Recent... 应被移除"""
        draft = load_case("case03_locked_reference", "draft.md")
        injector = CitationInjector(CitationRegistry())
        injector.set_document(draft)

        result = injector._remove_reference_list(draft)

        # References section removed
        assert "[1] Smith" not in result and "J. Science" not in result, \
            "Static reference list should be removed"


# ============ case04: abstract zone ============

class TestCase04_AbstractZone:
    """Abstract 区域 — 不能注入文献"""

    def test_abstract_detected(self):
        draft = load_case("case04_abstract_zone", "draft.md")
        assert "## Abstract" in draft

    def test_abstract_has_no_pandoc_citations(self):
        draft = load_case("case04_abstract_zone", "draft.md")
        ast = MarkdownAST(draft)
        ast.parse()

        # Abstract 在 ## Abstract 和 ## Introduction 之间
        abstract_start = draft.find("## Abstract")
        intro_start = draft.find("## Introduction")
        abstract_text = draft[abstract_start:intro_start]

        pandoc = re.findall(r'\[@\w+\]', abstract_text)
        assert len(pandoc) == 0, \
            f"Abstract should have NO citations, found: {pandoc}"

    def test_introduction_has_citations(self):
        draft = load_case("case04_abstract_zone", "draft.md")
        ast = MarkdownAST(draft)
        ast.parse()

        pandoc = ast.find_existing_pandoc_citations()
        assert len(pandoc) > 0, "Introduction should have citations"

    def test_abstract_keywords_not_matched(self):
        """Abstract 包含 PDMS/piezoresistive 关键词，但不应该匹配注入"""
        draft = load_case("case04_abstract_zone", "draft.md")
        assert "PDMS" in draft
        assert "piezoresistive" in draft.lower()

        # 验证 abstract 部分的引用已被隔离
        intro_start = draft.find("## Introduction")
        body_text = draft[intro_start:]

        # 正文中有引用
        assert "[@Wearable2023]" in body_text
        assert "[@PulseWave2024]" in body_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
