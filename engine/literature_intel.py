"""
CiteMatch v2.2 — Phase 2: Literature Intelligence Layer

Reads bibliography.bib, resolves PDF paths from BBT file field,
extracts metadata, and generates References_Summary.md with
semantic anchors for human review before injection.

Core output:
  References_Summary.md — human confirmation checkpoint

Rules:
  - All new papers must have a summary entry before injection
  - Human MUST confirm before Phase 3 proceeds
"""
import os
import re
from typing import Optional
from dataclasses import dataclass, field
from bib_parser import BibTeXParser


@dataclass
class PaperIntel:
    """Extracted intelligence for a single paper"""
    citekey: str
    title: str = ""
    paper_type: str = "research"       # review / research
    core_finding: str = ""
    technical_keywords: list[str] = field(default_factory=list)
    semantic_anchors: list[str] = field(default_factory=list)
    recommended_section: str = ""
    pdf_path: str = ""
    abstract: str = ""
    authors: str = ""
    year: str = ""
    journal: str = ""

    def to_markdown_row(self) -> str:
        keywords = ', '.join(self.technical_keywords[:5])
        anchors = ', '.join(self.semantic_anchors[:5])
        return (
            f'| @{self.citekey} | {self.paper_type} | {self.title[:60]} | '
            f'{self.core_finding[:80]} | *{keywords}* | {anchors} | '
            f'{self.recommended_section} |'
        )


