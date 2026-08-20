"""test_section_classifier.py — v2.4: Section classifier from YAML"""
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


@pytest.fixture
def pm():
    p = get_policy()
    p.load_profile("advanced_materials_review", PROFILES_DIR)
    return p


class TestSectionClassifier:
    def test_loads_classifier(self, pm):
        classifier = pm.load_section_classifier()
        assert "languages" in classifier

    def test_en_abstract(self, pm):
        assert pm.get_section_type("Abstract", "en") == "abstract"
        assert pm.get_section_type("ABSTRACT", "en") == "abstract"

    def test_en_introduction(self, pm):
        assert pm.get_section_type("Introduction", "en") == "introduction"
        assert pm.get_section_type("Background", "en") == "introduction"

    def test_en_results(self, pm):
        assert pm.get_section_type("Results", "en") == "results"
        assert pm.get_section_type("Discussion", "en") == "results"

    def test_zh_sections(self, pm):
        assert pm.get_section_type("摘要", "zh") == "abstract"
        assert pm.get_section_type("引言", "zh") == "introduction"
        assert pm.get_section_type("结果", "zh") == "results"

    def test_unknown_heading(self, pm):
        assert pm.get_section_type("Some Random Text", "en") == "body"

    def test_rejected_sections(self, pm):
        assert pm.is_rejected_section("Abstract", "en") is True
        assert pm.is_rejected_section("Introduction", "en") is False

    def test_this_work_patterns(self, pm):
        patterns = pm.get_this_work_patterns("en")
        assert "this work" in patterns
        assert "we propose" in patterns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
