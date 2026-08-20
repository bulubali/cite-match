"""
CiteMatch v2.5.x — Legacy Citation Migration Engine
ISSUE-004: Maps old numeric citations ^[1,2]^ to Pandoc [@key1; @key2] format.

Pipeline position: Between Mode C cleanup and Phase 1 delta detection.

Usage:
    from engine.legacy_migration import build_mapping, apply_migration

    mapping, report = build_migration(draft_with_refs_path, bib_path)
    migrated_text, count = apply_migration(cleaned_draft_text, mapping)
"""
from difflib import SequenceMatcher
import re
import unicodedata

try:
    from .bib_parser import BibTeXParser
except ImportError:  # Direct engine-path imports used by the existing CLI/tests.
    from bib_parser import BibTeXParser


def build_migration(draft_with_refs_path: str, bib_path: str) -> tuple:
    """Build mapping from old numeric refs to .bib CiteKeys.

    Args:
        draft_with_refs_path: Draft WITH References section intact (pre-Mode-C)
        bib_path: Path to .bib file

    Returns:
        mapping: dict {str: str}  e.g. {"1": "tanArtificial2022", "2": "parkHighly2025"}
        report: dict with statistics and per-entry detail
    """
    with open(draft_with_refs_path, 'r', encoding='utf-8') as f:
        draft = f.read()
    with open(bib_path, 'r', encoding='utf-8') as f:
        bib_content = f.read()

    ref_entries = _parse_references(draft)
    bib_index = _index_bib(bib_content)

    mapping = {}
    details_by_number = {}

    for num in sorted(ref_entries.keys()):
        entry = ref_entries[num]
        decision = _match_entry(entry, bib_index)
        detail = {
            'num': num,
            'first_author': entry['first_author'],
            'year': entry['year'],
            'journal': entry.get('journal', '')[:60],
            'raw': entry.get('raw', ''),
            'parsed': _public_reference_metadata(entry),
            'matched_key': decision['matched_key'],
            'score': decision['score'],
            'status': decision['status'],
            'decision_reason': decision['reason'],
            'candidates': decision['candidates'],
            'candidate_details': decision['candidate_details'],
        }
        details_by_number[num] = detail
        if decision['status'] == 'matched':
            mapping[str(num)] = decision['matched_key']

    many_to_one = []
    unsafe_many_to_one = []
    key_to_numbers = {}
    for number, key in mapping.items():
        key_to_numbers.setdefault(key, []).append(number)
    for key, numbers in key_to_numbers.items():
        if len(numbers) < 2:
            continue
        references = [ref_entries[int(number)] for number in numbers]
        if all(_references_equivalent(references[0], other)
               for other in references[1:]):
            many_to_one.append({
                'citekey': key,
                'numbers': sorted(numbers, key=int),
                'verified_duplicate': True,
                'reason': 'equivalent_legacy_bibliographic_identity',
            })
            continue

        conflict = {
            'citekey': key,
            'numbers': sorted(numbers, key=int),
            'verified_duplicate': False,
            'reason': 'different_legacy_references_share_candidate',
        }
        unsafe_many_to_one.append(conflict)
        for number in numbers:
            mapping.pop(number, None)
            detail = details_by_number[int(number)]
            detail['status'] = 'unsafe'
            detail['decision_reason'] = conflict['reason']
            detail['matched_key'] = None

    details = [details_by_number[num] for num in sorted(details_by_number)]
    mapped = [detail for detail in details if detail['status'] == 'matched']
    ambiguous = [detail for detail in details if detail['status'] == 'ambiguous']
    unmapped = [detail for detail in details if detail['status'] == 'unmapped']
    unsafe = [detail for detail in details if detail['status'] == 'unsafe']

    report = {
        'total': len(ref_entries),
        'mapped': len(mapped),
        'unmapped_count': len(unmapped),
        'ambiguous_count': len(ambiguous),
        'unsafe_count': len(unsafe),
        'mapped_list': mapped,
        'ambiguous_list': ambiguous,
        'unmapped_list': unmapped,
        'unsafe_list': unsafe,
        'many_to_one_list': many_to_one,
        'unsafe_many_to_one_list': unsafe_many_to_one,
        'mapping_pct': round(100 * len(mapped) / max(len(ref_entries), 1), 1),
    }
    return mapping, report


