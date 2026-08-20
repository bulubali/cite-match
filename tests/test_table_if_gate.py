"""test_table_if_gate.py — v2.3.3: Table Citation IF Gate (stricter)"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, get_policy
from body_if_gate import BodyCitationIFGate, IFGateResult
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


@pytest.fixture
def gate():
    pm = get_policy()
    pm.load_profile("advanced_materials_review", PROFILES_DIR)
    return BodyCitationIFGate()


def make_candidate(citekey, journal, sentence, is_table=False):
    return CitationCandidate(
        paper=PaperIntel(citekey=citekey, title="Paper", paper_type="research",
                       journal=journal, technical_keywords=["t"], semantic_anchors=["t"]),
        target_sentence=("| Material | Ref |\n| PDMS | [1] |" if is_table
                        else "Body text about sensors."),
        section="3.1", similarity_score=0.5, reason="matched",
    )


class TestTableIFGate:
    def test_high_if_table_passes_elite(self, gate):
        """Table citation with IF>10 → ELITE_PASS"""
        gate.set_user_threshold(6.0)
        c = make_candidate("NatPaper", "Nature", "", is_table=True)
        report = gate.validate_candidates([c])
        d = report.decisions[0]
        assert d.gate_type == 'table'
        assert d.result == IFGateResult.ELITE_PASS

    def test_medium_if_table_blocked(self, gate):
        """Table citation with IF between 6-10 → BLOCKED (needs elite)"""
        gate.set_user_threshold(6.0)
        c = make_candidate("MidPaper", "ACS Sens.", "", is_table=True)  # IF=8.5 < 10
        report = gate.validate_candidates([c])
        d = report.decisions[0]
        assert d.gate_type == 'table'
        assert d.result == IFGateResult.BELOW_THRESHOLD

    def test_low_if_table_blocked(self, gate):
        """Table citation with low IF → BLOCKED"""
        gate.set_user_threshold(6.0)
        c = make_candidate("LowPaper", "IEEE Sensors J.", "", is_table=True)  # IF=4.5
        report = gate.validate_candidates([c])
        d = report.decisions[0]
        assert d.gate_type == 'table'
        assert d.result == IFGateResult.BELOW_THRESHOLD

    def test_table_uses_elite_threshold(self, gate):
        """Table gate uses elite threshold (10), not global (6)"""
        gate.set_user_threshold(6.0)

        # ACS Nano = 15.8 → passes ELITE (15.8 >= 10)
        c_pass = make_candidate("HighTab", "ACS Nano", "", is_table=True)
        report = gate.validate_candidates([c_pass])
        assert report.decisions[0].result == IFGateResult.ELITE_PASS

        # npj Flexible Electron. = 9.2 → fails ELITE (9.2 < 10)
        c_fail = make_candidate("MidTab", "npj Flexible Electron.", "", is_table=True)
        report2 = gate.validate_candidates([c_fail])
        assert report2.decisions[0].result == IFGateResult.BELOW_THRESHOLD

    def test_body_uses_global_threshold(self, gate):
        """Body citation uses global threshold (6)"""
        gate.set_user_threshold(6.0)

        # npj Flex Electron = 9.2 → passes GLOBAL (9.2 >= 6)
        c = make_candidate("BodyPaper", "npj Flexible Electron.", "Body text.")
        report = gate.validate_candidates([c])
        assert report.decisions[0].result == IFGateResult.GLOBAL_PASS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
