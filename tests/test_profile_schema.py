"""test_profile_schema.py — v2.4: Profile schema validation"""
import sys, os, pytest

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENGINE_DIR)

from policy_manager import PolicyManager, PolicyError, get_policy

PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")


@pytest.fixture(autouse=True)
def reset():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


class TestSchemaValidation:
    def test_valid_profile_loads(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        assert pm.profile_name == "advanced_materials_review"

    def test_profile_has_required_sections(self):
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)
        for section in ["if_gate", "review_paper", "density", "zones", "semantic"]:
            assert pm.get_rule(section) is not None, f"Missing section: {section}"

    def test_all_profiles_valid(self):
        pm = get_policy()
        for name in ["default", "advanced_materials_review", "nature_review"]:
            pm.load_profile(name, PROFILES_DIR)
            assert pm.profile_name == name

    def test_corrupted_yaml_falls_back(self):
        """Missing profile → safe fallback to default"""
        pm = get_policy()
        pm.load_profile("nonexistent_profile_xyz", PROFILES_DIR)
        assert pm.profile_name == "default"
        assert pm.body_if_enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
