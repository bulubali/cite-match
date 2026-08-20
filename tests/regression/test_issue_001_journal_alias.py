"""ISSUE-001 — reviewed journal aliases resolve without widening IF coverage."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE = os.path.join(ROOT, "engine")
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

from body_if_gate import BodyCitationIFGate, IFGateResult
from literature_intel import PaperIntel
from policy_manager import PolicyManager, get_policy
from semantic_mapper import CitationCandidate


@pytest.fixture(autouse=True)
def reset_policy():
    PolicyManager.reset()
    yield
    PolicyManager.reset()


def _database():
    policy = get_policy()
    policy.load_profile("default", os.path.join(ROOT, "profiles"))
    return policy.load_journal_if_database()


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("Sens. Actuators, A", 4.2),
        ("Sens. Actuators A", 4.2),
        ("  sens. actuators, a  ", 4.2),
        ("Sensors and Actuators A: Physical", 4.2),
        ("Adv. Healthcare Mater.", 9.2),
        ("Advanced Materials", 27.4),
        ("Advanced Science", 14.3),
        ("Adv Funct Materials", 15.6),
        ("npj Flex Electron", 9.2),
        ("Chemical Engineering Journal", 13.2),
        ("Sens.", 3.9),
        ("IEEE Sensors J.", 4.5),
        ("Biosensors and Bioelectronics", 10.7),
    ],
)
def test_reviewed_aliases_and_formatting_resolve(variant, expected):
    assert BodyCitationIFGate._resolve_if(variant, _database()) == expected


def test_unknown_and_near_name_do_not_gain_an_if():
    database = _database()
    assert BodyCitationIFGate._resolve_if("Unknown Journal", database) == 0.0
    assert BodyCitationIFGate._resolve_if("Advanced Material Science", database) == 0.0


def test_alias_targets_are_existing_database_keys():
    policy = get_policy()
    policy.load_profile("default", os.path.join(ROOT, "profiles"))
    database = policy.load_journal_if_database()
    assert set(policy.load_journal_aliases().values()).issubset(database)


def test_verified_full_title_is_below_body_threshold_not_unknown():
    get_policy().load_profile("advanced_materials_review", os.path.join(ROOT, "profiles"))
    candidate = CitationCandidate(
        paper=PaperIntel(
            citekey="verified-alias", journal="Sensors and Actuators A: Physical"
        ),
        target_sentence="A matched body sentence.", section="Body",
        similarity_score=1.0, reason="matched",
    )
    gate = BodyCitationIFGate()
    gate.apply_runtime_policy(body_threshold=6, body_if_enabled=True)
    decision = gate.validate_candidates([candidate]).decisions[0]
    assert decision.impact_factor == 4.2
    assert decision.result == IFGateResult.BELOW_THRESHOLD
    assert decision.result != IFGateResult.UNKNOWN
