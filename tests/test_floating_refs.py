"""test_floating_refs.py — Phase 4: Floating Reference Handler"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate
from floating_refs import FloatingRefHandler, FloatingReference


@pytest.fixture
def handler():
    return FloatingRefHandler()


@pytest.fixture
def sample_floaters():
    return [
        CitationCandidate(
            paper=PaperIntel(
                citekey="PaperA", title="Sensor A", paper_type="research",
                core_finding="Achieves 85 kPa^-1",
                technical_keywords=["piezoelectric", "sensitivity"],
                recommended_section="§3.1.1",
                authors="Smith, J. and Lee, K.", year="2024", journal="Adv. Mater.",
            ),
            is_rejected=True,
            rejection_reason="FLOATING — no suitable sentence",
            target_sentence="", section="", similarity_score=0.0, reason="",
        ),
        CitationCandidate(
            paper=PaperIntel(
                citekey="PaperB", title="Review B", paper_type="review",
                core_finding="Reviews BP monitoring advances",
                technical_keywords=["review", "wearable", "blood pressure"],
                recommended_section="§1",
                authors="Wang, X.", year="2023", journal="Nat. Rev.",
            ),
            is_rejected=True,
            rejection_reason="FLOATING — no anchor match",
            target_sentence="", section="", similarity_score=0.0, reason="",
        ),
    ]


class TestFloatingReference:
    def test_creation(self):
        p = PaperIntel(citekey="Test")
        f = FloatingReference(paper=p, reason="No match",
                             suggested_section="§1")
        assert f.paper.citekey == "Test"
        assert f.reason == "No match"

    def test_expansion_markers(self):
        p = PaperIntel(citekey="Test", title="Test Paper",
                       paper_type="research",
                       core_finding="Found X",
                       technical_keywords=["kw1"],
                       authors="Smith, J.", year="2024", journal="J.")
        f = FloatingReference(paper=p, reason="No match",
                             suggested_expansion="Some expansion text.",
                             suggested_section="§1")
        text = f.expansion_with_markers()
        assert "【AI扩写区开始】" in text
        assert "Some expansion text." in text
        assert "【AI扩写区结束】" in text


class TestFloatingRefHandler:
    def test_identify_floaters(self, handler, sample_floaters):
        floaters = handler.identify_floating_references(sample_floaters)
        assert len(floaters) == 2
        for f in floaters:
            assert isinstance(f, FloatingReference)
            assert f.paper is not None
            assert f.reason

    def test_only_rejected_become_floaters(self, handler):
        candidates = [
            CitationCandidate(
                paper=PaperIntel(citekey="Good"),
                is_rejected=False, target_sentence="ok", section="§1",
                similarity_score=0.5, reason="matched",
            ),
            CitationCandidate(
                paper=PaperIntel(citekey="Bad"),
                is_rejected=True, rejection_reason="No match",
                target_sentence="", section="", similarity_score=0.0, reason="",
            ),
        ]
        floaters = handler.identify_floating_references(candidates)
        assert len(floaters) == 1
        assert floaters[0].paper.citekey == "Bad"

    def test_generate_report(self, handler, sample_floaters, tmp_path):
        floaters = handler.identify_floating_references(sample_floaters)
        out = str(tmp_path / "floating.md")
        content = handler.generate_report(floaters, out)
        assert os.path.exists(out)
        assert "Floating Reference" in content
        assert "PaperA" in content
        assert "PaperB" in content
        assert "【AI扩写区开始】" in content

    def test_report_has_review_checklist(self, handler, sample_floaters):
        floaters = handler.identify_floating_references(sample_floaters)
        content = handler.generate_report(floaters, "")
        assert "Review Checklist" in content
        assert "确认注入" in content

    def test_count_property(self, handler, sample_floaters):
        handler.identify_floating_references(sample_floaters)
        assert handler.count == 2

    def test_empty_candidates(self, handler):
        floaters = handler.identify_floating_references([])
        assert len(floaters) == 0
        assert handler.count == 0

    def test_apply_approved_expansion_to_explicit_section(
        self, handler, tmp_path
    ):
        manuscript = (
            "# Abstract\nProtected summary.\n\n"
            "# Introduction\nExisting introduction.\n\n"
            "# Methods\nExisting methods.\n"
        )
        output = tmp_path / "expanded.md"

        result = handler.apply_confirmed_expansion(
            manuscript,
            "Approved expansion [@PaperA].",
            "Introduction",
            target_location="section_end",
            output_path=str(output),
        )

        assert result["status"] == "completed"
        assert result["output_path"] == str(output)
        assert output.read_text(encoding="utf-8") == result["manuscript"]
        assert result["manuscript"].index("Existing introduction.") < \
            result["manuscript"].index("Approved expansion")
        assert result["manuscript"].index("Approved expansion") < \
            result["manuscript"].index("# Methods")
        assert "Protected summary." in result["manuscript"]
        assert "Existing methods." in result["manuscript"]

    def test_apply_preserves_existing_ai_markers(self, handler):
        manuscript = "# Introduction\nExisting text.\n"
        approved = (
            "【AI扩写区开始】\nApproved text.\n【AI扩写区结束】"
        )

        result = handler.apply_confirmed_expansion(
            manuscript, approved, "Introduction"
        )

        assert result["status"] == "completed"
        assert result["manuscript"].count("【AI扩写区开始】") == 1
        assert result["manuscript"].count("【AI扩写区结束】") == 1
        assert approved in result["manuscript"]

    def test_apply_missing_section_is_blocked(self, handler):
        manuscript = "# Introduction\nExisting text.\n"

        result = handler.apply_confirmed_expansion(
            manuscript, "Approved text.", "Discussion"
        )

        assert result["status"] == "blocked"
        assert result["reason"] == "TARGET_SECTION_NOT_FOUND"
        assert result["manuscript"] == manuscript

    def test_apply_protected_section_is_blocked(self, handler):
        manuscript = "# Abstract\nProtected summary.\n"

        result = handler.apply_confirmed_expansion(
            manuscript, "Approved text.", "Abstract"
        )

        assert result["status"] == "blocked"
        assert result["reason"] == "PROTECTED_TARGET_SECTION"
        assert result["manuscript"] == manuscript

    def test_apply_does_not_generate_or_rematch(
        self, handler, monkeypatch
    ):
        manuscript = "# Discussion\nExisting text.\n"

        def forbidden(*args, **kwargs):
            raise AssertionError("apply interface must not generate or match")

        monkeypatch.setattr(handler, "_generate_expansion", forbidden)
        result = handler.apply_confirmed_expansion(
            manuscript, "Caller-approved exact text.", "Discussion"
        )

        assert result["status"] == "completed"
        assert "Caller-approved exact text." in result["manuscript"]

    def test_apply_ambiguous_section_is_blocked(self, handler):
        manuscript = (
            "# Discussion\nFirst.\n\n# Discussion\nSecond.\n"
        )

        result = handler.apply_confirmed_expansion(
            manuscript, "Approved text.", "Discussion"
        )

        assert result["status"] == "blocked"
        assert result["reason"] == "TARGET_SECTION_AMBIGUOUS"
        assert result["manuscript"] == manuscript


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
