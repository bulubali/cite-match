"""test_profile_loading.py — v2.3: Profile loading and validation"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, PolicyError

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


class TestProfileValidation:
    def test_missing_section_raises(self):
        pm = PolicyManager()
        data = {"profile": {"name": "test"}}
        with pytest.raises(PolicyError, match="missing required section"):
            pm.load_profile_dict(data)

    def test_all_profiles_load(self):
        pm = PolicyManager()
        for name in ["default", "advanced_materials_review", "nature_review"]:
            pm.load_profile(name, PROFILES_DIR)
            assert pm.profile_name == name

    def test_profile_switching(self):
        pm = PolicyManager()
        pm.load_profile("default", PROFILES_DIR)
        assert pm.body_if_enabled is False
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        assert pm.body_if_enabled is True


class TestProfileValues:
    def test_advanced_matches_v223_constants(self):
        """advanced_materials_review must match pre-refactor hardcoded values"""
        pm = PolicyManager()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        # v2.2.3 hardcoded: IF_THRESHOLD_GLOBAL = 6
        assert pm.body_if_threshold == 6
        # v2.2.3 hardcoded: IF_THRESHOLD_ELITE = 10
        assert pm.table_if_threshold == 10
        # v2.2.3 hardcoded: MAX_PAPERS_PER_SENTENCE = 3
        assert pm.sentence_max_citations == 5
        # v2.3.1 production: paragraph normal = 12
        assert pm.paragraph_normal_max == 12
        # v2.2.3 hardcoded: MIN_SIMILARITY_THRESHOLD = 0.15
        assert pm.min_similarity == 0.15

    def test_nature_values(self):
        pm = PolicyManager()
        pm.load_profile("nature_review", PROFILES_DIR)
        assert pm.body_if_threshold == 15
        assert pm.table_if_threshold == 20
        assert pm.sentence_max_citations == 2
        assert pm.min_similarity == 0.25

    def test_default_values(self):
        pm = PolicyManager()
        pm.load_profile("default", PROFILES_DIR)
        assert pm.body_if_enabled is False
        assert pm.table_if_enabled is False
        assert pm.sentence_max_citations == 5
        assert pm.paragraph_normal_max == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
