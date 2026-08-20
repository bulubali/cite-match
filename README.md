# CiteMatch v2.5.x Release Candidate

CiteMatch is a fail-closed citation matching and document-compilation workflow for academic manuscripts. It ingests a manuscript and a Better BibTeX-compatible bibliography, preserves existing citations through Legacy Migration when necessary, matches eligible literature to safe locations, and compiles a cited DOCX with validation reports.

## Production architecture

```text
Installed CiteMatch Skill
        -> ManuscriptWorkflow
        -> existing Engine modules
        -> Pandoc / citeproc / CSL
        -> Final_Manuscript.docx + reports
```

The installed Skill is presentation and interaction only. It collects one Preflight configuration, invokes the single `ManuscriptWorkflow` production path, presents genuine safety interrupts, and returns outputs. Matching, IF policy, injection, table safety, CSL handling, and export remain in the existing workflow and engine modules.

## Supported modes

- **Mode A — full pipeline:** Preflight, Legacy Migration where needed, Phases 1–7, and final outputs.
- **Mode B — workflow-authorized standalone work:** only a phase that the workflow explicitly permits.
- **Mode C — legacy migration:** converts verified legacy numeric citations to Pandoc citekeys and safely removes the old bibliography only after mapping validation.

## Installation

### A. CiteMatch repository and Python dependencies

The RC was validated with **Python 3.13.7**. Python 3.9 or later is required by the source type syntax; use the validated interpreter where reproducibility matters.

Windows PowerShell:

```powershell
git clone https://github.com/bulubali/cite-match.git
Set-Location .\cite-match
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

macOS/Linux:

```bash
git clone https://github.com/bulubali/cite-match.git
cd cite-match
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

The dependency ranges in `requirements.txt` retain the dependency families used by the RC; they are not a lockfile.

### B. Pandoc and pandoc-crossref

Install a compatible Pandoc release and a compatible `pandoc-crossref` binary. The RC acceptance environment used Pandoc **3.6.4** and its paired `pandoc-crossref` executable. CiteMatch does not install either tool or modify `PATH`.

An explicit executable may be supplied when Pandoc is not on `PATH`:

```bash
python workflows/manuscript_workflow.py manuscript.docx references.bib \
  --mode A --preflight --write --output output/run \
  --pandoc-path <PANDOC_PATH>
```

When an explicit Pandoc path is supplied, the workflow validates it, uses it for DOCX-to-Markdown preparation and Phase 6 export, and first looks for `pandoc-crossref` beside that executable.

### Quick Install

The installer installs only the CiteMatch Skill; it does not install Codex, Claude Code, Python, Pandoc, or `pandoc-crossref`.

Windows / Codex (PowerShell):

```powershell
git clone https://github.com/bulubali/cite-match.git
Set-Location .\cite-match
.\installers\install.ps1 --target codex
```

Windows / Claude Code must be run from the Git Bash or WSL environment actually used by Claude Code:

```bash
./installers/install.sh --target claude
```

macOS/Linux:

```bash
git clone https://github.com/bulubali/cite-match.git
cd cite-match
chmod +x installers/install.sh
./installers/install.sh --target both
```

Use `--dry-run` to preview changes, `--force` to replace an existing installation after backup, and `--uninstall` to remove only an installer-owned CiteMatch Skill.

### C. Installed Skill

Copying `SKILL.md` alone is not a complete CiteMatch installation. Keep the repository checkout and Python dependencies available, and install Pandoc plus `pandoc-crossref` separately.

The distributable production Skill is [skill/SKILL.md](skill/SKILL.md). Run the following from the repository root:

```powershell
$skillRoot = Join-Path $env:USERPROFILE ".agents\skills\cite-match"
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -LiteralPath (Join-Path (Get-Location) "skill\SKILL.md") `
  -Destination (Join-Path $skillRoot "SKILL.md") -Force
