"""
CiteMatch v2.2 — Phase 3: Semantic Mapping Layer

For each pending paper, generates anchor vectors, matches against
manuscript sentences, and produces a citation candidate table.

Citation Type Routing Layer (v2.2):
  - Review papers: Introduction/background only, forbidden in results
  - Research papers: routed by contribution type
  - Abstract: absolute exclusion zone
  - Figure captions: absolute exclusion zone
  - Tables: Elite IF gate (IF > 10)
  - Body: Global IF gate (IF > 6)

Injection rules:
  - Max 3 papers per sentence
  - No blind injection (similarity score threshold)
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from literature_intel import PaperIntel
from md_ast import MarkdownAST, get_section_classifier_terms, is_protected_section_title


# ---- Policy-backed constants (fall back to hardcoded for backward compat) ----
def _get_policy_value(path, default):
    try:
        from policy_manager import get_policy
        v = get_policy().get_rule(path)
        return v if v is not None else default
    except Exception:
        return default

# IF Gate thresholds
IF_THRESHOLD_ELITE = 10
IF_THRESHOLD_GLOBAL = 6

# v2.4: Section classification via Policy Manager — no hardcoded language keywords.
# Fallback values are English-only generic academic terms.
INTRODUCTION_KEYWORDS = ['introduction', 'background']
RESULTS_KEYWORDS = ['results', 'discussion']
QUANTITATIVE_CLAIM_PATTERNS = [
    r'achieves?\s+\d+', r'sensitivity\s+of\s+\d+', r'\d+\s*kPa',
    r'\d+\s*mmHg', r'\d+\s*%', r'performance\s+of', r'demonstrates?\s+\d+',
]
CONTRIBUTION_ROUTING = {
    'material':    ['material', 'piezoelectric', 'piezoresistive', 'capacitive', 'iontronic', 'triboelectric', 'optical'],
    'fabrication': ['fabrication', 'printing', 'lithography', 'electrospinning', 'textile', 'fiber'],
    'algorithm':   ['algorithm', 'machine learning', 'deep learning', 'signal processing', 'pulse wave', 'neural', 'transfer learning'],
    'clinical':    ['clinical', 'application', 'healthcare', 'monitoring', 'surgery', 'icu', 'daily'],
}


@dataclass
class AnchorMatch:
    """A single anchor match against a manuscript sentence"""
    paper: PaperIntel
    sentence: str
    sentence_index: int
    section: str
    similarity_score: float
    matched_anchors: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class CitationCandidate:
    """A citation candidate ready for injection review"""
    paper: PaperIntel
    target_sentence: str
    section: str
    similarity_score: float
    reason: str
    is_rejected: bool = False
    rejection_reason: str = ""
    routing_rule: str = ""       # which routing rule was applied
    if_gate: str = ""            # "ELITE_PASS" / "GLOBAL_PASS" / "BELOW_GLOBAL" / "BELOW_ELITE"
    # ISSUE-003: keep the already-ranked, policy-valid alternatives selected by
    # this mapper.  CandidateAdapter and Injector deliberately do not interpret
    # this data; it is only consumed here while assigning sentence capacity.
    ranked_alternatives: list[dict] = field(default_factory=list)
    original_best_rank: int = 0
    selected_rank: int = 0
    original_target: str = ""
    selected_target: str = ""
    reroute_reason: str = ""
    attempted_candidate_count: int = 0
    reroute_attempts: list[dict] = field(default_factory=list)


class SemanticMapper:
    """Phase 3: Map papers to manuscript sentences via semantic anchors

    Usage:
        mapper = SemanticMapper()
        candidates = mapper.map_papers_to_manuscript(papers, manuscript_text)
        table = mapper.generate_candidate_table(candidates)
    """

    MAX_PAPERS_PER_SENTENCE = 3
    MAX_PARAGRAPH_PAPERS = 8
    MIN_SIMILARITY_THRESHOLD = 0.15
    REJECTED_SECTIONS = ['abstract', 'keywords']

    def __init__(self):
        self._sentences: list[str] = []
        self._sections: list[str] = []
        self._sentence_to_section: dict[int, str] = {}
        self._sentence_is_table: dict[int, bool] = {}
        self._section_classifier_terms = get_section_classifier_terms()

    # ---- Public API ----

    def map_papers_to_manuscript(
        self, papers: list[PaperIntel], manuscript_text: str,
        journal_if_map: Optional[dict[str, float]] = None,
    ) -> list[CitationCandidate]:
        """Map papers to manuscript sentences with full routing rules"""
        self._parse_manuscript(manuscript_text)
        candidates = []

        for paper in papers:
            # === IF Gate ===
            paper_if = self._get_paper_if(paper, journal_if_map)
            paper.if_score = paper_if  # attach for downstream use

            # === Type-based routing ===
            if paper.paper_type == 'review':
                candidate = self._route_review_paper(paper, paper_if)
            else:
                candidate = self._route_research_paper(paper, paper_if)

            if candidate is None:
                candidates.append(CitationCandidate(
                    paper=paper, target_sentence="", section="",
                    similarity_score=0.0, reason="",
                    is_rejected=True, rejection_reason="ROUTING: no valid section matched",
                ))
            else:
                candidates.append(candidate)

        candidates = self._enforce_sentence_limits(candidates)
        return candidates

    def generate_candidate_table(self, candidates: list[CitationCandidate]) -> str:
        """Generate citation candidate markdown table with IF gate status"""
        lines = []
        lines.append('# CiteMatch v2.2 — Citation Candidate Table')
        lines.append('')
        lines.append(f'| # | Paper | Type | IF Gate | Target | Section | Score | Reason | Status |')
        lines.append(f'|---|-------|------|---------|--------|---------|-------|--------|--------|')

        accepted = [c for c in candidates if not c.is_rejected]
        rejected = [c for c in candidates if c.is_rejected]

        for i, c in enumerate(accepted, 1):
            sent = c.target_sentence[:50] + '...' if len(c.target_sentence) > 50 else c.target_sentence
            ptype = c.paper.paper_type[:6]
            if_gate = c.if_gate or '—'
            lines.append(
                f'| {i} | @{c.paper.citekey} | {ptype} | {if_gate} | '
                f'{sent} | {c.section[:25]} | {c.similarity_score:.2f} | '
                f'{c.reason[:30]} | ✅ {c.routing_rule} |'
            )

        for i, c in enumerate(rejected, len(accepted) + 1):
            ptype = c.paper.paper_type[:6]
            lines.append(
                f'| {i} | @{c.paper.citekey} | {ptype} | — | — | — | — | '
                f'{c.rejection_reason[:50]} | ❌ |'
            )

        lines.append('')
        lines.append(f'**Accepted**: {len(accepted)} | **Floating**: {len(rejected)}')
        return '\n'.join(lines)

    # ---- Internal: Type-Based Routing ----

    def _route_review_paper(
        self, paper: PaperIntel, paper_if: float
    ) -> Optional[CitationCandidate]:
        """Route review paper — Introduction/background only"""
        matches = self._find_matches(paper)

        # Filter: only allow introduction/background sections
        intro_matches = [m for m in matches if self._is_intro_section(m.section)]

        if not intro_matches:
            return CitationCandidate(
                paper=paper, target_sentence="", section="",
                similarity_score=0.0, reason="",
                is_rejected=True,
                rejection_reason="TYPE: review paper — no Introduction/background match",
                routing_rule="REVIEW→INTRO_ONLY",
            )

        return self._candidate_from_ranked_matches(
            paper, intro_matches, paper_if, "REVIEW→INTRO"
        )

    def _route_research_paper(
        self, paper: PaperIntel, paper_if: float
    ) -> Optional[CitationCandidate]:
        """Route research paper by contribution type"""
        matches = self._find_matches(paper)

        if not matches:
            return None

        # Classify contribution type
        contrib = self._classify_contribution(paper)

        # Filter matches by contribution-allowed sections
        allowed = CONTRIBUTION_ROUTING.get(contrib, [])
        routed_matches = [
            m for m in matches
            if any(kw in m.section.lower() for kw in allowed)
        ]

        if not routed_matches:
            # Fall back to original best match if no routed match
            selected_matches = matches
            routed = False
        else:
            selected_matches = routed_matches
            routed = True

        rule = f'RESEARCH→{contrib.upper()}' if routed else 'RESEARCH→FALLBACK'
        return self._candidate_from_ranked_matches(
            paper, selected_matches, paper_if, rule
        )

    def _candidate_from_ranked_matches(
        self, paper: PaperIntel, matches: list[AnchorMatch], paper_if: float,
        routing_rule: str,
    ) -> CitationCandidate:
        """Build one candidate while retaining this mapper's ranked matches.

        The alternatives are not a new matching system: they are the existing
        ``_find_matches`` result after the same routing/protected-zone filters.
        """
        best = matches[0]
        alternatives = [
            {
                "rank": rank,
                "sentence_index": match.sentence_index,
                "target_sentence": match.sentence,
                "section": match.section,
                "is_in_table": self._sentence_is_table.get(
                    match.sentence_index, False
                ),
                "similarity_score": match.similarity_score,
                "reason": match.reason,
            }
            for rank, match in enumerate(matches, 1)
        ]
        return CitationCandidate(
            paper=paper, target_sentence=best.sentence,
            section=best.section, similarity_score=best.similarity_score,
            reason=best.reason, routing_rule=routing_rule,
            if_gate=self._evaluate_if_gate(best.sentence, paper_if),
            ranked_alternatives=alternatives,
            original_best_rank=1,
            selected_rank=1,
            original_target=best.sentence,
            selected_target=best.sentence,
        )

    # ---- Internal: IF Gate ----

    @staticmethod
    def _get_paper_if(paper: PaperIntel, journal_if_map: Optional[dict]) -> float:
        """Get paper IF from journal map or return 0"""
        if journal_if_map and paper.journal:
            # Normalize journal name for lookup
            j_norm = paper.journal.lower().replace('.', '').replace(' ', '')
            for j_name, j_if in journal_if_map.items():
                if j_name.replace('.', '').replace(' ', '').lower() == j_norm:
                    return j_if
            # Partial match
            for j_name, j_if in journal_if_map.items():
                short = j_name.replace('.', '').replace(' ', '').lower()[:15]
                if j_norm[:15] == short:
                    return j_if
        return 0.0

    @staticmethod
    def _evaluate_if_gate(sentence: str, paper_if: float) -> str:
        """Evaluate IF gate for a target sentence

        Returns: ELITE_PASS / GLOBAL_PASS / BELOW_ELITE / BELOW_GLOBAL / UNKNOWN
        """
        if paper_if <= 0:
            return 'UNKNOWN'

        is_table = '|' in sentence and sentence.count('|') >= 2

        if is_table:
            if paper_if >= IF_THRESHOLD_ELITE:
                return 'ELITE_PASS'
            else:
                return 'BELOW_ELITE'
        else:
            if paper_if >= IF_THRESHOLD_GLOBAL:
                return 'GLOBAL_PASS'
            else:
                return 'BELOW_GLOBAL'

    # ---- Internal: Contribution Classification ----

    @staticmethod
    def _classify_contribution(paper: PaperIntel) -> str:
        """Classify paper's primary contribution type"""
        text = (paper.title + ' ' + paper.core_finding + ' ' +
                ' '.join(paper.technical_keywords)).lower()

        scores = {}
        for contrib, keywords in CONTRIBUTION_ROUTING.items():
            score = sum(1 for kw in keywords if kw in text)
            scores[contrib] = score

        if max(scores.values()) == 0:
            return 'material'  # default

        return max(scores, key=scores.get)

    # ---- Internal: Section Checks ----

    @staticmethod
    def _is_intro_section(section: str) -> bool:
        """Check if section is introduction/background"""
        sec = section.lower()
        return any(kw in sec for kw in INTRODUCTION_KEYWORDS)

    @staticmethod
    def _is_quantitative_sentence(sentence: str) -> bool:
        """Check if sentence makes a quantitative performance claim"""
        sent = sentence.lower()
        return any(re.search(p, sent) for p in QUANTITATIVE_CLAIM_PATTERNS)

    # ---- Internal: Parsing + Matching ----

    def _parse_manuscript(self, text: str):
        """Parse manuscript into sentences with section tracking"""
        self._sentences = []
        self._sections = []
        self._sentence_to_section = {}
        self._sentence_is_table = {}

        lines = text.split('\n')
        current_section = '(preamble)'
        in_table = False
        in_figure_caption = False
        sentence_idx = 0
        ast = MarkdownAST(text)
        ast.parse()

        for line_number, line in enumerate(lines, 1):
            stripped = line.strip()

            if ast.is_heading_line(line_number):
                current_section = ast.get_section_for_line(line_number)[:80]
                in_table = False
                in_figure_caption = False  # heading ends figure block
                continue

            if not stripped: continue

            current_section = ast.get_section_for_line(line_number) or '(preamble)'
            if ast.is_in_protected_zone(line_number):
                continue

            # Detect table rows
            is_table_line = '|' in stripped and stripped.count('|') >= 2
            if is_table_line and not in_table:
                in_table = True

            # Track figure caption zones
            if stripped.startswith('![') and '](' in stripped:
                in_figure_caption = True
                continue  # image ref line — skip
            if in_figure_caption and not stripped:
                # Blank lines within figure blocks are normal — stay in figure mode
                continue
            if in_figure_caption:
                continue  # === FIGURE CAPTION ZONE: absolute exclusion for NEW injection ===

            if stripped.startswith('Figure') and len(stripped) < 30: continue
            if re.match(r'^\[@[\w\s;]+\]$', stripped): continue

            sents = re.split(r'(?<=[.!?。！？])\s+', stripped)
            for sent in sents:
                sent = sent.strip()
                if len(sent) < 10: continue
                self._sentences.append(sent)
                self._sections.append(current_section)
                self._sentence_to_section[sentence_idx] = current_section
                self._sentence_is_table[sentence_idx] = is_table_line
                sentence_idx += 1

    def _find_matches(self, paper: PaperIntel) -> list[AnchorMatch]:
        """Find manuscript sentences matching paper's semantic anchors"""
        matches = []

        for idx, sentence in enumerate(self._sentences):
            section = self._sections[idx]

            if self._is_rejected_zone(section, sentence, paper.paper_type):
                continue

            sent_lower = sentence.lower()
            hit_anchors = [a for a in paper.semantic_anchors if a.lower() in sent_lower]

            if not hit_anchors: continue

            score = len(hit_anchors) / max(len(paper.semantic_anchors), 1)
            if score >= self.MIN_SIMILARITY_THRESHOLD:
                matches.append(AnchorMatch(
                    paper=paper, sentence=sentence, sentence_index=idx,
                    section=section, similarity_score=round(score, 3),
                    matched_anchors=hit_anchors,
                    reason=self._build_reason(hit_anchors, score),
                ))

        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    def _is_rejected_zone(
        self, section: str, sentence: str, paper_type: str = 'research'
    ) -> bool:
        """Check if sentence is in a protected zone"""
        sec_lower = section.lower()
        sent_lower = sentence.lower()

        # === ABSOLUTE EXCLUSION: Abstract / Keywords ===
        if is_protected_section_title(section, self._section_classifier_terms):
            return True

        # === ABSOLUTE EXCLUSION: Figure captions (section named after image) ===
        if sec_lower.startswith("!["):
            return True

        # === ABSOLUTE EXCLUSION: Figure captions ===
        if sent_lower.startswith('figure') and len(sentence) < 100:
            return True
        if re.match(r'^[（(][a-z][）)]', sent_lower):
            return True

        # === "This work" / original contribution ===
        if re.search(
            r'(this\s+(work|paper|study|review)|we\s+(propose|develop|present|introduce|demonstrate))',
            sent_lower
        ):
            return True

        # === REVIEW PAPER: forbidden in quantitative claims ===
        if paper_type == 'review' and self._is_quantitative_sentence(sentence):
            return True

        return False

    # ---- Internal: Helpers ----

    @staticmethod
    def _build_reason(hit_anchors: list[str], score: float) -> str:
        anchors_str = ', '.join(hit_anchors[:3])
        if len(hit_anchors) > 3:
            anchors_str += f' +{len(hit_anchors)-3} more'
        return f'Anchors: {anchors_str} (score={score:.2f})'

    def _enforce_sentence_limits(
        self, candidates: list[CitationCandidate]
    ) -> list[CitationCandidate]:
        """Keep the current top-three primary assignment, then reroute overflow.

        Existing manuscript citations are intentionally not counted here: this
        is a placement limit for *new candidates* only.  Alternatives have
        already passed semantic, section, and protected-zone filtering.
        """
        primary_groups: dict[int, list[CitationCandidate]] = {}
        overflow: list[CitationCandidate] = []
        occupancy: dict[int, int] = {}

        for candidate in candidates:
            if candidate.is_rejected or not candidate.target_sentence:
                continue
            alternatives = candidate.ranked_alternatives
            if not alternatives:
                # Backward-compatible candidates cannot safely be rerouted.
                candidate.is_rejected = True
                candidate.rejection_reason = "no_safe_alternative_location"
                candidate.attempted_candidate_count = 0
                continue
            primary_groups.setdefault(
                int(alternatives[0]["sentence_index"]), []
            ).append(candidate)

        # Preserve the prior primary-target result: the top three scores remain
        # at each initial sentence.  Only surplus candidates enter rerouting.
        for sentence_index, papers in primary_groups.items():
            papers.sort(key=lambda item: (-item.similarity_score, item.paper.citekey))
            retained = papers[:self.MAX_PAPERS_PER_SENTENCE]
            occupancy[sentence_index] = len(retained)
            for candidate in retained:
                candidate.selected_rank = 1
                candidate.selected_target = candidate.target_sentence
                candidate.attempted_candidate_count = 1
            overflow.extend(papers[self.MAX_PAPERS_PER_SENTENCE:])

        # A density overflow gets every existing ranked alternative, in order.
        for candidate in overflow:
            attempts = []
            assigned = False
            primary_is_table = bool(candidate.ranked_alternatives[0].get(
                "is_in_table", False
            ))
            for alternative in candidate.ranked_alternatives:
                rank = int(alternative["rank"])
                sentence_index = int(alternative["sentence_index"])
                if rank == 1:
                    attempts.append({
                        "rank": rank,
                        "target_sentence": alternative["target_sentence"],
                        "reason": "sentence_density_full",
                    })
                    continue
                if bool(alternative.get("is_in_table", False)) != primary_is_table:
                    attempts.append({
                        "rank": rank,
                        "target_sentence": alternative["target_sentence"],
                        "reason": "table_context_mismatch",
                    })
                    continue
                if occupancy.get(sentence_index, 0) >= self.MAX_PAPERS_PER_SENTENCE:
                    attempts.append({
                        "rank": rank,
                        "target_sentence": alternative["target_sentence"],
                        "reason": "sentence_density_full",
                    })
                    continue

                occupancy[sentence_index] = occupancy.get(sentence_index, 0) + 1
                candidate.target_sentence = alternative["target_sentence"]
                candidate.section = alternative["section"]
                candidate.similarity_score = float(alternative["similarity_score"])
                candidate.reason = alternative["reason"]
                candidate.selected_rank = rank
                candidate.selected_target = candidate.target_sentence
                candidate.reroute_reason = "sentence_density_overflow"
                attempts.append({
                    "rank": rank,
                    "target_sentence": candidate.target_sentence,
                    "reason": "selected",
                })
                assigned = True
                break

            candidate.reroute_attempts = attempts
            candidate.attempted_candidate_count = len(attempts)
            if not assigned:
                candidate.is_rejected = True
                candidate.rejection_reason = "no_safe_alternative_location"
                candidate.reroute_reason = "sentence_density_overflow"

        return candidates
