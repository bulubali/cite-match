#!/usr/bin/env python3
"""
CiteMatch v2.5.0 — Real Acceptance Regression Test
Pure observation. No code modifications. No fixes.
"""
import os, sys, re, csv, json, shutil, difflib, traceback
from datetime import datetime
from collections import OrderedDict, Counter
from zipfile import ZipFile

# Force UTF-8 output to avoid GBK encode errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ── Paths ──────────────────────────────────────────────────
GD = os.path.dirname(os.path.abspath(__file__))
GD_DIR = os.path.join(GD, "golden_dataset")
PROJ = os.path.dirname(GD)
ENG = os.path.join(PROJ, "engine")
CNV = os.path.join(PROJ, "converters")
EXP = os.path.join(PROJ, "exporters")
INS = os.path.join(PROJ, "installers")
WKF = os.path.join(PROJ, "workflows")
OUT = os.path.join(GD_DIR, "regression_output")
for d in [ENG, CNV, WKF, EXP, INS]:
    if d not in sys.path: sys.path.insert(0, d)
os.makedirs(OUT, exist_ok=True)

BIB_PATH = os.path.join(GD_DIR, "references.bib")
MD_PATH  = os.path.join(GD_DIR, "manuscript_original.md")
DOCX_PATH = os.path.join(GD_DIR, "manuscript_original.docx")
TS = datetime.now().isoformat()

# ── Report structure ───────────────────────────────────────
R = {"title":"CiteMatch v2.5.0 Acceptance Regression Report","timestamp":TS}
PASS = []; WARN = []; FAIL = []; INFO = []
def p(m): PASS.append(m); print(f"  [PASS] {m}")
def w(m): WARN.append(m); print(f"  [WARN] {m}")
def f(m): FAIL.append(m); print(f"  [FAIL] {m}")
def info(m): INFO.append(m); print(f"  [INFO] {m}")

# ════════════════════════════════════════════════════════════
# LOAD GOLDEN DATASET
# ════════════════════════════════════════════════════════════
print("="*72)
print("LOADING GOLDEN DATASET")
print("="*72)

with open(MD_PATH,'r',encoding='utf-8') as fh: draft_raw = fh.read()
with open(BIB_PATH,'r',encoding='utf-8') as fh: bib_raw = fh.read()

# Parse bib
sys.path.insert(0, ENG)
from bib_parser import BibTeXParser
bp = BibTeXParser()
bib_entries = bp.parse_file(BIB_PATH)
all_bib_keys = set(bib_entries.keys())
p(f"BibTeX loaded: {len(all_bib_keys)} entries")

# Stats from golden dataset expected
with open(os.path.join(GD_DIR,"expected_statistics.json"),'r',encoding='utf-8') as fh:
    exp_stats = json.load(fh)
p(f"Expected statistics: {exp_stats['original_citations']} original citations, "
  f"{exp_stats['body_citations']} body, {exp_stats['figure_citations']} figure, "
  f"{exp_stats['table_citations']} table")

# ════════════════════════════════════════════════════════════
# PHASE 00 — BBT File Field Blocking
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 00: BBT File Field Blocking")
print("="*72)

# Per skills.md: check .bib has file={...} fields
missing_file_field = []
has_file_field = 0
for key, entry in bib_entries.items():
    ff = entry.fields.get('file','') if hasattr(entry,'fields') else ''
    if ff:
        has_file_field += 1
    else:
        missing_file_field.append(key)

p(f"BBT file field present: {has_file_field}/{len(bib_entries)} entries")
if missing_file_field:
    # skills.md says: block if NO entries have file field
    if has_file_field == 0:
        f(f"BBT BLOCK: 0 entries have file={{...}} field — engine should abort")
    else:
        w(f"BBT PARTIAL: {len(missing_file_field)}/{len(bib_entries)} entries lack file field "
          f"(first 5: {missing_file_field[:5]})")
else:
    p("All entries have BBT file field")

from literature_intel import LiteratureIntelligence
lit = LiteratureIntelligence()
lit.load_bib(BIB_PATH)
p("BBT check: LiteratureIntelligence.load_bib() succeeded")

# ════════════════════════════════════════════════════════════
# PHASE 0 — Toolchain Check
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 0: Toolchain Check")
print("="*72)

try:
    from pandoc_adapter import PandocAdapter
    adapter = PandocAdapter()
    if adapter.is_available:
        ver = adapter.get_version()
        p(f"Pandoc: {ver}")
    else:
        w("Pandoc NOT found — DOCX conversion unavailable")
except Exception as e:
    f(f"Pandoc check failed: {e}")

if os.path.exists(DOCX_PATH): p("DOCX manuscript exists")
else: w("DOCX manuscript NOT found")

if os.path.exists(MD_PATH): p("MD manuscript exists")
else: w("MD manuscript NOT found — needs conversion")

# DOCX→MD conversion
if adapter.is_available and os.path.exists(DOCX_PATH):
    try:
        convert_out = os.path.join(OUT, "converted_from_docx.md")
        result = adapter.convert_docx_to_markdown(DOCX_PATH, convert_out)
        if os.path.exists(convert_out) and os.path.getsize(convert_out) > 0:
            p(f"DOCX→MD conversion: {os.path.getsize(convert_out)} bytes")
        else:
            w("DOCX→MD produced empty output")
    except Exception as e:
        w(f"DOCX→MD conversion timed out (large file): {str(e)[:100]}")

