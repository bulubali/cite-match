"""ISSUE-003 — retain ranked matches and reroute sentence-density overflow."""
from dataclasses import asdict
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "engine"))

from candidate_adapter import adapt_semantic_candidates
from floating_refs import FloatingRefHandler
from literature_intel import PaperIntel
from phase_gate import WorkflowGate
from semantic_mapper import CitationCandidate, SemanticMapper
from workflows.manuscript_workflow import ManuscriptWorkflow


def _paper(key, anchors):
    return PaperIntel(
        citekey=key, title=key, paper_type="research",
        semantic_anchors=anchors, technical_keywords=anchors,
    )


def _map(papers, text):
    return SemanticMapper().map_papers_to_manuscript(papers, text)


def test_best_sentence_full_reroutes_to_second_ranked_candidate():
    text = "Shared common claim. Alternative alpha claim.\n"
    papers = [_paper(f"Primary{i}", ["common"]) for i in range(3)]
    papers.append(_paper("Rerouted", ["common", "alpha"]))

    candidates = _map(papers, text)
    rerouted = next(item for item in candidates if item.paper.citekey == "Rerouted")

    assert not rerouted.is_rejected
    assert rerouted.original_best_rank == 1
    assert rerouted.selected_rank == 2
    assert rerouted.original_target == "Shared common claim."
    assert rerouted.selected_target == "Alternative alpha claim."
    assert rerouted.reroute_reason == "sentence_density_overflow"
    assert rerouted.attempted_candidate_count == 2


def test_best_and_second_full_reroute_to_third_ranked_candidate():
    text = "Shared common claim. Alternative alpha claim. Alternative beta claim.\n"
    papers = [_paper(f"Common{i}", ["common"]) for i in range(3)]
    papers += [_paper(f"Alpha{i}", ["alpha"]) for i in range(3)]
    papers.append(_paper("ThirdChoice", ["common", "alpha", "beta"]))

    candidates = _map(papers, text)
    rerouted = next(item for item in candidates if item.paper.citekey == "ThirdChoice")

    assert not rerouted.is_rejected
    assert rerouted.selected_rank == 3
    assert rerouted.selected_target == "Alternative beta claim."
    assert [item["reason"] for item in rerouted.reroute_attempts] == [
        "sentence_density_full", "sentence_density_full", "selected"
    ]


def test_all_ranked_candidates_full_becomes_traceable_floating():
    text = "Shared common claim. Alternative alpha claim.\n"
    papers = [_paper(f"Common{i}", ["common"]) for i in range(3)]
    papers += [_paper(f"Alpha{i}", ["alpha"]) for i in range(3)]
    papers.append(_paper("NoAlternative", ["common", "alpha"]))

    candidates = _map(papers, text)
    rejected = next(item for item in candidates if item.paper.citekey == "NoAlternative")

    assert rejected.is_rejected
    assert rejected.rejection_reason == "no_safe_alternative_location"
    assert rejected.attempted_candidate_count == 2
    assert all(
        item["reason"] == "sentence_density_full"
        for item in rejected.reroute_attempts
    )
    report = FloatingRefHandler().generate_report(
        FloatingRefHandler().identify_floating_references([rejected])
    )
    assert "no_safe_alternative_location" in report


def test_ranked_alternatives_survive_json_workflow_state_restore(tmp_path):
    candidate = _map(
        [_paper("Persisted", ["common", "alpha"])],
        "Shared common claim. Alternative alpha claim.\n",
    )[0]
    state_path = str(tmp_path / "workflow_state.json")
    gate = WorkflowGate(state_path)
    gate.start_phase(3)
    gate.set_context({"candidate_state": {"candidates": [asdict(candidate)]}})

    restored = WorkflowGate(state_path).context
    candidates = ManuscriptWorkflow._deserialize_candidates(restored)
    restored_candidate = candidates[0]
    assert len(restored_candidate.ranked_alternatives) == 2
    assert restored_candidate.ranked_alternatives[1]["rank"] == 2


