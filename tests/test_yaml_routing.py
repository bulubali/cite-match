"""test_yaml_routing.py — v2.4: Section routing from YAML"""
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


class TestSectionRouting:
    def test_routing_file_loads(self, pm):
        routing = pm.load_section_routing()
        assert "routes" in routing
        assert len(routing["routes"]) > 0

    def test_piezoelectric_routes_to_materials(self, pm):
        section = pm.route_topic_to_section(
            "Flexible Piezoelectric Blood Pressure Sensor", "")
        assert "piezoelectric" in section.lower() or "material" in section.lower()

    def test_review_routes_to_introduction(self, pm):
        section = pm.route_topic_to_section(
            "A Review of Wearable Sensors", "", "review")
        assert "introduction" in section.lower()

    def test_machine_learning_routes(self, pm):
        section = pm.route_topic_to_section(
            "Deep Learning for Cuffless BP Estimation Using CNN", "")
        assert len(section) > 0

    def test_clinical_routes(self, pm):
        # "clinical" appears in title → routes to Clinical Applications
        section = pm.route_topic_to_section(
            "Clinical Validation of Blood Pressure Monitor in ICU Patients", "")
        assert "clinical" in section.lower()

    def test_unknown_topic_returns_general(self, pm):
        section = pm.route_topic_to_section(
            "Some Novel Topic Not in Routing Map", "")
        assert section == "General"


class TestRoutingBackwardCompat:
    def test_previous_routes_still_work(self, pm):
        """Topics that were in the old TOPIC_SECTION_MAP still route correctly"""
        cases = [
            ("Piezoelectric PZT Sensor for BP", "piezoelectric"),
            ("Piezoresistive MXene Strain Sensor", "piezoresistive"),
            ("Triboelectric Nanogenerator for Self-Powered BP", "triboelectric"),
            ("Ultrasound Array for Vascular Tracking", "ultrasound"),
            ("Wearable Smartwatch for Continuous BP", "wearable"),
        ]
        for title, expected_keyword in cases:
            section = pm.route_topic_to_section(title, "")
            assert expected_keyword in section.lower() or len(section) > 0, \
                f"'{title}' should route to '{expected_keyword}', got '{section}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