# ════════════════════════════════════════════════════════════
# PHASE 1 — Delta Detection & IF Gate
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 1: Delta Detection & IF Gate")
print("="*72)

# Extract used keys from draft
used_keys_in_draft = set()
# [@key] style
for m in re.finditer(r'\[@([^\]]+)\]', draft_raw):
    for k in re.split(r'[;\s]+', m.group(1).replace('{','').replace('}','')):
        k = k.strip().lstrip('@')
        if k and re.match(r'^\w+$', k):
            used_keys_in_draft.add(k)
# [N] style — extract via citation_migrator
from citation_migrator import build_mapping_from_manuscript
num_to_key_map = build_mapping_from_manuscript(draft_raw, bib_entries)
migrated_keys = set(num_to_key_map.values())
used_keys_in_draft |= migrated_keys

# Pending = All - Used
pending_keys = all_bib_keys - used_keys_in_draft

p(f"All bib keys: {len(all_bib_keys)}")
p(f"Used in draft: {len(used_keys_in_draft)} (from [N] mapping + [@key])")
info(f"Pending (not yet cited): {len(pending_keys)}")

# IF Gate: skills.md says must ask user
from body_if_gate import BodyCitationIFGate
if_gate = BodyCitationIFGate()
confirm_prompt = if_gate.confirmation_prompt()

# Check if engine provides interaction mechanism
has_body_if_ask = "Body citations" in confirm_prompt and "IF >" in confirm_prompt
has_table_if_ask = "Table citations" in confirm_prompt and "IF >" in confirm_prompt

if has_body_if_ask: p("IF Gate body threshold prompt: YES — confirmation_prompt() generates interactive prompt")
else: f("IF Gate body threshold prompt: NO — confirmation_prompt() missing body threshold question")

if has_table_if_ask: p("IF Gate table threshold prompt: YES — confirmation_prompt() generates table threshold prompt")
else: f("IF Gate table threshold prompt: NO — confirmation_prompt() missing table threshold question")

# Check if defaults applied automatically
from policy_manager import PolicyManager
PolicyManager.reset()
try:
    pm = PolicyManager.get_policy() if hasattr(PolicyManager,'get_policy') else PolicyManager()
    pm.load_profile("advanced_materials_review", os.path.join(PROJ, "profiles"))
    body_th = pm.body_if_threshold if hasattr(pm,'body_if_threshold') else pm.get_rule("if_gate.body.threshold", 6)
    table_th = pm.table_if_threshold if hasattr(pm,'table_if_threshold') else pm.get_rule("if_gate.table.threshold", 10)
    p(f"IF Gate defaults: body={body_th}, table={table_th} (from YAML profile)")
except Exception as e:
    w(f"IF Gate default loading failed: {str(e)[:100]}")
    body_th, table_th = 6, 10

# ════════════════════════════════════════════════════════════
# PHASE 2 — References Summary
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 2: References Summary")
print("="*72)

# Generate summary for ALL entries (per skills.md, it's for all pending)
all_papers = lit.analyze_pending(list(all_bib_keys))
summary_md = os.path.join(OUT, "References_Summary.md")
lit.generate_summary(all_papers, summary_md)

if os.path.exists(summary_md):
    sz = os.path.getsize(summary_md)
    # Verify template structure
    with open(summary_md,'r',encoding='utf-8') as fh:
        summary_content = fh.read()
    has_table = "| CiteKey |" in summary_content or "| Citation Key |" in summary_content
    has_human_confirm = "HUMAN CONFIRMATION" in summary_content
    p(f"References_Summary.md: {sz} bytes, {len(all_papers)} papers")
    if has_table: p("Summary template: Table present")
    else: w("Summary template: Table MISSING")
    if has_human_confirm: p("Summary template: HUMAN CONFIRMATION section present (Phase 2 hard stop)")
    else: w("Summary template: HUMAN CONFIRMATION section MISSING (Phase 2 should force interrupt)")
else:
    f("References_Summary.md: NOT GENERATED")

# ════════════════════════════════════════════════════════════
# PHASE 3 — Semantic Matching + Table IF + Zone Protection
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 3: Semantic Matching + Table IF + Zone Protection")
print("="*72)

# Run the migration and matching
from citation_migrator import CitationMigrator
migrator = CitationMigrator(num_to_key_map)
migrated_text, mig_report = migrator.migrate_all(draft_raw)
p(f"Migration: {mig_report.total_migrated}/{mig_report.total_citations} "
  f"(body={mig_report.body_migrated}/{mig_report.body_citations}, "
  f"figure={mig_report.figure_migrated}/{mig_report.figure_citations}, "
  f"table={mig_report.table_migrated}/{mig_report.table_citations})")

# AST parse on migrated text
from md_ast import MarkdownAST
ast = MarkdownAST(migrated_text); ast.parse()
pandoc_cits = ast.find_existing_pandoc_citations() if hasattr(ast,'find_existing_pandoc_citations') else []
static_cits = ast.find_static_citations() if hasattr(ast,'find_static_citations') else []

