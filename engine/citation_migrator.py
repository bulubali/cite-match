"""
CiteMatch v2.2.1 — Citation Migrator

Two independent rules:
  Rule 1: Existing static citations [N] in figure captions MUST be migrated to [@citekey]
  Rule 2: New semantic injection papers MUST NEVER be inserted into figure captions

Responsibilities:
  - Scan body, table, and figure caption zones
  - Convert all legacy \\[N\\]^ citations to verified Pandoc [@citekey]
  - Preserve physical position and caption text
  - Report migration coverage by zone
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from collections import OrderedDict


@dataclass
class MigrationZone:
    """A text zone in the manuscript"""
    zone_type: str           # "body" / "figure_caption" / "table" / "abstract" / "heading"
    line_start: int
    line_end: int
    content: str = ""
    citation_count: int = 0
    migrated_count: int = 0


@dataclass
class MigrationReport:
    """Migration coverage report"""
    total_citations: int = 0
    total_migrated: int = 0
    body_citations: int = 0
    body_migrated: int = 0
    figure_citations: int = 0
    figure_migrated: int = 0
    table_citations: int = 0
    table_migrated: int = 0
    abstract_citations: int = 0
    abstract_migrated: int = 0
    zones: list[MigrationZone] = field(default_factory=list)
    unmigrated: list[dict] = field(default_factory=list)

    def coverage_summary(self) -> str:
        lines = [
            '## Migration Coverage Report',
            '',
            '| Zone | Citations | Migrated | Coverage |',
            '|------|-----------|----------|----------|',
            f'| Body | {self.body_citations} | {self.body_migrated} | {self._pct(self.body_migrated, self.body_citations)} |',
            f'| Figure Captions | {self.figure_citations} | {self.figure_migrated} | {self._pct(self.figure_migrated, self.figure_citations)} |',
            f'| Tables | {self.table_citations} | {self.table_migrated} | {self._pct(self.table_migrated, self.table_citations)} |',
            f'| Abstract | {self.abstract_citations} | {self.abstract_migrated} | {self._pct(self.abstract_migrated, self.abstract_citations)} |',
            f'| **Total** | **{self.total_citations}** | **{self.total_migrated}** | **{self._pct(self.total_migrated, self.total_citations)}** |',
        ]
        return '\n'.join(lines)

    @staticmethod
    def _pct(part, total):
        if total == 0: return 'N/A'
        return f'{100 * part // total}%'


class CitationMigrator:
    """Migrate all legacy \\[N\\]^ citations to [@citekey] across all zones

    Usage:
        migrator = CitationMigrator(num_to_key_mapping, bib_entries)
        migrated_text, report = migrator.migrate_all(manuscript_text)
    """

    BS = chr(92)

    def __init__(self, num_to_key: dict[int, str]):
        self._num_to_key = num_to_key

    def migrate_all(self, text: str) -> tuple[str, MigrationReport]:
        """Migrate all legacy citations in all zones

        Returns:
            (migrated_text, MigrationReport)
        """
        report = MigrationReport()
        zones = self._identify_zones(text)
        report.zones = zones

        # Build line-indexed conversion
        lines = text.split('\n')
        migrated_lines = list(lines)

        total_conv = 0

        for zone in zones:
            zone_citations = 0
            zone_migrated = 0

            for line_idx in range(zone.line_start - 1, zone.line_end):
                if line_idx >= len(migrated_lines):
                    continue
                line = migrated_lines[line_idx]
                new_line, conv_count = self._convert_line(line)
                if conv_count > 0:
                    migrated_lines[line_idx] = new_line
                    zone_citations += conv_count
                    zone_migrated += conv_count

            zone.citation_count = zone_citations
            zone.migrated_count = zone_migrated

            # Accumulate in report
            if zone.zone_type == 'body':
                report.body_citations += zone_citations
                report.body_migrated += zone_migrated
            elif zone.zone_type == 'figure_caption':
                report.figure_citations += zone_citations
                report.figure_migrated += zone_migrated
            elif zone.zone_type == 'table':
                report.table_citations += zone_citations
                report.table_migrated += zone_migrated
            elif zone.zone_type == 'abstract':
                report.abstract_citations += zone_citations
                report.abstract_migrated += zone_migrated

            total_conv += zone_migrated

        report.total_citations = (
            report.body_citations + report.figure_citations +
            report.table_citations + report.abstract_citations
        )
        report.total_migrated = total_conv

        return '\n'.join(migrated_lines), report

    # ---- Zone Detection ----

    def _identify_zones(self, text: str) -> list[MigrationZone]:
        """Identify all text zones in the manuscript"""
        lines = text.split('\n')
        zones = []
        i = 0
        current_zone_type = 'body'
        current_zone_start = 1
        in_figure_block = False
        heading_level = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Heading detection
            heading_match = re.match(r'^(#{1,6})\s+', stripped)
            if heading_match:
                # Close previous zone
                if i >= current_zone_start:
                    zones.append(MigrationZone(
                        zone_type=current_zone_type,
                        line_start=current_zone_start,
                        line_end=i,
                    ))

                heading_level = len(heading_match.group(1))
                heading_text = re.sub(r'^#{1,6}\s+', '', stripped)[:80]

                # Classify zone based on heading
                if re.search(r'abstract', heading_text, re.IGNORECASE):
                    current_zone_type = 'abstract'
                else:
                    current_zone_type = 'body'

                current_zone_start = i + 1
                in_figure_block = False  # heading ends figure block
                i += 1
                continue

            # Image reference detection — opens a figure caption block
            if stripped.startswith('![') and '](' in stripped:
                in_figure_block = True
                # The image line itself is not a caption
                i += 1
                continue

            # Figure caption text (after image ref, before next heading)
            if in_figure_block and stripped:
                if not stripped.startswith('!['):
                    # This is figure caption text — classify as figure_caption
                    if current_zone_type != 'figure_caption':
                        if i >= current_zone_start:
                            zones.append(MigrationZone(
                                zone_type=current_zone_type,
                                line_start=current_zone_start,
                                line_end=i,
                            ))
                        current_zone_type = 'figure_caption'
                        current_zone_start = i + 1

            # Empty line DURING figure block → keep in figure_caption mode
            # (blank lines between image and caption text are normal)
            if in_figure_block and not stripped:
                # Stay in figure_caption — blank lines within figure blocks are normal
                if current_zone_type == 'figure_caption':
                    i += 1
                    continue
                # If we're still in figure_block but zone hasn't switched to figure_caption yet,
                # this is a blank line between image and caption
                i += 1
                continue

            # Table detection — supports both pipe tables and Pandoc grid tables
            is_pipe_row = '|' in stripped and stripped.count('|') >= 2
            is_pipe_sep = bool(re.match(r'^\|?[\s:-]+\|[\s|:-]+\|?$', stripped))
            # Pandoc grid table separator: line of dashes (with optional =, +)
            is_grid_sep = bool(re.match(r'^[\s\-=+:]+$', stripped) and stripped.count('-') >= 6)

            if (is_pipe_row or is_grid_sep) and current_zone_type not in ('table', 'figure_caption'):
                if is_pipe_row and not is_pipe_sep:
                    # Pipe table data row — check next line for separator
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if re.match(r'^\|?[\s:-]+\|[\s|:-]+\|?$', next_line):
                            if i >= current_zone_start:
                                zones.append(MigrationZone(
                                    zone_type=current_zone_type,
                                    line_start=current_zone_start,
                                    line_end=i,
                                ))
                            current_zone_type = 'table'
                            current_zone_start = i + 1
                elif is_grid_sep:
                    # Grid table separator row — this IS the table boundary
                    if i >= current_zone_start:
                        zones.append(MigrationZone(
                            zone_type=current_zone_type,
                            line_start=current_zone_start,
                            line_end=i,
                        ))
                    current_zone_type = 'table'
                    current_zone_start = i + 1

            # Stay in table zone until end of table content
            elif current_zone_type == 'table' and not stripped:
                # End of table: empty line after table data
                if i > current_zone_start:
                    # Check if next line starts a new section
                    next_non_empty = None
                    for j in range(i + 1, min(len(lines), i + 5)):
                        if lines[j].strip():
                            next_non_empty = lines[j].strip()
                            break
                    if next_non_empty:
                        is_next_table = (
                            ('|' in next_non_empty and next_non_empty.count('|') >= 2) or
                            bool(re.match(r'^[\s\-=+:]+$', next_non_empty) and next_non_empty.count('-') >= 6)
                        )
                        if not is_next_table:
                            zones.append(MigrationZone(
                                zone_type='table',
                                line_start=current_zone_start,
                                line_end=i,
                            ))
                            current_zone_type = 'body'
                            current_zone_start = i + 1

            i += 1

        # Close final zone
        if len(lines) >= current_zone_start:
            zones.append(MigrationZone(
                zone_type=current_zone_type,
                line_start=current_zone_start,
                line_end=len(lines),
            ))

        return zones

    # ---- Line Conversion ----

    def _convert_line(self, line: str) -> tuple[str, int]:
        """Convert all \\[N\\]^ and \\[N,M\\]^ patterns in a line to [@citekey]

        Preserves all non-citation text exactly.
        Returns (converted_line, conversion_count)
        """
        result = []
        i = 0
        conv_count = 0

        while i < len(line):
            if i + 2 < len(line) and line[i:i+2] == self.BS + '[':
                j = i + 2
                end = line.find(self.BS + ']', j)
                if end > j and end - j < 50:
                    inner = line[j:end]
                    has_caret_prefix = i > 0 and line[i-1] == '^'
                    has_caret_suffix = end + 2 < len(line) and line[end+2] == '^'

                    pandoc_parts = []
                    for part in re.split(r'[,;\s]+', inner.strip()):
                        part = part.strip()
                        if not part: continue
                        range_match = re.match(r'(\d+)\s*[-–]+\s*(\d+)', part)
                        if range_match:
                            for n in range(int(range_match.group(1)), int(range_match.group(2)) + 1):
                                key = self._num_to_key.get(n)
                                if key: pandoc_parts.append(f'@{key}')
                        else:
                            try:
                                n = int(part)
                                key = self._num_to_key.get(n)
                                if key: pandoc_parts.append(f'@{key}')
                            except ValueError: pass

                    if pandoc_parts:
                        replacement = f'[{"; ".join(pandoc_parts)}]'
                        if has_caret_prefix: result.append('^')
                        result.append(replacement)
                        if has_caret_suffix: result.append('^')
                        conv_count += 1
                        i = end + 2
                        if has_caret_suffix and i < len(line) and line[i] == '^':
                            i += 1
                    else:
                        result.append(line[i]); i += 1
                else:
                    result.append(line[i]); i += 1
            else:
                result.append(line[i]); i += 1

        return ''.join(result), conv_count


def build_mapping_from_manuscript(
    zh_text: str, bib_entries: dict, manual_map: Optional[dict] = None
) -> dict[int, str]:
    """Build [N] → @citekey mapping from manuscript reference list + bib"""
    BS = chr(92)
    if manual_map is None:
        manual_map = {}

    # Build bib index
    bib_by_author_year = {}
    for key, entry in bib_entries.items():
        fa = entry.first_author_surname.lower().replace('-', '')
        bib_by_author_year.setdefault((fa, entry.year), []).append(key)

    # Find reference list
    ref_start = zh_text.rfind(BS + '[1' + BS + ']')
    if ref_start < 0:
        return {}
    ref_section = zh_text[ref_start:]

    ref_pattern = re.compile(
        re.escape(BS) + r'\[(\d+)' + re.escape(BS) + r'\]\s+(.*?)(?=\s*'
        + re.escape(BS) + r'\[\d+' + re.escape(BS) + r'\]|\s*\Z)', re.DOTALL)

    num_to_key = OrderedDict()

    for match in ref_pattern.finditer(ref_section):
        num = int(match.group(1))
        if num > 59: break
        content = match.group(2).strip()

        if num in manual_map:
            num_to_key[num] = manual_map[num]
            continue

        author_match = re.match(
            r'((?:[A-Z][a-z]*\.(?:\-[A-Z][a-z]*\.)?\s)*[A-Z][a-z\-]+(?:\s+[A-Z][a-z]+)?)', content)
        surname = author_match.group(1).strip().split()[-1].lower().replace('-', '') if author_match else ''
        year_match = re.search(r'\*?\*?(\d{4})\*?\*?', content)
        year = year_match.group(1) if year_match else ''

        if surname and year:
            candidates = bib_by_author_year.get((surname, year), [])
            if len(candidates) == 1:
                num_to_key[num] = candidates[0]
            elif len(candidates) > 1:
                # Disambiguate by volume + page from reference text
                vol_match = re.search(r'\*\*?\d{4}\*\*?,\s*\*?(\d+)\*?,\s*(\d+)', content)
                best_key = None
                if vol_match:
                    ref_vol, ref_page = vol_match.group(1), vol_match.group(2)
                    for ck in candidates:
                        entry = bib_entries.get(ck)
                        if entry:
                            bv = entry.fields.get('volume', '')
                            bp = entry.fields.get('pages', '')
                            bp_first = re.match(r'(\d+)', bp.replace('--', '-'))
                            if bv == ref_vol and bp_first and bp_first.group(1) == ref_page:
                                best_key = ck
                                break
                # Fallback: journal name similarity
                if not best_key:
                    journal_match = re.search(r'\*([A-Z][A-Za-z .&]+)\*', content)
                    ref_journal = journal_match.group(1).strip().lower() if journal_match else ''
                    if ref_journal:
                        for ck in candidates:
                            entry = bib_entries.get(ck)
                            if entry and entry.journal:
                                j_norm = entry.journal.lower().replace('.', ' ').replace('  ', ' ').strip()
                                rj_norm = ref_journal.replace('.', ' ').replace('  ', ' ').strip()
                                if j_norm[:15] == rj_norm[:15] or rj_norm[:15] in j_norm:
                                    best_key = ck
                                    break
                # Last resort: first candidate
                if not best_key:
                    best_key = candidates[0]
                num_to_key[num] = best_key

    return dict(num_to_key)