class LiteratureIntelligence:
    """Phase 2: Extract intelligence from bibliography for human review

    Usage:
        intel = LiteratureIntelligence()
        intel.load_bib("bibliography.bib")
        papers = intel.analyze_pending(pending_keys)
        intel.generate_summary(papers, "References_Summary.md")
    """

    # v2.4: Section routing via Policy Manager — no manuscript-specific names

    def __init__(self):
        self._bib_entries: dict = {}
        self._parser = BibTeXParser()
        self._missing_bbt_file: bool = False

    def load_bib(self, bib_path: str) -> dict:
        """Load and parse bibliography"""
        self._bib_entries = self._parser.parse_file(bib_path)
        return self._bib_entries

    def analyze_pending(self, pending_keys: list[str]) -> list[PaperIntel]:
        """Analyze pending papers and extract intelligence

        Args:
            pending_keys: list of citekeys to analyze

        Returns:
            list of PaperIntel with extracted metadata
        """
        results = []
        for key in pending_keys:
            entry = self._bib_entries.get(key)
            if not entry:
                continue

            intel = PaperIntel(citekey=key)
            intel.title = self._clean_latex(entry.title)
            intel.authors = entry.fields.get('author', '')
            intel.year = entry.year
            intel.journal = entry.journal
            intel.abstract = self._clean_latex(entry.fields.get('abstract', ''))

            # Resolve PDF path from BBT file field
            intel.pdf_path = self._resolve_pdf_path(entry.fields.get('file', ''))
            # BBT blocking: warn if no file field (but don't block non-BBT bibs with 0 entries failing)
            self._missing_bbt_file = self._missing_bbt_file or (
                not entry.fields.get('file', '') and len(self._bib_entries) > 0)

            # Classify paper type
            intel.paper_type = self._classify_paper_type(intel.title, intel.abstract)

            # Extract core finding
            intel.core_finding = self._extract_core_finding(intel.title, intel.abstract)

            # Extract technical keywords
            intel.technical_keywords = self._extract_keywords(intel.title, intel.abstract)

            # Generate semantic anchors
            intel.semantic_anchors = self._generate_anchors(
                intel.title, intel.abstract, intel.technical_keywords)

            # Route to recommended section
            intel.recommended_section = self._route_to_section(
                intel.title, intel.abstract, intel.paper_type)

            results.append(intel)

        return results

    def generate_summary(self, papers: list[PaperIntel], output_path: str) -> str:
        """Generate References_Summary.md with human confirmation checkpoint

        Returns:
            The markdown content as a string
        """
        lines = []
        lines.append('# CiteMatch v2.2 — References Summary')
        lines.append('')
        lines.append(f'> **Total pending papers**: {len(papers)}')
        lines.append(f'> **Review papers**: {sum(1 for p in papers if p.paper_type == "review")}')
        lines.append(f'> **Research papers**: {sum(1 for p in papers if p.paper_type == "research")}')
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## ⚠️ HUMAN CONFIRMATION REQUIRED')
        lines.append('')
        lines.append('**Before proceeding to Phase 3 (Semantic Injection):**')
        lines.append('')
        lines.append('1. Review each paper\'s semantic anchors for accuracy')
        lines.append('2. Verify recommended manuscript sections')
        lines.append('3. Remove or reassign papers that don\'t fit')
        lines.append('4. Reply with "继续匹配" to proceed')
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## Paper Intelligence')
        lines.append('')
        lines.append(
            '| CiteKey | Type | Title | Core Finding | Keywords | Semantic Anchors | '
            'Recommended Section |'
        )
        lines.append(
            '|:---|:---|:---|:---|:---|:---|:---|'
        )

        for paper in papers:
            lines.append(paper.to_markdown_row())

        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## PDF Availability')
        lines.append('')
        for paper in papers:
            status = '✅' if paper.pdf_path else '❌'
            lines.append(f'- {status} @{paper.citekey}: {paper.pdf_path or "No PDF path in BBT file field"}')

        content = '\n'.join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(content)

        return content

    # ---- Internal helpers ----

    @staticmethod
    def _clean_latex(text: str) -> str:
        """Remove LaTeX markup"""
        if not text:
            return ""
        text = re.sub(r'\{\\(?:bf|it|em|text)[a-z]*\{([^}]+)\}\}', r'\1', text)
        text = re.sub(r'\{([^}]+)\}', r'\1', text)
        text = re.sub(r'\\[a-z]+\{([^}]+)\}', r'\1', text)
        text = text.replace('{{', '').replace('}}', '')
        return text.strip()

    @staticmethod
    def _resolve_pdf_path(file_field: str) -> str:
        """Resolve PDF path from Zotero BBT file field"""
        if not file_field:
            return ""
        # Format: :C:\path\to\file.pdf:application/pdf
        # or: C:\path\to\file.pdf
        match = re.search(r'([A-Za-z]:[^:;]+\.pdf)', file_field)
        if match:
            path = match.group(1).strip()
            return path if os.path.exists(path) else ""
        return ""

    @staticmethod
    def _classify_paper_type(title: str, abstract: str) -> str:
        """Classify as review or research paper"""
        text = (title + ' ' + abstract).lower()
        review_words = ['review', 'survey', 'overview', 'progress', 'advances',
                       'perspective', 'comprehensive']
        if any(w in text for w in review_words):
            return 'review'
        return 'research'

    @staticmethod
    def _extract_core_finding(title: str, abstract: str) -> str:
        """Extract core finding/conclusion from title and abstract"""
        if not abstract:
            return title[:80]

        # Look for conclusion-like sentences
        conclusion_patterns = [
            r'(demonstrates?\s+[^.]{20,120}\.)',
            r'(achieves?\s+[^.]{20,120}\.)',
            r'(shows?\s+[^.]{20,120}\.)',
            r'(results?\s+[^.]{20,120}\.)',
            r'(proposes?\s+[^.]{20,120}\.)',
        ]
        for pattern in conclusion_patterns:
            match = re.search(pattern, abstract, re.IGNORECASE)
            if match:
                return match.group(1)[:120]

        # Fallback: first substantial sentence
        sentences = re.split(r'(?<=[.!])\s+', abstract)
        for s in sentences:
            if len(s) > 30:
                return s[:120]

        return title[:80]

    @staticmethod
    def _extract_keywords(title: str, abstract: str) -> list[str]:
        """Extract technical keywords from title and abstract"""
        text = (title + ' ' + abstract).lower()

        keyword_patterns = [
            r'piezoelectric', r'piezoresistive', r'triboelectric', r'capacitive',
            r'iontronic', r'photoplethysmograph', r'ultrasound', r'ultrasonic',
            r'pulse wave', r'pulse transit', r'ptt', r'pwv',
            r'machine learning', r'deep learning', r'neural network',
            r'mxene', r'graphene', r'carbon nanotube', r'nanowire',
            r'liquid metal', r'hydrogel', r'pdms', r'pvdf',
            r'breathable', r'textile', r'fabric', r'self-powered',
            r'wearable', r'epidermal', r'skin', r'conformal',
            r'blood pressure', r'hypertension', r'cardiovascular',
            r'sensitivity', r'linearity', r'hysteresis', r'response time',
            r'motion artifact', r'signal-to-noise', r'calibration-free',
        ]

        found = []
        for pattern in keyword_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                keyword = pattern.replace(r'\ ', ' ').replace(r'-', '-')
                found.append(keyword)

        return found[:8]

    @staticmethod
    def _generate_anchors(title: str, abstract: str,
                          keywords: list[str]) -> list[str]:
        """Generate semantic anchors — phrases likely to match manuscript text"""
        anchors = []

        # From keywords: add typical manuscript phrases
        for kw in keywords[:5]:
            kw_clean = kw.replace(' ', '-')
            anchors.append(kw)

        # From title: extract noun phrases
        title_words = re.findall(r'[A-Z][a-z]+(?:\s+[a-z]+){1,3}', title)
        for phrase in title_words[:3]:
            if len(phrase) > 10:
                anchors.append(phrase.lower())

        # Deduplicate, keep top 8
        seen = set()
        unique = []
        for a in anchors:
            if a.lower() not in seen:
                seen.add(a.lower())
                unique.append(a)
        return unique[:8]

    def _route_to_section(self, title: str, abstract: str,
                          paper_type: str) -> str:
        """Route paper to recommended manuscript section via Policy Manager"""
        try:
            from policy_manager import get_policy
            section = get_policy().route_topic_to_section(title, abstract, paper_type)
            if section and section != "General":
                return section
        except Exception:
            pass

        # Generic fallback routing — no manuscript-specific section names
        text = (title + ' ' + abstract).lower()
        if paper_type == 'review':
            return 'Introduction'
        if any(w in text for w in ['sensitivity', 'strain', 'pressure sensor']):
            return 'Materials & Sensing'
        if any(w in text for w in ['fabrication', 'printing', 'electrospinning']):
            return 'Fabrication'
        if any(w in text for w in ['clinical', 'surgery', 'icu']):
            return 'Clinical Applications'
        return 'General'