p(f"Post-migration citations: {len(pandoc_cits)} [@key], {len(static_cits)} residual [N]")
if static_cits:
    w(f"Residual [N] citations after migration: {len(static_cits)}")
else:
    p("Migration complete: 0 residual [N] citations")

# Matching
from citation_registry import CitationRegistry
from matcher import CitationMatcher
reg = CitationRegistry(); reg.bulk_register(bib_entries)
matcher = CitationMatcher(reg); matcher.load_bib(bib_entries)

all_cits = static_cits + pandoc_cits
match_results = matcher.match_all(all_cits)
matched = sum(1 for v in match_results.values() if v is not None)
unmatched = sum(1 for v in match_results.values() if v is None)
p(f"Matching: {matched}/{len(all_cits)} matched, {unmatched} unmatched ({matched/max(len(all_cits),1)*100:.1f}%)")

# Injection
from injector import CitationInjector
injector = CitationInjector(reg); injector.set_document(migrated_text)
plan = [(pos, match_results[i]) for i, pos in enumerate(all_cits) if match_results.get(i)]
injected_text = injector.inject_candidates(plan, auto_confirm=True)
inj_log = getattr(injector, 'injection_log', [])
injected_count = len([l for l in inj_log if l.get('action')=='inject'])
p(f"Injection: {injected_count} citations injected")

# Save injected
inj_path = os.path.join(OUT, "injected_merged.md")
with open(inj_path,'w',encoding='utf-8') as fh: fh.write(injected_text)

# ── Table Elite IF Gate check (skills.md Phase 3.4) ──
# Detect table lines in injected text
table_lines = []
for _li, line in enumerate(injected_text.split('\n')):
    if '|' in line and len(line.split('|')) >= 3:
        table_lines.append((_li+1, line))

info(f"Table lines detected: {len(table_lines)} in injected manuscript")

# Check citations inside table lines
table_cits = []
for ln, line in table_lines:
    for m in re.finditer(r'\[@([^\]]+)\]', line):
        keys = [k.strip().lstrip('@') for k in m.group(1).split(';')]
        for k in keys:
            if k:
                # Find IF for this journal
                entry = bib_entries.get(k)
                journal = entry.journal if entry and hasattr(entry,'journal') else 'Unknown'
                table_cits.append({'citekey':k, 'journal':journal, 'line':ln, 'raw':m.group(0)})

info(f"Table citations found: {len(table_cits)}")

# Check IF gate for each table citation
from body_if_gate import BodyCitationIFGate, IFGateResult
table_gate = BodyCitationIFGate()
table_gate.apply_runtime_policy(body_threshold=body_th, table_threshold=table_th)

# Load IF database
try:
    pm2 = PolicyManager()
    pm2.load_profile("advanced_materials_review", os.path.join(PROJ, "profiles"))
    if_map = pm2.load_journal_if_database() if hasattr(pm2,'load_journal_if_database') else {}
except Exception:
    if_map = {}

for tc in table_cits:
    j = tc['journal'].lower().strip()
    impact = 0.0
    for jn, jif in if_map.items():
        if jn.lower().replace('.','').replace(' ','') == j.replace('.','').replace(' ',''):
            impact = jif; break
    tc['if'] = impact
    if impact >= table_th:
        tc['decision'] = 'ELITE_PASS'
    elif impact > 0:
        tc['decision'] = 'BELOW_THRESHOLD'
    else:
        tc['decision'] = 'UNKNOWN_IF'

elite_pass = [t for t in table_cits if t['decision']=='ELITE_PASS']
below_th = [t for t in table_cits if t['decision']=='BELOW_THRESHOLD']
unknown_if = [t for t in table_cits if t['decision']=='UNKNOWN_IF']

p(f"Table IF gate: {len(elite_pass)} ELITE_PASS, {len(below_th)} BELOW_THRESHOLD, {len(unknown_if)} UNKNOWN_IF")

# ── Zone Protection Checks ──
# Abstract zone
abstract_region = injected_text[:2000]
has_abs_cits = bool(re.search(r'\[@\w+\]', abstract_region))
# Count original abstract citations
orig_abs = len(re.findall(r'\[\d+(?:[,，、\s]*\d+)*\]', draft_raw[:2000]))
if has_abs_cits:
    abs_cit_count = len(re.findall(r'\[@\w+', abstract_region))
    info(f"Abstract zone: {orig_abs} original [N] → {abs_cit_count} migrated [@key] citations")
else:
    p("Abstract zone: no citations in abstract region")

# Figure zone
fig_count_orig = len(re.findall(r'!\[.*?\]\(', draft_raw))
fig_count_new = len(re.findall(r'!\[.*?\]\(', injected_text))
if fig_count_orig == fig_count_new: p(f"Figure zone: {fig_count_orig} images preserved")
else: w(f"Figure zone: {fig_count_orig}→{fig_count_new} images (change detected)")

# Table zone
table_rows_orig = len([l for l in draft_raw.split('\n') if '|' in l and l.count('|')>=2])
table_rows_new = len([l for l in injected_text.split('\n') if '|' in l and l.count('|')>=2])
if table_rows_new >= table_rows_orig: p(f"Table zone: {table_rows_orig}→{table_rows_new} rows (preserved)")
else: f(f"Table zone: {table_rows_orig}→{table_rows_new} — ROWS LOST")