def apply_migration(draft_text: str, mapping: dict) -> tuple:
    """Replace legacy numeric citations with Pandoc [@key] format.

    Args:
        draft_text: Draft body (after Mode C cleanup)
        mapping: {"1": "key1", "2": "key2", ...}

    Returns:
        (migrated_text: str, replacement_count: int)
    """
    counter = [0]  # mutable counter for closure

    def _replace_one(match):
        inner = next(group for group in match.groups() if group is not None)
        parts = [part.strip() for part in re.split(r'[,;]', inner)]
        keys = []
        all_mapped = True
        for part in parts:
            range_m = re.match(r'(\d+)\s*(?:--?|–)\s*(\d+)', part)
            if range_m:
                range_keys = []
                for n in range(int(range_m.group(1)), int(range_m.group(2)) + 1):
                    if str(n) in mapping:
                        range_keys.append(mapping[str(n)])
                    else:
                        all_mapped = False
                keys.extend(range_keys)
            else:
                if part in mapping:
                    keys.append(mapping[part])
                else:
                    all_mapped = False
        # Only replace if ALL numbers in this citation are mapped
        if keys and all_mapped:
            counter[0] += 1
            return '[' + '; '.join(f'@{k}' for k in keys) + ']'
        return match.group(0)  # preserve original if any part is unmapped

    migrated = re.sub(r'\^\\\[([^\]]+?)\\\]\^', _replace_one, draft_text)
    migrated = re.sub(r'\\\[([0-9][0-9,;\s\-–—]*?)\\\]',
                      _replace_one, migrated)
    migrated = re.sub(r'(?<!\\)\[([0-9][0-9,;\s\-–—]*?)\](?!\()',
                      _replace_one, migrated)
    return migrated, counter[0]


# ── Internal ──────────────────────────────────────────────

def _parse_references(draft: str) -> dict:
    """Parse stable bibliographic fields from the legacy References section."""
    # Find the **References** marker
    ref_marker = re.search(r'\*\*References\*\*', draft)
    if not ref_marker:
        ref_marker = re.search(r'^#+\s*References?\s*$', draft, re.MULTILINE)
    if not ref_marker:
        return {}

    section = draft[ref_marker.end():]
    entries = {}

    # Split into individual entries.
    # Format in Pandoc markdown: \[1\] Author...  (single backslash escaping)
    # Python string repr shows: '\\[1\\] Author...' (each \ shown as \\)
    normalized = section.strip()

    BS = chr(92)  # backslash character

    # Match pattern: BS [ digits BS ] i.e. "\[1\]"
    positions = []
    search_pos = 0
    while True:
        # Look for "\" (BS) then "["
        bs_pos = normalized.find(BS, search_pos)
        if bs_pos < 0:
            break
        # Check if next char is "[", then digits, then "\", then "]"
        if (bs_pos + 1 < len(normalized) and normalized[bs_pos+1] == '['):
            # Found "\ [", now find closing "\ ]"
            close_bs = normalized.find(BS, bs_pos + 2)
            if close_bs > 0 and close_bs + 1 < len(normalized) and normalized[close_bs+1] == ']':
                num_str = normalized[bs_pos+2:close_bs].strip()
                if num_str.isdigit():
                    positions.append((bs_pos, int(num_str)))
                search_pos = close_bs + 2
            else:
                search_pos = bs_pos + 2
        else:
            search_pos = bs_pos + 1

    # Extract blocks between positions
    blocks = []
    for i, (pos, num) in enumerate(positions):
        next_pos = positions[i+1][0] if i+1 < len(positions) else len(normalized)
        block_text = normalized[pos:next_pos].strip()
        blocks.append((num, block_text))

    for num, block in blocks:
        marker_end = block.find(']', block.find(BS))
        body = block[marker_end + 1:].strip() if marker_end > 0 else block
        entries[num] = _parse_reference_body(body, block.strip())

    return entries


