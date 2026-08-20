import os
import sys

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "engine"))

from candidate_adapter import CandidateAdaptationError, adapt_semantic_candidates
from citation_registry import CitationRegistry
from injector import CitationInjector
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate


def _candidate(sentence: str, citekey: str = "Paper2025") -> CitationCandidate:
    return CitationCandidate(
        paper=PaperIntel(citekey=citekey),
        target_sentence=sentence,
        section="Introduction",
        similarity_score=0.75,
        reason="approved semantic match",
    )


def test_adapter_preserves_semantic_decision_and_injector_owns_rendering():
    sentence = "Flexible sensors support continuous monitoring."
    manuscript = f"# Introduction\n\n{sentence}\n"
    plan = adapt_semantic_candidates([_candidate(sentence)], manuscript)

    position, match = plan[0]
    assert match.citekey == "Paper2025"
    assert match.confidence == 0.75
    assert position.raw_text == ""
    assert not position.is_in_table

    registry = CitationRegistry()
    registry.register("Paper2025")
    injector = CitationInjector(registry)
    injector.set_document(manuscript)
    result = injector.inject_candidates(plan, auto_confirm=False)
    assert "continuous monitoring [@Paper2025]." in result


def test_adapter_fails_closed_for_non_unique_target():
    sentence = "The same sentence is repeated."
    manuscript = f"{sentence}\n\n{sentence}\n"
    with pytest.raises(CandidateAdaptationError, match="exactly once"):
        adapt_semantic_candidates([_candidate(sentence)], manuscript)


def test_adapter_preserves_table_protection():
    sentence = "| Sensor | Strong response. |"
    manuscript = "| Type | Result |\n|---|---|\n" + sentence + "\n"
    plan = adapt_semantic_candidates([_candidate(sentence)], manuscript)
    assert plan[0][0].is_in_table

    injector = CitationInjector(CitationRegistry())
    injector.set_document(manuscript)
    result = injector.inject_candidates(plan, auto_confirm=False)
    assert result == manuscript
    assert injector.has_table_citations()
