"""test_policy_manager.py — v2.3: Policy Manager core tests"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, PolicyError, get_policy

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset_policy():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


@pytest.fixture
def pm():
    return PolicyManager()


class TestPolicyLoading:
    def test_load_default_profile(self, pm):
        pm.load_profile("default", PROFILES_DIR)
        assert pm.profile_name == "default"

    def test_load_advanced_materials_review(self, pm):
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        assert pm.profile_name == "advanced_materials_review"

    def test_load_nature_review(self, pm):
        pm.load_profile("nature_review", PROFILES_DIR)
        assert pm.profile_name == "nature_review"

    def test_load_nonexistent_falls_back_to_default(self, pm):
        """v2.4: nonexistent profile → safe fallback to default.yaml"""
        pm.load_profile("nonexistent", PROFILES_DIR)
        # Should have loaded default.yaml instead
        assert pm.profile_name == "default"
        assert pm.body_if_enabled is False  # default has IF disabled

    def test_load_dict(self, pm):
        data = {
            "profile": {"name": "test", "version": "1.0"},
            "if_gate": {"body": {"enabled": True, "threshold": 5}, "table": {"enabled": False, "threshold": 0}},
            "review_paper": {"introduction_only": False, "forbidden_in_quantitative_claims": False, "forbidden_in_results": False},
            "density": {"sentence": {"max": 3}, "paragraph": {"normal_max": 8, "review_max": 18}},
            "zones": {"abstract": {"new_citation": False}, "figure_caption": {"migrate_existing": True, "allow_new_injection": False}, "table": {"migrate_existing": True, "elite_if_gate": False}, "code_block": {"allow_injection": False, "allow_migration": False}},
            "semantic": {"min_similarity_threshold": 0.2, "rejected_sections": ["abstract"], "this_work_patterns": ["this work"]},
            "sections": {"introduction_keywords": ["intro"], "results_keywords": ["results"], "quantitative_claim_patterns": ["\\d+ kPa"]},
            "contribution_routing": {"material": ["material"]},
        }
        pm.load_profile_dict(data)
        assert pm.profile_name == "inline"


class TestRuleAccess:
    @pytest.fixture(autouse=True)
    def setup(self, pm):
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

    def test_get_rule_dot_path(self, pm):
        assert pm.get_rule("if_gate.body.default_threshold") == 6
        assert pm.get_rule("if_gate.table.default_threshold") == 10
        assert pm.get_rule("density.sentence.max") == 5

    def test_get_rule_default(self, pm):
        assert pm.get_rule("nonexistent.path", 999) == 999

    def test_body_if_enabled(self, pm):
        assert pm.body_if_enabled is True

    def test_table_if_enabled(self, pm):
        assert pm.table_if_enabled is True

    def test_review_intro_only(self, pm):
        assert pm.review_intro_only is True

    def test_sentence_max(self, pm):
        assert pm.sentence_max_citations == 5

    def test_figure_zone_rules(self, pm):
        assert pm.figure_migrate_existing is True
        assert pm.figure_allow_new is False

    def test_min_similarity(self, pm):
        assert pm.min_similarity == 0.15


class TestProfileDefaults:
    def test_default_no_if_gate(self, pm):
        pm.load_profile("default", PROFILES_DIR)
        assert pm.body_if_enabled is False
        assert pm.table_if_enabled is False

    def test_default_review_not_restricted(self, pm):
        pm.load_profile("default", PROFILES_DIR)
        assert pm.review_intro_only is False

    def test_nature_strict(self, pm):
        pm.load_profile("nature_review", PROFILES_DIR)
        assert pm.body_if_threshold == 15
        assert pm.table_if_threshold == 20
        assert pm.review_forbidden_results is True
        assert pm.sentence_max_citations == 2


class TestConvenienceAccessors:
    @pytest.fixture(autouse=True)
    def setup(self, pm):
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

    def test_section_keywords(self, pm):
        kw = pm.get_section_keywords("introduction")
        assert "introduction" in kw

    def test_contribution_routing(self, pm):
        kw = pm.get_contribution_routing("material")
        assert "piezoelectric" in kw

    def test_zone_rules(self, pm):
        rules = pm.get_zone_rules("abstract")
        assert rules["new_citation"] is False

    def test_summary(self, pm):
        s = pm.summary()
        assert "advanced_materials_review" in s
        assert "threshold=6" in s


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
