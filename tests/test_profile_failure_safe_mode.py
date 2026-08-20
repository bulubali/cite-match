"""test_profile_failure_safe_mode.py — v2.4: Safe failure → default.yaml"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, get_policy

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


class TestSafeFailureMode:
    def test_missing_profile_loads_default(self):
        """Nonexistent profile → default.yaml loaded"""
        pm = get_policy()
        pm.load_profile("does_not_exist_xyz", PROFILES_DIR)
        assert pm.profile_name == "default"

    def test_fallback_has_if_disabled(self):
        """Default fallback has IF gate disabled (safe)"""
        pm = get_policy()
        pm.load_profile("nonexistent_abc", PROFILES_DIR)
        assert pm.body_if_enabled is False
        assert pm.table_if_enabled is False

    def test_fallback_has_no_review_restriction(self):
        pm = get_policy()
        pm.load_profile("nonexistent_def", PROFILES_DIR)
        assert pm.review_intro_only is False

    def test_fallback_allows_writes(self):
        """Default fallback does NOT block all papers"""
        pm = get_policy()
        pm.load_profile("nope_ghi", PROFILES_DIR)
        assert pm.sentence_max_citations == 5
        assert pm.paragraph_normal_max == 12

    def test_explicit_default_still_works(self):
        """Loading default.yaml directly works"""
        pm = get_policy()
        pm.load_profile("default", PROFILES_DIR)
        assert pm.profile_name == "default"
        assert pm.body_if_enabled is False

    def test_switching_to_valid_profile_works(self):
        """After a failed load, switching to valid profile works"""
        pm = get_policy()
        pm.load_profile("nope_jkl", PROFILES_DIR)
        assert pm.profile_name == "default"
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        assert pm.profile_name == "advanced_materials_review"
        assert pm.body_if_enabled is True


class TestAdvancedMaterialsUnchanged:
    def test_advanced_materials_still_works(self):
        """advanced_materials_review behavior unchanged from v2.3.3"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        assert pm.body_if_enabled is True
        assert pm.body_if_threshold == 6
        assert pm.table_if_threshold == 10
        assert pm.review_intro_only is True
        assert pm.sentence_max_citations == 5
        assert pm.paragraph_normal_max == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
