"""test_crossref_guard.py — v2.5: Cross-reference protection"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from crossref_guard import is_crossref, filter_crossrefs, merge_adjacent_citations


class TestIsCrossref:
    def test_fig_prefix(self):
        assert is_crossref("fig:diagram1") is True
        assert is_crossref("@fig:diagram1") is True

    def test_tbl_prefix(self):
        assert is_crossref("tbl:results") is True

    def test_eq_prefix(self):
        assert is_crossref("eq:einstein") is True

    def test_citation_is_not_crossref(self):
        assert is_crossref("Key2024") is False
        assert is_crossref("@Key2024") is False


class TestFilterCrossrefs:
    def test_mixed_block(self):
        citations, crossrefs = filter_crossrefs("[@KeyA; @fig:1; @KeyB]")
        assert "KeyA" in citations
        assert "KeyB" in citations
        assert "fig:1" in crossrefs


class TestMergeAdjacent:
    def test_merges_adjacent(self):
        text = "Text [@KeyA] [@KeyB]."
        result = merge_adjacent_citations(text)
        assert "[@KeyA; @KeyB]" in result

    def test_does_not_merge_crossref(self):
        text = "See [@KeyA] [@fig:1]."
        result = merge_adjacent_citations(text)
        assert "[@KeyA] [@fig:1]" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
