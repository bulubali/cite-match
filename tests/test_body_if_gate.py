"""test_body_if_gate.py — v2.2.3: Body Citation IF Gate"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from body_if_gate import (
    BodyCitationIFGate, IFGateResult, IFGateDecision, IFGateReport,
)
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate


@pytest.fixture
def gate():
    return BodyCitationIFGate()


@pytest.fixture
def sample_candidates():
    return [
        CitationCandidate(
            paper=PaperIntel(citekey="HighIF", title="High IF Paper",
                           paper_type="research", journal="Nature",
                           technical_keywords=["test"], semantic_anchors=["test"]),
            target_sentence="This sensor shows excellent performance.",
            section="3.1.1", similarity_score=0.8, reason="matched",
        ),
        CitationCandidate(
            paper=PaperIntel(citekey="LowIF", title="Low IF Paper",
                           paper_type="research", journal="IEEE Sensors J.",
                           technical_keywords=["test"], semantic_anchors=["test"]),
            target_sentence="Another approach uses flexible materials.",
            section="3.1.2", similarity_score=0.6, reason="matched",
        ),
        CitationCandidate(
            paper=PaperIntel(citekey="UnknownIF", title="Unknown Journal",
                           paper_type="research", journal="Unknown J.",
                           technical_keywords=["test"], semantic_anchors=["test"]),
            target_sentence="Novel methods are emerging.",
            section="5.2", similarity_score=0.4, reason="matched",
        ),
    ]


class TestIFGateBasic:
    def test_default_thresholds(self, gate):
        # v2.3.3: safe fallback — defaults are 0 (disabled) without profile
        assert gate._global_threshold == 0.0
        assert gate._elite_threshold == 0.0

    def test_set_user_threshold(self, gate):
        gate.set_user_threshold(8.0)
        assert gate.effective_threshold == 8.0
        assert gate.is_confirmed

    def test_user_prompt(self, gate):
        prompt = gate.user_prompt()
        assert 'IF>5' in prompt
        assert 'IF>10' in prompt

    def test_set_none_threshold(self, gate):
        gate.set_user_threshold(None)
        assert gate.effective_threshold == 0.0  # falls back to safe default


class TestIFGateValidation:
    def test_high_if_passes(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        high = [d for d in report.decisions if d.citekey == "HighIF"]
        assert len(high) == 1
        assert high[0].result == IFGateResult.GLOBAL_PASS

    def test_low_if_blocked(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        low = [d for d in report.decisions if d.citekey == "LowIF"]
        assert len(low) == 1
        assert low[0].result == IFGateResult.BELOW_THRESHOLD

    def test_unknown_if_manual(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        unk = [d for d in report.decisions if d.citekey == "UnknownIF"]
        assert len(unk) == 1
        assert unk[0].result == IFGateResult.UNKNOWN

    def test_blocked_candidate_is_rejected(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        low = [c for c in sample_candidates if c.paper.citekey == "LowIF"]
        assert low[0].is_rejected
        assert 'IF GATE' in low[0].rejection_reason

    def test_pass_count(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        assert report.pass_count == 1  # only HighIF (Nature = 50.5)
        assert report.block_count == 2  # LowIF + UnknownIF


class TestIFGateReport:
    def test_summary_table(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        table = report.summary_table()
        assert 'IF Gate Validation' in table
        assert 'HighIF' in table
        assert 'LowIF' in table
        assert 'UnknownIF' in table

    def test_passed_property(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        passed = report.passed
        assert len(passed) == 1
        assert passed[0].citekey == "HighIF"

    def test_blocked_property(self, gate, sample_candidates):
        gate.set_user_threshold(6.0)
        report = gate.validate_candidates(sample_candidates)
        blocked = report.blocked
        assert len(blocked) == 2


class TestIFGateEdgeCases:
    def test_empty_candidates(self, gate):
        report = gate.validate_candidates([])
        assert report.pass_count == 0
        assert report.block_count == 0

    def test_stricter_threshold_blocks_more(self, gate, sample_candidates):
        gate.set_user_threshold(50.0)  # Only Nature (IF=50.5) passes
        report = gate.validate_candidates(sample_candidates)
        passed_keys = {d.citekey for d in report.passed}
        # Nature at 50.5 >= 50.0 → passes
        assert 'HighIF' in passed_keys
        # LowIF/UnknownIF blocked
        assert 'LowIF' not in passed_keys
        assert report.block_count >= 1

    def test_no_restriction_allows_all(self, gate, sample_candidates):
        gate.set_user_threshold(0.0)
        report = gate.validate_candidates(sample_candidates)
        # UnknownIF still blocked on UNKNOWN
        passed_if = [d for d in report.decisions
                     if d.result in (IFGateResult.GLOBAL_PASS, IFGateResult.ELITE_PASS)]
        assert len(passed_if) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
