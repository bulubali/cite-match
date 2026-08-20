"""test_multilingual_sections.py — v2.4: Multi-language section detection"""
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


class TestEnglishSections:
    def test_all_en_types(self, pm):
        cases = [
            ("Abstract", "abstract"), ("Introduction", "introduction"),
            ("Background", "introduction"), ("Results", "results"),
            ("Discussion", "results"), ("Materials", "materials"),
            ("Fabrication", "materials"), ("Mechanisms", "mechanisms"),
            ("Working Principle", "mechanisms"), ("Applications", "applications"),
            ("Clinical", "applications"), ("Conclusion", "conclusion"),
            ("Outlook", "conclusion"), ("Future", "conclusion"),
        ]
        for heading, expected in cases:
            assert pm.get_section_type(heading, "en") == expected, \
                f"{heading} should be {expected}"


class TestChineseSections:
    def test_all_zh_types(self, pm):
        cases = [
            ("摘要", "abstract"), ("引言", "introduction"),
            ("背景", "introduction"), ("结果", "results"),
            ("讨论", "results"), ("材料", "materials"),
            ("制备", "materials"), ("机制", "mechanisms"),
            ("原理", "mechanisms"), ("应用", "applications"),
            ("临床", "applications"), ("总结", "conclusion"),
            ("展望", "conclusion"), ("结论", "conclusion"),
        ]
        for heading, expected in cases:
            assert pm.get_section_type(heading, "zh") == expected, \
                f"{heading} should be {expected}"


class TestRejectedZones:
    def test_abstract_rejected_both_langs(self, pm):
        assert pm.is_rejected_section("Abstract", "en")
        assert pm.is_rejected_section("摘要", "zh")

    def test_intro_not_rejected(self, pm):
        assert not pm.is_rejected_section("Introduction", "en")
        assert not pm.is_rejected_section("引言", "zh")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
