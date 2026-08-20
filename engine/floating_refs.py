"""
CiteMatch v2.2 — Phase 4: Floating Reference Handler

Handles papers that have no suitable sentence match.
Generates Floating_Reference_Report.md with expansion suggestions.

AI-generated expansion text MUST include:
  【AI扩写区开始】
  ...
  【AI扩写区结束】
"""
import os
import re
from typing import Optional
from dataclasses import dataclass, field
from literature_intel import PaperIntel
from md_ast import MarkdownAST
from file_guard import WriteGuard


@dataclass
class FloatingReference:
    """A paper with no suitable sentence match"""
    paper: PaperIntel
    reason: str = ""
    suggested_section: str = ""
    suggested_expansion: str = ""
    keywords_matched: str = ""

    def expansion_with_markers(self) -> str:
        """Return expansion text with mandatory AI markers"""
        return (
            f'【AI扩写区开始】\n'
            f'{self.suggested_expansion}\n'
            f'【AI扩写区结束】'
        )


class FloatingRefHandler:
    """Phase 4: Handle papers that can't be matched to existing sentences

    Usage:
        handler = FloatingRefHandler()
        floaters = handler.identify_floating_references(candidates)
        report = handler.generate_report(floaters, "Floating_Reference_Report.md")
    """

    # Templates for generating expansion suggestions
    EXPANSION_TEMPLATES = {
        'review': (
            'A recent review by {authors} ({year}) provides a comprehensive '
            'overview of {topic}, highlighting the importance of {keywords} '
            'for advancing the field of blood pressure monitoring.'
        ),
        'research': (
            '{authors} ({year}) demonstrated that {core_finding}. '
            'This work contributes to the understanding of {keywords} '
            'in the context of wearable blood pressure sensors.'
        ),
        'method': (
            'From a methodological perspective, {authors} ({year}) introduced '
            'a novel approach for {topic}, achieving {core_finding}. '
            'This method offers potential improvements in {keywords}.'
        ),
    }

    def __init__(self):
        self._floaters: list[FloatingReference] = []

    def identify_floating_references(
        self,
        candidates: list,
    ) -> list[FloatingReference]:
        """Identify papers with no suitable sentence from semantic mapper

        Args:
            candidates: list of CitationCandidate from SemanticMapper

        Returns:
            list of FloatingReference for papers that need expansion
        """
        self._floaters = []

        for c in candidates:
            if c.is_rejected:
                paper = c.paper
                floater = FloatingReference(
                    paper=paper,
                    reason=c.rejection_reason,
                    suggested_section=paper.recommended_section,
                )

                # Generate expansion suggestion
                floater.keywords_matched = ', '.join(paper.technical_keywords[:3])
                floater.suggested_expansion = self._generate_expansion(paper)

                self._floaters.append(floater)

        return list(self._floaters)

    def generate_report(
        self, floaters: list[FloatingReference], output_path: str = ""
    ) -> str:
        """Generate Floating_Reference_Report.md

        Returns:
            The markdown content as a string
        """
        lines = []
        lines.append('# CiteMatch v2.2 — Floating Reference Report')
        lines.append('')
        lines.append(f'> **Floating papers**: {len(floaters)}')
        lines.append(f'> **All require human review before injection**')
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## ⚠️ AI EXPANSION WARNING')
        lines.append('')
        lines.append('The expansion text below is AI-generated.')
        lines.append('Search for `【AI扩写区】` to review all AI-authored content.')
        lines.append('**Delete or rewrite before final manuscript submission.**')
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## Floating References')
        lines.append('')

        for i, floater in enumerate(floaters, 1):
            paper = floater.paper
            lines.append(f'### {i}. @{paper.citekey}')
            lines.append('')
            lines.append(f'**Title**: {paper.title}')
            lines.append(f'**Authors**: {paper.authors[:100]}')
            lines.append(f'**Year**: {paper.year} | **Journal**: {paper.journal}')
            lines.append(f'**Type**: {paper.paper_type}')
            lines.append('')
            lines.append(f'**Reason for floating**: {floater.reason}')
            lines.append(f'**Suggested section**: {floater.suggested_section}')
            lines.append('')
            lines.append('**Suggested Expansion**:')
            lines.append('')
            lines.append(floater.expansion_with_markers())
            lines.append('')
            lines.append('---')
            lines.append('')

        lines.append('## Summary')
        lines.append('')
        lines.append('| # | CiteKey | Reason | Suggested Section |')
        lines.append('|---|---------|--------|-------------------|')
        for i, floater in enumerate(floaters, 1):
            lines.append(
                f'| {i} | @{floater.paper.citekey} | {floater.reason[:60]} | '
                f'{floater.suggested_section} |'
            )
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## Review Checklist')
        lines.append('')
        lines.append('- [ ] Review each AI-generated expansion for accuracy')
        lines.append('- [ ] Verify the paper\'s core finding matches the expansion text')
        lines.append('- [ ] Confirm the suggested section is appropriate')
        lines.append('- [ ] Remove or rewrite any expansion that misrepresents the paper')
        lines.append('- [ ] Search `【AI扩写区】` to locate all AI-authored content')
        lines.append('- [ ] Reply "确认注入" to proceed with injection')

        content = '\n'.join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return content

    def apply_confirmed_expansion(
        self,
        manuscript_text: str,
        approved_expansion: str,
        target_section: str,
        target_location: str = "section_end",
        output_path: str = "",
    ) -> dict:
        """Apply user-approved expansion text at an explicit section boundary.

        This method performs no matching, section recommendation, or expansion
        generation.  The target title must resolve exactly once and the caller
        must choose ``section_start`` or ``section_end``.
        """
        if target_location not in {"section_start", "section_end"}:
            return self._apply_blocked(
                manuscript_text, "INVALID_TARGET_LOCATION",
                {"allowed": ["section_start", "section_end"]},
            )
        expansion = str(approved_expansion or "").strip()
        if not expansion:
            return self._apply_blocked(
                manuscript_text, "EMPTY_APPROVED_EXPANSION"
            )

        ast = MarkdownAST(manuscript_text)
        ast.parse()
        normalized_target = self._normalize_section(target_section)
        headings = [
            node for node in ast.root.children
            if node.type == "heading" and self._normalize_section(
                node.metadata.get("title", "")
            ) == normalized_target
        ]
        if not headings:
            return self._apply_blocked(
                manuscript_text, "TARGET_SECTION_NOT_FOUND",
                {"target_section": target_section},
            )
        if len(headings) > 1:
            return self._apply_blocked(
                manuscript_text, "TARGET_SECTION_AMBIGUOUS",
                {"target_section": target_section, "matches": len(headings)},
            )
        if self._is_protected_section(target_section):
            return self._apply_blocked(
                manuscript_text, "PROTECTED_TARGET_SECTION",
                {"target_section": target_section},
            )

        start_marker = "【AI扩写区开始】"
        end_marker = "【AI扩写区结束】"
        start_count = expansion.count(start_marker)
        end_count = expansion.count(end_marker)
        if start_count == 0 and end_count == 0:
            marked_expansion = (
                f"{start_marker}\n{expansion}\n{end_marker}"
            )
        elif (start_count == 1 and end_count == 1 and
              expansion.index(start_marker) < expansion.index(end_marker)):
            marked_expansion = expansion
        else:
            return self._apply_blocked(
                manuscript_text, "INVALID_EXPANSION_MARKERS"
            )

        heading = headings[0]
        following_headings = [
            node for node in ast.root.children
            if node.type == "heading" and node.line_start > heading.line_start
        ]
        section_end_index = (
            following_headings[0].line_start - 1
            if following_headings else len(manuscript_text.split("\n"))
        )
        insertion_index = (
            heading.line_end
            if target_location == "section_start"
            else section_end_index
        )
        lines = manuscript_text.split("\n")
        inserted_lines = ["", *marked_expansion.split("\n"), ""]
        modified = "\n".join(
            lines[:insertion_index] + inserted_lines + lines[insertion_index:]
        )

        written_path = None
        if output_path:
            output_path = os.path.abspath(output_path)
            guard = WriteGuard(workspace_root=os.path.dirname(output_path))
            guard.set_dry_run_completed()
            guard.set_validator(lambda: (
                modified.count(start_marker) == manuscript_text.count(start_marker) + 1
                and modified.count(end_marker) == manuscript_text.count(end_marker) + 1
            ))
            if not guard.validate():
                return self._apply_blocked(
                    manuscript_text, "EXPANSION_VALIDATION_FAILED"
                )
            written_path = guard.safe_write(modified, output_path)

        return {
            "status": "completed",
            "manuscript": modified,
            "output_path": written_path,
            "target_section": target_section,
            "target_location": target_location,
        }

    @staticmethod
    def _normalize_section(section: str) -> str:
        return re.sub(r"\s+", " ", str(section).strip().strip("*_")).casefold()

    @classmethod
    def _is_protected_section(cls, section: str) -> bool:
        normalized = cls._normalize_section(section)
        protected = (
            "abstract", "keywords", "figure", "fig.", "table", "caption",
            "摘要", "关键词", "图", "表",
        )
        return normalized.startswith(protected)

    @staticmethod
    def _apply_blocked(manuscript_text: str, reason: str, details=None) -> dict:
        return {
            "status": "blocked",
            "reason": reason,
            "details": details or {},
            "manuscript": manuscript_text,
            "output_path": None,
        }

    # ---- Internal ----

    def _generate_expansion(self, paper: PaperIntel) -> str:
        """Generate AI expansion text for a floating reference"""
        authors = paper.authors.split(' and ')[0].split(',')[0].strip()
        year = paper.year
        topic = paper.title[:60]
        core = paper.core_finding[:80]
        keywords = ', '.join(paper.technical_keywords[:3])

        template = (
            self.EXPANSION_TEMPLATES['review'] if paper.paper_type == 'review'
            else self.EXPANSION_TEMPLATES['research']
        )

        return template.format(
            authors=authors,
            year=year,
            topic=topic,
            core_finding=core,
            keywords=keywords,
        )

    @property
    def floaters(self) -> list[FloatingReference]:
        return list(self._floaters)

    @property
    def count(self) -> int:
        return len(self._floaters)
