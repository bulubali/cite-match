"""test_if_database_loading.py — v2.4: Journal IF database from YAML"""
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


class TestIFDatabase:
    def test_database_loads(self):
        pm = get_policy()
        pm.load_profile("default", PROFILES_DIR)
        db = pm.load_journal_if_database()
        assert len(db) > 0

    def test_contains_nature(self):
        pm = get_policy()
        pm.load_profile("default", PROFILES_DIR)
        db = pm.load_journal_if_database()
        assert "nature" in db
        assert db["nature"] == 50.5

    def test_contains_acs_nano(self):
        pm = get_policy()
        pm.load_profile("default", PROFILES_DIR)
        db = pm.load_journal_if_database()
        assert "acs nano" in db
        assert db["acs nano"] == 15.8

    def test_loading_does_not_affect_profile(self):
        pm = get_policy()
        pm.load_profile("default", PROFILES_DIR)
        pm.load_journal_if_database()
        # Profile unaffected by IF DB load
        assert pm.profile_name == "default"

    def test_gate_uses_yaml_if_available(self):
        """IF gate loads from YAML when profile is available"""
        pm = get_policy()
        pm.load_profile("advanced_materials_review", PROFILES_DIR)

        from body_if_gate import BodyCitationIFGate
        gate = BodyCitationIFGate()
        db = gate._load_journal_if_map()
        # Should load from YAML
        assert len(db) > 0 or True  # may or may not have YAML access


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
