"""test_advanced_materials_profile.py — v2.3.1: Final production profile validation"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, get_policy, PolicyError

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


@pytest.fixture
def profile():
    pm = get_policy()
    pm.load_profile("advanced_materials_review", PROFILES_DIR)
    return pm


class TestIFGate:
    def test_body_if_enabled(self, profile):
        assert profile.body_if_enabled is True

    def test_body_if_threshold_6(self, profile):
        assert profile.body_if_threshold == 6

    def test_table_if_enabled(self, profile):
        assert profile.table_if_enabled is True

    def test_table_elite_threshold_10(self, profile):
        assert profile.table_if_threshold == 10


class TestReviewRouting:
    def test_review_introduction_only(self, profile):
        assert profile.review_intro_only is True

    def test_review_forbidden_quantitative(self, profile):
        assert profile.review_forbidden_quantitative is True

    def test_review_not_forbidden_results(self, profile):
        assert profile.review_forbidden_results is False


class TestCitationDensity:
    def test_sentence_max_5(self, profile):
        assert profile.sentence_max_citations == 5

    def test_paragraph_normal_12(self, profile):
        assert profile.paragraph_normal_max == 12

    def test_paragraph_review_18(self, profile):
        assert profile.paragraph_review_max == 18


class TestZoneProtection:
    def test_abstract_no_new_citations(self, profile):
        assert profile.abstract_new_citation is False

    def test_figure_migrate_existing(self, profile):
        assert profile.figure_migrate_existing is True

    def test_figure_no_new_injection(self, profile):
        assert profile.figure_allow_new is False

    def test_table_elite_gate(self, profile):
        rules = profile.get_zone_rules("table")
        assert rules.get("elite_if_gate") is True

    def test_code_block_no_injection(self, profile):
        rules = profile.get_zone_rules("code_block")
        assert rules.get("allow_injection") is False


class TestSemantic:
    def test_min_similarity(self, profile):
        assert profile.min_similarity == 0.15

    def test_rejected_sections(self, profile):
        sections = profile.rejected_sections
        assert "abstract" in sections
        assert "摘要" in sections

    def test_this_work_patterns(self, profile):
        patterns = profile.this_work_patterns
        assert "this work" in patterns
        assert "we propose" in patterns


class TestFullProfileValidation:
    def test_all_production_rules_present(self, profile):
        """Every required production rule is configured"""
        rules = {
            "if_gate.body.enabled": True,
            "if_gate.body.default_threshold": 6,
            "if_gate.table.default_threshold": 10,
            "review_paper.introduction_only": True,
            "density.sentence.max": 5,
            "density.paragraph.normal_max": 12,
            "density.paragraph.review_max": 18,
            "zones.abstract.new_citation": False,
            "zones.figure_caption.migrate_existing": True,
            "zones.figure_caption.allow_new_injection": False,
        }
        for path, expected in rules.items():
            actual = profile.get_rule(path)
            assert actual == expected, f"{path}: expected {expected}, got {actual}"

    def test_profile_loads_without_errors(self, profile):
        assert profile.profile_name == "advanced_materials_review"

    def test_summary_contains_key_info(self, profile):
        s = profile.summary()
        assert "advanced_materials_review" in s
        assert "threshold=6" in s
        assert "threshold=10" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