_INITIALS_AND_SURNAME = re.compile(
    r'^(?:(?:[A-Z][a-z]*\.(?:-[A-Z][a-z]*\.)?)\s*)+(.+)$'
)


def _parse_reference_body(body: str, raw: str) -> dict:
    """Extract only fields actually present in a formatted reference."""
    doi_match = re.search(
        r'(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)',
        body, re.IGNORECASE,
    )
    doi = _normalize_doi(doi_match.group(1)) if doi_match else ''

    journal_match = re.search(r'\*([^*]+?)\*', body)
    journal = journal_match.group(1).strip() if journal_match else ''
    prefix = body[:journal_match.start()].rstrip(' ,.;') if journal_match else body
    author_chunks, title = _split_authors_and_title(prefix)
    authors = [_normalize_text(author) for author in author_chunks if author]

    search_start = journal_match.end() if journal_match else 0
    suffix = body[search_start:]
    year_match = re.search(
        r'\*\*((?:19|20)\d{2})\*\*|(?<!\d)((?:19|20)\d{2})(?!\d)',
        suffix,
    )
    year = ''
    tail = ''
    if year_match:
        year = year_match.group(1) or year_match.group(2)
        tail = suffix[year_match.end():]

    volume, issue, pages = _parse_locator_tail(tail)
    title_words = set(re.findall(r'[a-z0-9]{4,}', _normalize_text(title)))
    first_author = authors[0] if authors else _fallback_first_author(body)

    return {
        'first_author': first_author,
        'authors': authors,
        'authors_truncated': bool(re.search(r'\bet\s+al\.?', prefix, re.I)),
        'year': year,
        'title': title,
        'title_normalized': _normalize_text(title),
        'title_words': title_words,
        'journal': journal,
        'journal_normalized': _normalize_text(journal),
        'volume': volume,
        'issue': issue,
        'pages': pages,
        'doi': doi,
        'raw': raw,
    }


def _split_authors_and_title(prefix: str) -> tuple[list[str], str]:
    chunks = [chunk.strip() for chunk in prefix.split(',') if chunk.strip()]
    authors = []
    title_start = len(chunks)
    for index, chunk in enumerate(chunks):
        match = _INITIALS_AND_SURNAME.match(chunk)
        if not match:
            title_start = index
            break
        authors.append(match.group(1).strip(' {}'))
    title = ', '.join(chunks[title_start:]).strip(' .')
    return authors, title


def _fallback_first_author(body: str) -> str:
    match = _INITIALS_AND_SURNAME.match(body.split(',', 1)[0].strip())
    return _normalize_text(match.group(1)) if match else ''


def _parse_locator_tail(tail: str) -> tuple[str, str, str]:
    parts = [part.strip(' *.;') for part in tail.strip(' ,.;').split(',')]
    parts = [part for part in parts if part]
    if not parts:
        return '', '', ''

    volume = parts[0]
    issue = ''
    volume_issue = re.match(r'^([^()]+?)\s*\(([^)]+)\)$', volume)
    if volume_issue:
        volume = volume_issue.group(1).strip()
        issue = volume_issue.group(2).strip()

    pages = parts[-1] if len(parts) > 1 else ''
    if len(parts) > 2 and not issue:
        issue = parts[-2]
    return volume.strip(' *'), issue.strip(' *'), pages.strip(' *')