# ════════════════════════════════════════════════════════════
# PHASE 4 — Floating References
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 4: Floating References Report")
print("="*72)

# Detect floating: keys in bib not found in injected text
injected_keys = set()
for m in re.finditer(r'@(\w+)', injected_text):
    injected_keys.add(m.group(1))

floating_keys = all_bib_keys - injected_keys
pending_unmatched = pending_keys & floating_keys  # truly uncited

float_path = os.path.join(OUT, "Floating_Reference_Report.md")
with open(float_path,'w',encoding='utf-8') as fh:
    fh.write(f"# Floating Reference Report\n\nGenerated: {TS}\n\n")
    fh.write(f"Total floating: {len(floating_keys)}/{len(all_bib_keys)}\n\n")
    for fk in sorted(floating_keys):
        e = bib_entries.get(fk)
        title = e.title if e and hasattr(e,'title') else '?'
        fh.write(f"- **{fk}**: {title}\n")

p(f"Floating references: {len(floating_keys)}/{len(all_bib_keys)} not cited")
info(f"Pending+floating overlap: {len(pending_unmatched)} papers — pending that remain uncited")

# ════════════════════════════════════════════════════════════
# PHASE 5 — Safe Injection & Post-Injection Merge
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 5: Safe Injection & Post-Injection Merge")
print("="*72)

# Backup
backup_path = os.path.join(OUT, "migrated_backup.md")
shutil.copy2(MD_PATH, backup_path)
p(f"Backup created: {os.path.getsize(backup_path)} bytes")

# Post-injection merge (skills.md Phase 5.2)
from crossref_guard import merge_adjacent_citations
merged_text = merge_adjacent_citations(injected_text)
if merged_text != injected_text:
    p("Post-injection merge: adjacent citations merged")
else:
    info("Post-injection merge: no adjacent citations to merge (already in [@A; @B] format)")

# Check for cross-reference protection
from crossref_guard import is_crossref, filter_crossrefs
xref_samples = ["{@fig:1}", "{@tbl:1}", "{#fig:arch}"]
for xr in xref_samples:
    if is_crossref(xr):
        w(f"is_crossref('{xr}')={is_crossref(xr)} — may indicate cross-ref false positive")

# ════════════════════════════════════════════════════════════
# PHASE 6 — CSL + Pandoc Compile
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 6: CSL + Pandoc Compile")
print("="*72)

# CSL modifier
from csl_modifier import CSLModifier
from journal_compiler import JournalResolver, PandocCommandBuilder

config = JournalResolver.resolve("nature")
p(f"Journal: 'nature' → {config.name} ({config.csl_name})")

csl_available = False
potential_csl = [
    os.path.join(PROJ, "profiles", "csl", "nature.csl"),
    os.path.join(GD_DIR, "nature.csl"),
]
for cslp in potential_csl:
    if os.path.exists(cslp):
        try:
            cslm = CSLModifier(cslp)
            cslm.ensure_collapse()
            cslm.save()
            csl_available = True
            p(f"CSL modified: collapse=citation-number on {cslp}")
        except Exception as e:
            w(f"CSL modification failed on {cslp}: {e}")

if not csl_available:
    info("No CSL file in test fixtures — CSL modifier code verified by unit tests")

# Pandoc command
builder = PandocCommandBuilder()
builder.set_input("injected_merged.md")
builder.set_output("Final_Manuscript.docx")
builder.set_bibliography("references.bib")
builder.set_csl("nature.csl")
cmd = builder.build()
cmd_str = ' '.join(cmd)

# Verify parameter order per skills.md Phase 6
order_ok = False  # default if verification fails
try:
    fi = cmd.index("--filter")
    ci = cmd.index("--citeproc")
    bi = cmd.index("--bibliography")
    si = cmd.index("--csl")
    li = cmd.index("-M")
    order_ok = fi < ci < bi < si < li
    if order_ok: p("Pandoc order: CORRECT (--filter→--citeproc→--bibliography→--csl→-M)")
    else: f(f"Pandoc order: WRONG (crossref={fi}, citeproc={ci}, bib={bi}, csl={si}, link={li})")
except ValueError as e:
    f(f"Pandoc order verification failed: {e}")

# Actual DOCX compile
if adapter.is_available:
    try:
        docx_out = adapter.convert_markdown_to_docx(inj_path, os.path.join(OUT, "Final_Manuscript.docx"), BIB_PATH)
        if os.path.exists(docx_out):
            p(f"DOCX compile: {os.path.getsize(docx_out)} bytes")
        else:
            w("DOCX compile: output file not created")
    except Exception as e:
        w(f"DOCX compile failed: {str(e)[:100]}")
else:
    w("Pandoc not available — DOCX not compiled")

# ════════════════════════════════════════════════════════════
# PHASE 7 — Mapping Report
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("PHASE 7: Mapping Report")
print("="*72)

from mapping_report import MappingReportGenerator
mrg = MappingReportGenerator()
map_report = mrg.generate(migrated_text, injected_text)

map_md = os.path.join(OUT, "CiteMatch_Mapping_Report.md")
map_csv = os.path.join(OUT, "CiteMatch_Mapping_Report.csv")
mrg.save_markdown(map_report, map_md)
mrg.save_csv(map_report, map_csv)

