"""Adapt approved semantic candidates to the existing injector interface."""
from __future__ import annotations

from cm_types import CitationPosition, MatchResult, MatchStrategy
from md_ast import MarkdownAST


class CandidateAdaptationError(ValueError):
    """Raised when an approved target cannot be located uniquely and safely."""


def adapt_semantic_candidates(candidates: list, manuscript_text: str) -> list[tuple]:
    """Convert approved ``CitationCandidate`` values into injector tuples.

    Semantic matching has already selected the target sentence and citekey.
    This adapter performs no scoring or routing; it only resolves that exact
    sentence to a unique zero-width AST position.  Ambiguous or missing targets
    fail closed.
    """
    ast = MarkdownAST(manuscript_text)
    ast.parse()
    lines = manuscript_text.split("\n")
    adapted = []

    for candidate in candidates:
        if candidate.is_rejected:
            continue
        target = candidate.target_sentence
        if not target:
            raise CandidateAdaptationError(
                f"Approved candidate @{candidate.paper.citekey} has no target sentence"
            )

        occurrences = []
        for line_number, line in enumerate(lines, 1):
            start = 0
            while True:
                column = line.find(target, start)
                if column < 0:
                    break
                occurrences.append((line_number, column))
                start = column + 1

        if len(occurrences) != 1:
            raise CandidateAdaptationError(
                f"Target for @{candidate.paper.citekey} must occur exactly once; "
                f"found {len(occurrences)}"
            )

        line_number, column = occurrences[0]
        if ast.is_in_protected_zone(line_number):
            raise CandidateAdaptationError(
                f"Target for @{candidate.paper.citekey} is in protected section "
                f"'{ast.get_section_for_line(line_number)}'"
            )
        insertion_column = column + len(target)
        if target[-1:] in ".!?。！？":
            insertion_column -= 1

        position = CitationPosition(
            line_number=line_number,
            column_start=insertion_column,
            column_end=insertion_column,
            raw_text="",
            section=ast.get_section_for_line(line_number) or candidate.section,
            is_in_table=ast._is_in_table(line_number),
            is_in_code_block=ast._is_in_code_block(line_number),
            is_in_protected_zone=ast.is_in_protected_zone(line_number),
        )
        match = MatchResult(
            citekey=candidate.paper.citekey,
            confidence=candidate.similarity_score,
            strategy=MatchStrategy.MANUAL,
            evidence="Approved SemanticMapper target",
        )
        adapted.append((position, match))

    return adapted