def test_existing_legacy_citations_do_not_consume_new_candidate_capacity():
    text = "Shared common claim [@Existing; @Legacy]. Alternative alpha claim.\n"
    papers = [_paper(f"Primary{i}", ["common"]) for i in range(3)]
    papers.append(_paper("NewPaper", ["common", "alpha"]))

    candidates = _map(papers, text)
    accepted = [item for item in candidates if not item.is_rejected]
    assert len(accepted) == 4
    assert next(item for item in candidates if item.paper.citekey == "NewPaper").selected_rank == 2


def test_protected_zones_are_never_ranked_as_fallback_locations():
    text = (
        "# Abstract\ncommon alpha claim.\n\n"
        "# Keywords\ncommon beta claim.\n\n"
        "# Introduction\nShared common claim. Alternative gamma claim.\n\n"
        "![Figure caption common delta claim](figure.png)\n"
    )
    candidate = _map([_paper("Protected", ["common", "alpha", "beta", "gamma", "delta"])], text)[0]
    targets = [item["target_sentence"] for item in candidate.ranked_alternatives]
    assert "Shared common claim." in targets
    assert "Alternative gamma claim." in targets
    assert all("alpha" not in target and "beta" not in target and "delta" not in target for target in targets)


def test_table_candidate_never_reroutes_to_body_location():
    mapper = SemanticMapper()
    candidate = CitationCandidate(
        paper=_paper("TableOnly", ["table"]),
        target_sentence="| common table claim |", section="Table 1",
        similarity_score=1.0, reason="table", ranked_alternatives=[
            {"rank": 1, "sentence_index": 1, "target_sentence": "| common table claim |", "section": "Table 1", "is_in_table": True, "similarity_score": 1.0, "reason": "table"},
            {"rank": 2, "sentence_index": 2, "target_sentence": "Body alternative claim.", "section": "Introduction", "is_in_table": False, "similarity_score": 0.5, "reason": "body"},
        ], original_best_rank=1, selected_rank=1,
        original_target="| common table claim |", selected_target="| common table claim |",
    )
    fillers = [
        CitationCandidate(
            paper=_paper(f"Table{i}", ["table"]), target_sentence="| common table claim |",
            section="Table 1", similarity_score=2.0, reason="table", ranked_alternatives=[
                {"rank": 1, "sentence_index": 1, "target_sentence": "| common table claim |", "section": "Table 1", "is_in_table": True, "similarity_score": 2.0, "reason": "table"}
            ], original_best_rank=1, selected_rank=1,
            original_target="| common table claim |", selected_target="| common table claim |",
        ) for i in range(3)
    ]

    result = mapper._enforce_sentence_limits([*fillers, candidate])
    rejected = next(item for item in result if item.paper.citekey == "TableOnly")
    assert rejected.is_rejected
    assert rejected.rejection_reason == "no_safe_alternative_location"
    assert any(item["reason"] == "table_context_mismatch" for item in rejected.reroute_attempts)


def test_adapter_and_injector_do_not_choose_ranked_alternatives():
    candidate = _map(
        [_paper("AdapterOnly", ["common", "alpha"])],
        "Shared common claim. Alternative alpha claim.\n",
    )[0]
    candidate.target_sentence = candidate.ranked_alternatives[0]["target_sentence"]
    plan = adapt_semantic_candidates(
        [candidate], "Shared common claim. Alternative alpha claim.\n"
    )
    assert plan[0][0].column_start == len("Shared common claim")
    assert candidate.selected_rank == 1


def test_existing_max_three_behavior_is_preserved_when_no_alternative_exists():
    candidates = _map(
        [_paper(f"Only{i}", ["common"]) for i in range(4)],
        "Shared common claim.\n",
    )
    assert len([item for item in candidates if not item.is_rejected]) == 3
    overflow = next(item for item in candidates if item.paper.citekey == "Only3")
    assert overflow.rejection_reason == "no_safe_alternative_location"