```

Windows path: `%USERPROFILE%\.agents\skills\cite-match\SKILL.md`

macOS/Linux:

```bash
skill_root="$HOME/.agents/skills/cite-match"
mkdir -p "$skill_root"
cp skill/SKILL.md "$skill_root/SKILL.md"
```

macOS/Linux path: `~/.agents/skills/cite-match/SKILL.md`

The Skill is only the user-facing trigger and configuration adapter; it routes production work to this checkout's `ManuscriptWorkflow`. Installing only this file does not install the engine, Python dependencies, Pandoc, or `pandoc-crossref`.

## Basic usage and Preflight

Use the installed Skill for normal work. It first obtains profile-owned defaults and then presents one natural-language Preflight covering Body IF policy, Table IF policy, target journal, author display mode, and floating-reference policy.

After the user confirms, the workflow continues automatically through the normal pipeline. It does not replay ordinary per-phase confirmations.

```bash
python workflows/manuscript_workflow.py manuscript.docx references.bib \
  --mode A --preflight --write --output output/run \
  --profile advanced_materials_review \
  --body-if 6 --table-if 10 --journal "Advanced Materials" \
  --all-authors no --floating-policy ask \
  --pandoc-path <PANDOC_PATH>
```

## Safety interrupts

The workflow stops fail-closed for ambiguous legacy mapping, unsafe or duplicate citekeys, unavailable dependencies, ambiguous journal/CSL resolution, final-integrity failures, and other conditions it cannot safely decide.

### IF UNKNOWN

When an enabled IF policy cannot resolve a journal impact factor, the workflow returns `IF_UNKNOWN_REVIEW`. The literature is neither silently approved nor silently discarded. The user may allow it to continue for body semantic matching, exclude it, or inspect the detailed list. This is not a claim that an unknown IF meets a numeric threshold.

### Tables

Pipe tables use the table-safe injection route. Simple/grid tables are recognized as table content; if a safe cell-preserving write cannot be guaranteed, CiteMatch records `skip_unsafe_table` instead of falling back to body text injection. This protects cell boundaries, neighboring text, and citations from corruption.

### Floating references

Unmatched references are retained in `Floating_Reference_Report.md`. `keep` records them without editing prose; `ask` becomes a safety interrupt only when an expansion would be applied; `expand` uses the existing deterministic/template-based draft behavior. It is not a grounded LLM evidence-generation system and must be reviewed by the user before use.

## CSL behavior

For a resolved journal, CiteMatch obtains the CSL from the official Citation Style Language styles repository when it is not already in the local cache, then applies the existing safe CSL modifier for numeric bibliography presentation and author-display settings. The cache is local runtime state and is not distributed as project-owned MIT code. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Output artifacts

A completed run can produce `Final_Manuscript.docx`, `References_Summary.md`, `Floating_Reference_Report.md`, `injected_manuscript.md`, `CiteMatch_Mapping_Report.md`, `CiteMatch_Mapping_Report.csv`, workflow state, and validation evidence. All are runtime outputs and are intentionally ignored by Git.

## Testing

```bash
python -m pytest tests/ -v
```

The RC baseline is **538 passed, 3 skipped**. The historic Golden and real-case fixtures are private research fixtures and are intentionally not distributed in a public checkout. Their production evidence is summarized in [docs/Production_Changelog.md](docs/Production_Changelog.md); a clean public checkout therefore cannot run those private-fixture validations.

## Known limitations

- ISSUE-009 is deferred: CiteMatch does not automatically query external IF providers. IF provenance/provider integration requires a separately approved data and licensing design.
- Unknown IF requires an explicit user decision whenever the relevant IF policy is enabled.
- Unsafe simple/grid table citations may be safe-skipped rather than injected.
- Floating expansion is deterministic/template-based, not grounded LLM generation.
- Review citation protection has known coverage limits for some non-quantitative experimental claims; it is not expanded in this RC.
- Private production manuscripts, bibliographies, acceptance artifacts, and Golden fixtures are not part of the distributed release.

## Privacy and research data

Do not commit manuscripts, PDFs, Zotero exports, workflow states, generated reports, or production artifacts. This repository's `.gitignore` deliberately excludes these paths. Use synthetic, licensed fixtures before adding any document-based public regression data.

## Release status

**CiteMatch v2.5.x Release Candidate**

- Real User Production Acceptance: PASS
- Full Suite baseline: 538 passed, 3 skipped
- Golden: PASS in the private fixture environment
- Regression Testing: ISSUE-004 — Legacy Citation Migration
- Deferred: ISSUE-009 — IF Resolution Provenance and Provider Integration

## License

The CiteMatch source code is available under the [MIT License](LICENSE.txt). Third-party assets retain their own licenses.