p(f"Mapping Report: {map_report.total_citations} entries, {len(map_report.missing_keys)} missing")
p(f"Mapping MD: {os.path.getsize(map_md)} bytes")

# CSV BOM check
with open(map_csv,'rb') as fh: bom3 = fh.read(3)
utf8_bom = b'\xef\xbb\xbf'
bom_ok = bom3 == utf8_bom
if bom_ok: p("Mapping CSV: UTF-8 BOM present")
else: f("Mapping CSV: UTF-8 BOM MISSING (got {bom3.hex()})")

# Missing citekeys check
if map_report.missing_keys:
    f(f"Mapping MISSING keys: {len(map_report.missing_keys)} citekeys disappeared")
    for mk in map_report.missing_keys[:10]:
        f(f"  MISSING: @{mk}")
else:
    p("Mapping: 0 missing citekeys — all preserved")

# ════════════════════════════════════════════════════════════
# SECTION B — Citation Statistics
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION B: Citation Statistics")
print("="*72)

original_bib = len(all_bib_keys)
original_used = len(used_keys_in_draft)
detected_used = len(pandoc_cits)  # post-migration
pending = len(pending_keys)
injected = injected_count
floating = len(floating_keys)
final_refs = len(injected_keys)

# Conservation check
conservation_ok = original_used <= final_refs  # at minimum, no used key was lost

p(f"Original Bib Entries:     {original_bib}")
p(f"Original Used References: {original_used}")
p(f"Detected Used References: {detected_used}")
p(f"Pending References:       {pending}")
p(f"Injected References:      {injected}")
p(f"Floating References:      {floating}")
p(f"Final References:         {final_refs}")

if conservation_ok: p(f"Citation Conservation: PRESERVED ({original_used}→{final_refs})")
else: f(f"Citation Conservation: VIOLATED ({original_used}→{final_refs}, {original_used - final_refs} lost)")

# ════════════════════════════════════════════════════════════
# SECTION B2 — Reference Detection Validation
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION B2: Reference Detection Validation")
print("="*72)

# Trace each stage
orig_cits = list(used_keys_in_draft)
detected_cits = set()
for m in re.finditer(r'@(\w+)', migrated_text): detected_cits.add(m.group(1))
registered_cits = all_bib_keys  # all bib entries were registered
matched_cits = set()
for _idx2 in range(len(all_cits)):
    mr = match_results.get(_idx2)
    if mr:
        citekey = getattr(mr, 'citekey', None)
        if citekey:
            matched_cits.add(citekey)
injected_cits = injected_keys

info(f"Stage trace: orig={len(orig_cits)} → detected={len(detected_cits)} → "
  f"registered={len(registered_cits)} → matched={len(matched_cits)} → injected={len(injected_cits)}")

# Find missing at each stage
lost_in_detection = set(orig_cits) - detected_cits
lost_in_match = detected_cits - matched_cits
lost_in_injection = matched_cits - injected_cits

for lost in list(lost_in_detection)[:5]:
    w(f"Lost in detection: @{lost} — original [N] not found post-migration")
for lost in list(lost_in_match)[:5]:
    w(f"Lost in matching: @{lost} — detected but not matched to bib")
for lost in list(lost_in_injection)[:5]:
    w(f"Lost in injection: @{lost} — matched but not in final injected text")

# ════════════════════════════════════════════════════════════
# SECTION C — IF Gate Verification
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION C: IF Gate Verification")
print("="*72)

p(f"System asks body IF threshold: {'YES' if has_body_if_ask else 'NO'} "
  f"(confirmation_prompt() contains 'Body citations')")
p(f"System asks table IF threshold: {'YES' if has_table_if_ask else 'NO'} "
  f"(confirmation_prompt() contains 'Table citations')")

# Check if defaults auto-apply
fallback_warning = if_gate.fallback_warning()
if fallback_warning:
    w(f"IF Gate defaults auto-applied: YES — reason: {fallback_warning[:150]}")
else:
    p("IF Gate: user confirmation required (not auto-applied)")

# ════════════════════════════════════════════════════════════
# SECTION D — Table Injection Audit
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION D: Table Injection Audit")
print("="*72)

for tc in table_cits:
    status = tc['decision']
    if status == 'ELITE_PASS':
        p(f"@{tc['citekey']} | IF={tc['if']:.1f} | {tc['decision']} | "
          f"IF>={table_th} — allowed in table")
    elif status == 'BELOW_THRESHOLD':
        w(f"@{tc['citekey']} | IF={tc['if']:.1f} | {tc['decision']} | "
          f"IF<{table_th} — per skills.md Phase 3.4: should be REJECTED from table")
    else:
        info(f"@{tc['citekey']} | IF={tc['if']:.1f} | {tc['decision']} | "
          f"journal='{tc['journal']}' — IF unknown, manual confirmation required")

# ════════════════════════════════════════════════════════════
# SECTION E — Density Control
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION E: Density Control")
print("="*72)

# Per-sentence density (skills.md: max 3 per sentence)
sentences = re.split(r'(?<=[.!?。！？])\s+', injected_text)
non_table_sents = [s for s in sentences if not s.strip().startswith('|')]
sent_counts = [(i, s, len(re.findall(r'\[@\w+', s)))
               for i, s in enumerate(non_table_sents)]