def _index_bib(bib_content: str) -> list:
    """Build the search index through the repository's robust BibTeX parser."""
    entries = BibTeXParser().parse(bib_content)
    index = []
    for key, bib_entry in entries.items():
        fields = bib_entry.fields
        author_surnames = _bib_author_surnames(fields.get('author', ''))
        year = fields.get('year', '')
        if not year:
            date_match = re.search(r'(?<!\d)((?:19|20)\d{2})(?!\d)',
                                   fields.get('date', ''))
            year = date_match.group(1) if date_match else ''
        title = fields.get('title', '')
        index.append({
            'key': key,
            'entry_type': bib_entry.entry_type,
            'first_author': author_surnames[0] if author_surnames else '',
            'authors': author_surnames,
            'year': year,
            'title': title,
            'title_normalized': _normalize_text(title),
            'title_words': set(re.findall(
                r'[a-z0-9]{4,}', _normalize_text(title)
            )),
            'journal': fields.get('journal', ''),
            'journal_normalized': _normalize_text(fields.get('journal', '')),
            'volume': fields.get('volume', ''),
            'issue': fields.get('number', '') or fields.get('issue', ''),
            'pages': fields.get('pages', ''),
            'doi': _normalize_doi(fields.get('doi', '')),
        })
    return index


def _bib_author_surnames(author_field: str) -> list[str]:
    surnames = []
    for author in re.split(r'\s+and\s+', author_field):
        author = author.strip()
        if not author:
            continue
        if ',' in author:
            surname = author.split(',', 1)[0]
        else:
            surname = author.split()[-1]
        surnames.append(_normalize_text(surname.strip(' {}')))
    return surnames


def _match_entry(entry: dict, bib_index: list) -> dict:
    """Return a match only when one candidate has uniquely strong evidence."""
    ranked = [_evaluate_candidate(entry, candidate) for candidate in bib_index]
    ranked.sort(key=lambda item: (-item['score'], item['citekey']))
    qualified = [item for item in ranked if item['qualified']]
    visible = [item for item in ranked if item['score'] > 0][:5]

    if len(qualified) == 1:
        winner = qualified[0]
        status = 'matched'
        matched_key = winner['citekey']
        reason = winner['qualification_reason']
    elif len(qualified) > 1:
        winner = qualified[0]
        status = 'ambiguous'
        matched_key = None
        reason = 'multiple_high_confidence_candidates'
    else:
        winner = visible[0] if visible else None
        status = 'unmapped'
        matched_key = None
        reason = 'no_unique_high_confidence_candidate'

    return {
        'status': status,
        'matched_key': matched_key,
        'score': winner['score'] if winner else 0.0,
        'reason': reason,
        'candidates': [
            (item['citekey'], item['score']) for item in visible
        ],
        'candidate_details': visible,
    }


