"""ISSUE-008 regression: Abstract/Keywords are read-only for NEW citations."""
from __future__ import annotations

import os
import sys

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "engine"))

from candidate_adapter import CandidateAdaptationError, adapt_semantic_candidates
from citation_registry import CitationRegistry
from cm_types import CitationPosition, MatchResult, MatchStrategy
from injector import CitationInjector
from literature_intel import PaperIntel
from md_ast import MarkdownAST
from semantic_mapper import CitationCandidate, SemanticMapper


def _paper(citekey: str = "New2026") -> PaperIntel:
    return PaperIntel(
        citekey=citekey,
        title="Flexible blood pressure monitoring",
        paper_type="research",
        technical_keywords=["flexible", "blood pressure"],
        semantic_anchors=["flexible", "blood pressure"],
    )


def _candidate(target: str, section: str = "Introduction") -> CitationCandidate:
    return CitationCandidate(
        paper=_paper(),
        target_sentence=target,
        section=section,
        similarity_score=1.0,
        reason="approved semantic match",
    )


@pytest.mark.parametrize(
    "heading",
    ["# Abstract", "## Abstract", "**Abstract**", "**Abstract:**", "Abstract:",
     "摘要", "**摘要**", "**摘要：**"],
)
def test_abstract_heading_variants_are_protected_until_body(heading):
    text = (
        f"{heading}\n\nFlexible blood pressure content in the summary.\n\n"
        "**Introduction:**\n\nFlexible blood pressure monitoring in the body.\n"
    )
    ast = MarkdownAST(text)
    ast.parse()
    assert ast.is_in_protected_zone(3)
    assert not ast.is_in_protected_zone(7)

    candidates = SemanticMapper().map_papers_to_manuscript([_paper()], text)
    accepted = [candidate for candidate in candidates if not candidate.is_rejected]
    assert len(accepted) == 1
    assert accepted[0].target_sentence == "Flexible blood pressure monitoring in the body."


@pytest.mark.parametrize(
    "heading",
    ["# Keywords", "**Keywords:**", "Keywords:", "Key words:",
     "关键词", "**关键词：**"],
)
def test_keywords_heading_variants_are_protected_until_body(heading):
    text = (
        f"{heading}\n\nFlexible; blood pressure; monitoring\n\n"
        "# Introduction\n\nFlexible blood pressure monitoring in the body.\n"
    )
    ast = MarkdownAST(text)
    ast.parse()
    assert ast.is_in_protected_zone(3)
    assert not ast.is_in_protected_zone(7)

    candidates = SemanticMapper().map_papers_to_manuscript([_paper()], text)
    accepted = [candidate for candidate in candidates if not candidate.is_rejected]
    assert len(accepted) == 1
    assert accepted[0].target_sentence == "Flexible blood pressure monitoring in the body."


def test_adapter_rejects_protected_target_even_with_false_candidate_section():
    target = "Flexible blood pressure content in the summary."
    text = f"**Abstract:**\n\n{target}\n\n**Introduction:**\n\nBody text.\n"
    with pytest.raises(CandidateAdaptationError, match="protected section"):
        adapt_semantic_candidates([_candidate(target, section="Introduction")], text)


def test_injector_final_guard_blocks_when_candidate_classification_is_wrong():
    target = "Flexible blood pressure content in the summary."
    text = f"**Abstract:**\n\n{target}\n\n**Introduction:**\n\nBody text.\n"
    position = CitationPosition(
        line_number=3,
        column_start=len(target) - 1,
        column_end=len(target) - 1,
        raw_text="",
        section="Introduction",
        is_in_protected_zone=False,
    )
    match = MatchResult(
        citekey="New2026",
        confidence=1.0,
        strategy=MatchStrategy.MANUAL,
    )
    registry = CitationRegistry()
    registry.register("New2026")
    injector = CitationInjector(registry)
    injector.set_document(text)

    result = injector.inject_candidates([(position, match)])

    assert result == text
    assert any(
        item["action"] == "skip_locked" and "protected section" in item["reason"]
        for item in injector.injection_log
    )


def test_legacy_citation_is_preserved_while_body_new_citation_is_injected():
    body_target = "Flexible blood pressure monitoring in the body."
    text = (
        "**Abstract:**\n\nExisting summary citation ^[1]^ remains.\n\n"
        f"**Introduction:**\n\n{body_target}\n"
    )
    plan = adapt_semantic_candidates([_candidate(body_target)], text)
    registry = CitationRegistry()
    registry.register("New2026")
    injector = CitationInjector(registry)
    injector.set_document(text)

    result = injector.inject_candidates(plan)

    assert "Existing summary citation ^[1]^ remains." in result
    assert "Flexible blood pressure monitoring in the body [@New2026]." in result
    abstract_block, body_block = result.split("**Introduction:**", 1)
    assert "@New2026" not in abstract_block
    assert "@New2026" in body_block


def test_legacy_replacement_remains_allowed_inside_abstract():
    text = "**Abstract:**\n\nExisting summary citation ^[1]^ remains.\n"
    raw = "^[1]^"
    line = text.splitlines()[2]
    start = line.index(raw)
    position = CitationPosition(
        line_number=3,
        column_start=start,
        column_end=start + len(raw),
        raw_text=raw,
        section="Abstract",
        is_in_protected_zone=True,
    )
    match = MatchResult(
        citekey="Old2020",
        confidence=1.0,
        strategy=MatchStrategy.MANUAL,
    )
    registry = CitationRegistry()
    registry.register("Old2020")
    injector = CitationInjector(registry)
    injector.set_document(text)

    result = injector.inject_batch([(position, match)], remove_reference_list=False)

    assert "Old2020" in result
    assert "^[1]^" not in result
    assert any(item["action"] == "inject" for item in injector.injection_log)
    assert not any(item["action"] == "skip_locked" for item in injector.injection_log)