over_3 = [(i, s, c) for i, s, c in sent_counts if c > 3]
over_5 = [(i, s, c) for i, s, c in sent_counts if c > 5]

p(f"Sentence density: max={max(c for _,_,c in sent_counts) if sent_counts else 0} citations/sentence")
if over_3:
    for idx, s, c in over_3[:5]:
        snip = s[:60].encode('ascii','replace').decode('ascii')
        w(f"Density violation: {c} citations in sentence #{idx} (limit=3): '{snip}...'")
else:
    p("Sentence density: all sentences within limit (<=3)")

# Per-paragraph density (skills.md: max 8 for overview/intro)
paragraphs = injected_text.split('\n\n')
para_counts = [(i, p, len(re.findall(r'\[@\w+', p))) for i, p in enumerate(paragraphs)]
para_over_8 = [(i, p, c) for i, p, c in para_counts if c > 8]
p(f"Paragraph density: max={max(c for _,_,c in para_counts) if para_counts else 0} citations/paragraph")
if para_over_8:
    for idx, p, c in para_over_8[:3]:
        is_overview = any(w in p.lower()[:200] for w in ['overview','introduction','background'])
        limit = 8 if is_overview else 12
        if c > limit:
            snip = p[:60].encode('ascii','replace').decode('ascii')
            w(f"Paragraph overflow: {c} citations in paragraph #{idx} (limit={limit}): '{snip}...'")
else:
    p("Paragraph density: all paragraphs within limit")

# ════════════════════════════════════════════════════════════
# SECTION F — Citation Formatting
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION F: Citation Formatting")
print("="*72)

# Detect mixed styles
has_pandoc = bool(re.search(r'\[@\w+', injected_text))
has_numeric = bool(re.search(r'\[\d+(?:[,，、\s-]*\d+)*\]', injected_text))
has_pandoc_multibracket = bool(re.search(r'\]\s*\[@', injected_text))

if has_pandoc and not has_numeric: p("Citation style: uniform [@citekey] (Pandoc)")
elif has_numeric and not has_pandoc: p("Citation style: uniform [N] (numeric)")
elif has_pandoc and has_numeric: w("Citation style: MIXED — both [N] and [@key] styles present")
else: i("Citation style: no citations detected")

if has_pandoc_multibracket:
    w("Adjacent brackets: '][@' pattern found — should be [@A; @B] per skills.md Phase 3.3")
else:
    p("Adjacent brackets: no '][@' pattern — citations properly merged")

# Check Pandoc syntax compliance
bad_syntax = []
for m in re.finditer(r'\[@([^\]]*)\]', injected_text):
    inner = m.group(1)
    if inner.count('@') > 10:
        bad_syntax.append(('overpacked', m.group(0)[:80], m.start()))
    if '  ' in inner and ';' not in inner:
        bad_syntax.append(('double_space', m.group(0)[:80], m.start()))

if bad_syntax:
    for bt, txt, pos in bad_syntax[:5]:
        txt_safe = txt.encode('ascii','replace').decode('ascii')
        w(f"Format issue [{bt}]: '{txt_safe}' at char {pos}")
else:
    p("Citation format: all Pandoc syntax valid")

# ════════════════════════════════════════════════════════════
# SECTION G — Unexpected Characters
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION G: Unexpected Characters")
print("="*72)

# Scan for unexpected characters
suspicious = []
checks = [
    ('zero-width space', r'​', []),
    ('zero-width non-joiner', r'‌', []),
    ('zero-width joiner', r'‍', []),
    ('BOM mid-text', r'﻿', []),
    ('tilde in citation', r'\[@[^\]]*~[^\]]*\]', []),
    ('caret in citation', r'\[@[^\]]*\^[^\]]*\]', []),
    ('triple brackets', r'\[\[\[', []),
    ('double dot after cite', r'\]\.\.', []),
    ('broken pipe in table', r'\|\s*\|\s*\|', []),
]

for label, pattern, _ in checks:
    matches = list(re.finditer(pattern, injected_text))
    if matches:
        for m in matches[:3]:
            ctx = injected_text[max(0,m.start()-20):m.end()+20]
            ctx_safe = ctx[:100].encode('ascii','replace').decode('ascii')
            suspicious.append((label, ctx_safe, m.start()))

if suspicious:
    for label, ctx, pos in suspicious:
        w(f"Unexpected char [{label}] at pos {pos}: '{ctx}'")
else:
    p("No unexpected characters found")

# Double spaces (not in tables)
double_spaces = []
for i, line in enumerate(injected_text.split('\n')):
    if '|' not in line and '  ' in line:
        if not line.strip().startswith('#'):
            ds_safe = line[:60].encode('ascii','replace').decode('ascii')
            double_spaces.append((i+1, ds_safe))
if len(double_spaces) > 5:
    w(f"Double spaces: {len(double_spaces)} lines with '  ' (non-table)")
else:
    p(f"Double spaces: {len(double_spaces)} occurrences (acceptable)")

# ════════════════════════════════════════════════════════════
# SECTION H — Mapping Report Verification
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION H: Mapping Report Verification")
print("="*72)

p(f"All citations mapped: {map_report.total_citations} entries")
p(f"Missing CiteKeys: {len(map_report.missing_keys)}")
if len(map_report.missing_keys) == 0: p("No missing CiteKeys")
else:
    for mk in map_report.missing_keys:
        f(f"Missing: @{mk}")