def _evaluate_candidate(reference: dict, candidate: dict) -> dict:
    evidence = []
    conflicts = []

    def compare(field: str, label: str, normalizer=_normalize_text):
        reference_value = reference.get(field, '')
        candidate_value = candidate.get(field, '')
        if not reference_value or not candidate_value:
            return False
        if normalizer(reference_value) == normalizer(candidate_value):
            evidence.append(label)
            return True
        conflicts.append(f'{label}_conflict')
        return False

    doi_exact = compare('doi', 'doi_exact', _normalize_doi)
    first_author_exact = compare('first_author', 'first_author_exact')
    year_exact = compare('year', 'year_exact')
    volume_exact = compare('volume', 'volume_exact')
    issue_exact = compare('issue', 'issue_exact')

    journal_exact = False
    if reference.get('journal_normalized') and candidate.get('journal_normalized'):
        if reference['journal_normalized'] == candidate['journal_normalized']:
            journal_exact = True
            evidence.append('journal_exact')

    pages_exact = False
    if reference.get('pages') and candidate.get('pages'):
        if _locator_matches(reference['pages'], candidate['pages']):
            pages_exact = True
            evidence.append('pages_or_article_exact')
        else:
            conflicts.append('pages_or_article_conflict')

    authors_exact = False
    if (reference.get('authors') and candidate.get('authors') and
            not reference.get('authors_truncated')):
        if reference['authors'] == candidate['authors']:
            authors_exact = True
            evidence.append('author_sequence_exact')

    title_exact = False
    title_near = False
    title_similarity = 0.0
    reference_title = reference.get('title_normalized', '')
    candidate_title = candidate.get('title_normalized', '')
    if reference_title and candidate_title:
        title_exact = reference_title == candidate_title
        title_similarity = SequenceMatcher(
            None, reference_title, candidate_title
        ).ratio()
        if title_exact:
            evidence.append('title_normalized_exact')
        elif title_similarity >= 0.94:
            title_near = True
            evidence.append('title_normalized_near_exact')

    score = 0.0
    score += 1.0 if doi_exact else 0.0
    score += 0.8 if title_exact else (0.55 if title_near else 0.0)
    score += 0.45 if authors_exact else (0.25 if first_author_exact else 0.0)
    score += 0.2 if year_exact else 0.0
    score += 0.15 if journal_exact else 0.0
    score += 0.1 if volume_exact else 0.0
    score += 0.05 if issue_exact else 0.0
    score += 0.2 if pages_exact else 0.0

    strong_conflict = any(conflict in conflicts for conflict in (
        'doi_exact_conflict', 'first_author_exact_conflict',
        'year_exact_conflict', 'volume_exact_conflict',
        'pages_or_article_conflict',
    ))
    composite_exact = (
        first_author_exact and year_exact and
        (
            (journal_exact and pages_exact) or
            (journal_exact and volume_exact and authors_exact) or
            (authors_exact and (journal_exact or pages_exact))
        )
    )

    qualification_reason = ''
    qualified = False
    if doi_exact and not strong_conflict:
        qualified = True
        qualification_reason = 'unique_doi_exact'
    elif title_exact and first_author_exact and not strong_conflict:
        qualified = True
        qualification_reason = 'unique_title_author_exact'
    elif (title_near and first_author_exact and year_exact and
          not strong_conflict):
        qualified = True
        qualification_reason = 'unique_near_title_with_author_year'
    elif composite_exact and not strong_conflict:
        qualified = True
        qualification_reason = 'unique_composite_bibliographic_identity'

    return {
        'citekey': candidate['key'],
        'score': round(score, 3),
        'qualified': qualified,
        'qualification_reason': qualification_reason,
        'evidence': evidence,
        'conflicts': conflicts,
        'metadata': {
            field: candidate.get(field, '') for field in (
                'first_author', 'authors', 'year', 'title', 'journal',
                'volume', 'issue', 'pages', 'doi'
            )
        },
        'title_similarity': round(title_similarity, 3),
    }


def _references_equivalent(first: dict, second: dict) -> bool:
    if first.get('doi') and second.get('doi'):
        return first['doi'] == second['doi']
    if (first.get('title_normalized') and
            first['title_normalized'] == second.get('title_normalized') and
            first.get('year') == second.get('year')):
        return True
    return bool(
        first.get('authors') and first['authors'] == second.get('authors') and
        first.get('year') and first['year'] == second.get('year') and
        first.get('journal_normalized') == second.get('journal_normalized') and
        first.get('volume') == second.get('volume') and
        first.get('pages') and
        _locator_matches(first['pages'], second.get('pages', ''))
    )


def _locator_matches(first: str, second: str) -> bool:
    first_normalized = _normalize_locator(first)
    second_normalized = _normalize_locator(second)
    if not first_normalized or not second_normalized:
        return False
    if first_normalized == second_normalized:
        return True
    first_start = re.split(r'-+', first_normalized)[0]
    second_start = re.split(r'-+', second_normalized)[0]
    return first_start == second_start


def _normalize_locator(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value))
    value = value.replace('–', '-').replace('—', '-').replace('--', '-')
    return re.sub(r'[^a-zA-Z0-9-]', '', value).lower()


def _normalize_doi(value: str) -> str:
    value = str(value or '').strip().lower()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value)
    return value.rstrip('.,;')


def _normalize_text(value: str) -> str:
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r'[{}\\]', '', value).lower()
    return re.sub(r'[^a-z0-9]+', '', value)


def _public_reference_metadata(entry: dict) -> dict:
    return {
        field: entry.get(field, '') for field in (
            'authors', 'year', 'title', 'journal', 'volume', 'issue',
            'pages', 'doi'
        )
    }