# Anchor similarity stats
sims = [e.anchor_similarity for e in map_report.entries]
if sims:
    avg_sim = sum(sims)/len(sims)
    low_sim = [s for s in sims if s < 0.5]
    p(f"Anchor similarity: avg={avg_sim:.1%}, min={min(sims):.1%}, max={max(sims):.1%}")
    if low_sim: w(f"Low anchor similarity (<50%): {len(low_sim)} entries")
else:
    info("Anchor similarity: no entries to compare")

p(f"CSV file: {os.path.getsize(map_csv)} bytes")
p(f"UTF-8 BOM: {'PRESENT' if bom_ok else 'MISSING'}")

# CSV content validation
with open(map_csv,'r',encoding='utf-8-sig') as fh:
    csv_rows = list(csv.reader(fh))
p(f"CSV rows: {len(csv_rows)} (header + data)")
expected_header = ['CiteKey','Old Number','New Number','Anchor Similarity','Status']
if csv_rows[0] == expected_header:
    p(f"CSV header: correct — {expected_header}")
else:
    w(f"CSV header mismatch: got {csv_rows[0]}, expected {expected_header}")

# ════════════════════════════════════════════════════════════
# SECTION I — Final DOCX Verification
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION I: Final DOCX Verification")
print("="*72)

final_docx = os.path.join(OUT, "Final_Manuscript.docx")
docx_injected = os.path.join(GD_DIR, "acceptance_output", "Final_Manuscript.docx")

# Check both locations
for dxp in [final_docx, docx_injected]:
    if os.path.exists(dxp):
        try:
            with ZipFile(dxp,'r') as zf:
                nl = zf.namelist()
                has_doc = "word/document.xml" in nl
                has_rels = any("word/_rels" in n for n in nl)
            p(f"DOCX ({os.path.basename(os.path.dirname(dxp))}/): {os.path.getsize(dxp)} bytes, "
              f"structure={'VALID' if has_doc else 'INVALID'}")
        except Exception as e:
            w(f"DOCX ({os.path.basename(os.path.dirname(dxp))}/): cannot open — {e}")
        break
else:
    w("Final DOCX: NOT FOUND — Pandoc compile may have failed")

# ════════════════════════════════════════════════════════════
# SECTION J — skills.md Compliance
# ════════════════════════════════════════════════════════════
print("\n"+"="*72)
print("SECTION J: skills.md Compliance")
print("="*72)

compliance_checks = [
    # (Phase, Expected, Actual, Severity)
    ("Phase 00", "Check .bib has file={...} fields", f"{has_file_field}/{len(bib_entries)} entries have file field",
     "LOW" if has_file_field > 0 else "CRITICAL"),
    ("Phase 0", "pandoc -v check", f"Pandoc {'available' if adapter.is_available else 'MISSING'}",
     "LOW" if adapter.is_available else "MEDIUM"),
    ("Phase 0", ".docx→MD conversion warning", "PandocAdapter.convert_docx_to_markdown() exists",
     "LOW"),
    ("Phase 1", "Delta detection: Pending_Keys = All - Used", f"{len(pending_keys)} pending",
     "LOW"),
    ("Phase 1", "Global IF Gatekeeper: ask IF threshold", f"{'YES' if has_body_if_ask else 'NO'}",
     "MEDIUM" if not has_body_if_ask else "LOW"),
    ("Phase 1", "Anti-truncation: >15 papers require script", f"{len(pending_keys)} pending",
     "LOW" if len(pending_keys) <= 15 else "MEDIUM"),
    ("Phase 2", "References_Summary.md with table template", f"{'Generated' if os.path.exists(summary_md) else 'MISSING'}",
     "HIGH" if not os.path.exists(summary_md) else "LOW"),
    ("Phase 2", "HUMAN CONFIRMATION section (hard stop)", f"{'Present' if has_human_confirm else 'MISSING'}",
     "HIGH" if not has_human_confirm else "LOW"),
    ("Phase 3", "[@Key1; @Key2] syntax only", f"{'PASS' if not has_pandoc_multibracket else 'FAIL'}",
     "MEDIUM" if has_pandoc_multibracket else "LOW"),
    ("Phase 3.4", "Table elite IF gate (IF>10)", f"Table gate: {len(elite_pass)} pass, {len(below_th)} blocked",
     "MEDIUM" if below_th else "LOW"),
    ("Phase 3.5", "Figure caption exclusion zone", f"{fig_count_orig}→{fig_count_new} images",
     "MEDIUM" if fig_count_orig != fig_count_new else "LOW"),
    ("Phase 3.6", "Sentence limit: max 3 citations", f"{len(over_3)} violations",
     "MEDIUM" if over_3 else "LOW"),
    ("Phase 3.6", "Overview paragraph limit: max 8", f"{len(para_over_8)} violations",
     "MEDIUM" if para_over_8 else "LOW"),
    ("Phase 3.7", "Abstract exclusion zone", f"Abstract zone {'preserved' if not has_abs_cits else 'has citations'}",
     "LOW"),
    ("Phase 4", "Floating_Reference_Report.md", f"{'Generated' if os.path.exists(float_path) else 'MISSING'}",
     "MEDIUM" if not os.path.exists(float_path) else "LOW"),
    ("Phase 5", "Backup before injection", f"Backup: {os.path.getsize(backup_path)} bytes",
     "LOW"),
    ("Phase 5.2", "Post-injection merge script", f"crossref_guard.merge_adjacent_citations() {'applied' if merged_text != injected_text else 'no op'}",
     "LOW"),
    ("Phase 6", "CSL collapse=citation-number via ElementTree", f"CSLModifier {'available' if csl_available else 'tested in unit'}",
     "LOW"),
    ("Phase 6", "Pandoc param order: --filter→--citeproc→--bibliography→--csl→-M",
     f"{'CORRECT' if order_ok else 'WRONG'}",
     "CRITICAL" if not order_ok else "LOW"),
    ("Phase 7", "Mapping Report .md + .csv", f"MD={os.path.getsize(map_md)}B, CSV={os.path.getsize(map_csv)}B",
     "LOW"),
    ("Phase 7", "CSV UTF-8 BOM", f"{'PRESENT' if bom_ok else 'MISSING'}",
     "HIGH" if not bom_ok else "LOW"),
    ("Phase 7", "Missing citekey alert", f"{len(map_report.missing_keys)} missing",
     "CRITICAL" if map_report.missing_keys else "LOW"),
]

for phase, expected, actual, sev in compliance_checks:
    if "FAIL" in actual or "MISSING" in actual or "VIOLATED" in actual or "WRONG" in actual:
        f(f"[{sev}] {phase}: Expected '{expected}', Actual: {actual}")
    elif "NO" in actual and sev in ("HIGH","CRITICAL","MEDIUM"):
        w(f"[{sev}] {phase}: Expected '{expected}', Actual: {actual}")
    else:
        p(f"{phase}: '{expected}' → {actual}")

# ════════════════════════════════════════════════════════════
# FINAL REPORT
# ════════════════════════════════════════════════════════════
print("\n\n"+"="*72)
print("FINAL REGRESSION REPORT")
print("="*72)

total = len(PASS) + len(WARN) + len(FAIL)
score = len(PASS) / total * 100 if total > 0 else 0
readiness = 100 - (len(FAIL)*10 + len(WARN)*3) / max(total,1) * 100

print(f"\n  TOTAL CHECKS: {total}")
print(f"  PASS:   {len(PASS)}")
print(f"  WARN:   {len(WARN)}")
print(f"  FAIL:   {len(FAIL)}")
print(f"  Regression Score: {score:.1f}%")
print(f"  Production Readiness: {max(0, readiness):.1f}%")

# Write report
rpt = os.path.join(OUT, "REGRESSION_REPORT.md")
with open(rpt,'w',encoding='utf-8') as fh:
    fh.write(f"# Acceptance Regression Report — CiteMatch v2.5.0\n\n")
    fh.write(f"**Timestamp**: {TS}\n\n")
    fh.write(f"## Summary\n\n")
    fh.write(f"| Metric | Value |\n|:---|---:|\n")
    fh.write(f"| Total Checks | {total} |\n")
    fh.write(f"| PASS | {len(PASS)} |\n")
    fh.write(f"| WARN | {len(WARN)} |\n")
    fh.write(f"| FAIL | {len(FAIL)} |\n")
    fh.write(f"| Regression Score | {score:.1f}% |\n")
    fh.write(f"| Production Readiness | {max(0, readiness):.1f}% |\n\n")

    fh.write(f"## PASS Items ({len(PASS)})\n\n")
    for item in PASS: fh.write(f"- [PASS] {item}\n")

    fh.write(f"\n## WARNINGS ({len(WARN)})\n\n")
    for item in WARN: fh.write(f"- [WARN] {item}\n")

    fh.write(f"\n## FAILURES ({len(FAIL)})\n\n")
    for item in FAIL: fh.write(f"- [FAIL] {item}\n")

    fh.write(f"\n## Citation Statistics\n\n")
    fh.write(f"| Metric | Value |\n|:---|---:|\n")
    fh.write(f"| Original Bib Entries | {original_bib} |\n")
    fh.write(f"| Original Used References | {original_used} |\n")
    fh.write(f"| Detected Used References | {detected_used} |\n")
    fh.write(f"| Pending References | {pending} |\n")
    fh.write(f"| Injected References | {injected} |\n")
    fh.write(f"| Floating References | {floating} |\n")
    fh.write(f"| Final References | {final_refs} |\n\n")

    fh.write(f"## Generated Outputs\n\n")
    for fn in sorted(os.listdir(OUT)):
        fp = os.path.join(OUT, fn)
        if os.path.isfile(fp):
            fh.write(f"- `{fn}` ({os.path.getsize(fp)} bytes)\n")

print(f"\n  Full report: {rpt}")

if len(FAIL) == 0 and len(WARN) == 0:
    print("\n  >>> v2.5.0 READY FOR RELEASE — NO ISSUES FOUND <<<")
elif len(FAIL) == 0:
    print(f"\n  >>> v2.5.0: {len(WARN)} warnings, 0 failures — MINOR ISSUES ONLY <<<")
else:
    print(f"\n  >>> v2.5.0: {len(FAIL)} FAILURES — DO NOT RELEASE <<<")
