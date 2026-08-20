"""Production-entry routing tests for CiteMatch stabilization."""
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = PROJECT_ROOT / "workflows"
WORKFLOW_SCRIPT = WORKFLOW_DIR / "manuscript_workflow.py"
sys.path.insert(0, str(WORKFLOW_DIR))

from manuscript_workflow import ManuscriptWorkflow, PRODUCTION_ENTRY_ID


def _write_mode_c_fixture(tmp_path: Path) -> tuple[Path, Path]:
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        "# Results\n\n"
        "A supported claim ^\\[1\\]^.\n\n"
        "**References**\n\n"
        "\\[1\\] A. Author, A supported claim. *Journal* **2024**, *1*, 1.\n",
        encoding="utf-8",
    )
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@article{Author2024,\n"
        "  author = {Author, A.},\n"
        "  title = {A supported claim},\n"
        "  journal = {Journal},\n"
        "  year = {2024},\n"
        "}\n\n"
        "@article{Pending2025,\n"
        "  author = {Pending, P.},\n"
        "  title = {A pending paper},\n"
        "  journal = {Journal},\n"
        "  year = {2025},\n"
        "}\n",
        encoding="utf-8",
    )
    return manuscript, bib


def test_direct_workflow_mode_c_uses_canonical_entry(tmp_path):
    manuscript, bib = _write_mode_c_fixture(tmp_path)
    output = tmp_path / "direct-output"

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(mode="C", dry_run=False)

    assert result["status"] == "completed"
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["data"]["mapping"] == {
        "total": 1,
        "mapped": 1,
        "unmapped": 0,
        "ambiguous": 0,
        "unsafe": 0,
        "mapping_pct": 100.0,
    }
    assert result["data"]["legacy_occurrences"] == 1
    assert result["data"]["migrated_occurrences"] == 1
    assert result["data"]["legacy_numeric_occurrences"] == 0
    assert result["data"]["total_migrated_occurrences"] == 1
    assert result["data"]["residual_superscript"] == 0
    assert result["data"]["residual_numeric"] == 0
    assert result["data"]["used_references"] == 1
    assert result["data"]["pending_references"] == 1
    migrated = Path(result["outputs"]["markdown"]).read_text(encoding="utf-8")
    assert "[@Author2024]" in migrated
    assert "**References**" not in migrated
    assert "\\[1\\] A. Author" not in migrated


def test_cli_routes_to_same_manuscript_workflow(tmp_path):
    manuscript, bib = _write_mode_c_fixture(tmp_path)
    output = tmp_path / "cli-output"

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(WORKFLOW_SCRIPT),
            str(manuscript),
            str(bib),
            "--mode",
            "C",
            "--write",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "completed"
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["data"]["migrated_occurrences"] == 1
    assert Path(result["outputs"]["markdown"]).parent == output


def test_installed_skill_routes_to_canonical_entry():
    skill_path = Path(os.environ.get(
        "CITEMATCH_SKILL_PATH",
        Path.home() / ".agents" / "skills" / "cite-match" / "SKILL.md",
    ))
    assert skill_path.exists(), f"Installed CiteMatch Skill not found: {skill_path}"
    skill = skill_path.read_text(encoding="utf-8")

    assert "workflows/manuscript_workflow.py" in skill
    assert "ManuscriptWorkflow" in skill
    assert "citematch.workflows.manuscript_workflow.ManuscriptWorkflow" in skill
    for retired_script in (
        "_mode_c_clean.py",
        "_phase1_if_gate.py",
        "_phase2_summary.py",
        "_phase3_match.py",
        "_phase5_inject.py",
        "_phase7_mapping.py",
    ):
        assert retired_script not in skill


def test_mode_c_mapping_failure_preserves_references_and_stops(tmp_path):
    manuscript, bib = _write_mode_c_fixture(tmp_path)
    bib.write_text(
        "@article{Other2025,\n"
        "  author = {Other, O.},\n"
        "  title = {An unrelated paper},\n"
        "  journal = {Other Journal},\n"
        "  year = {2025},\n"
        "}\n",
        encoding="utf-8",
    )
    output = tmp_path / "blocked-output"

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(mode="C", dry_run=False)

    assert result["status"] == "blocked"
    assert result["reason"] == "LEGACY_MAPPING_UNSAFE"
    assert result["details"]["references_preserved"] is True
    assert "**References**" in manuscript.read_text(encoding="utf-8")
    assert not (output / "migrated.md").exists()


def test_mode_c_ambiguous_metadata_fails_closed(tmp_path):
    manuscript, bib = _write_mode_c_fixture(tmp_path)
    bib.write_text(
        "@article{CandidateA,\n"
        "  author = {Author, A.},\n"
        "  title = {A supported claim},\n"
        "  journal = {Journal},\n"
        "  year = 2024,\n"
        "}\n\n"
        "@article{CandidateB,\n"
        "  author = {Author, A.},\n"
        "  title = {A supported claim},\n"
        "  journal = {Journal},\n"
        "  year = 2024,\n"
        "}\n",
        encoding="utf-8",
    )

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "ambiguous-output")
    ).run(mode="C", dry_run=False)

    assert result["status"] == "blocked"
    assert result["reason"] == "LEGACY_MAPPING_UNSAFE"
    assert result["details"]["mapping"]["ambiguous"] == 1
    ambiguity = next(
        issue for issue in result["details"]["issues"]
        if issue["type"] == "ambiguous"
    )
    assert ambiguity["number"] == 1
    assert {item["citekey"] for item in ambiguity["candidates"]} == {
        "CandidateA", "CandidateB"
    }
    assert result["details"]["references_preserved"] is True
    assert not (tmp_path / "ambiguous-output" / "migrated.md").exists()


def test_mode_c_verified_duplicate_references_allow_many_to_one(tmp_path):
    manuscript = tmp_path / "duplicate-references.md"
    manuscript.write_text(
        "# Results\n\n"
        "First claim ^\\[1\\]^. Second claim ^\\[2\\]^.\n\n"
        "**References**\n\n"
        "\\[1\\] A. Author, Shared study. *Journal* **2024**, *1*, 10.\n"
        "\\[2\\] A. Author, Shared study. *Journal* **2024**, *1*, 10.\n",
        encoding="utf-8",
    )
    bib = tmp_path / "duplicate-references.bib"
    bib.write_text(
        "@article{Shared2024,\n"
        "  author = {Author, A.},\n"
        "  title = {Shared study},\n"
        "  journal = {Journal},\n"
        "  year = 2024,\n"
        "  volume = {1},\n"
        "  pages = {10},\n"
        "}\n",
        encoding="utf-8",
    )

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "duplicate-output")
    ).run(mode="C", dry_run=True)

    assert result["status"] == "completed", result
    assert result["data"]["mapping"]["mapped"] == 2
    assert result["data"]["mapping"]["unsafe"] == 0
    assert result["data"]["used_references"] == 1
    assert result["data"]["pending_references"] == 0
    assert result["data"]["total_migrated_occurrences"] == 2
    assert result["data"]["residual_numeric"] == 0


def test_mode_a_returns_structured_confirmation_state(tmp_path):
    manuscript, bib = _write_mode_c_fixture(tmp_path)
    manuscript.write_text(
        "# Results\n\nA supported claim [@Author2024].\n",
        encoding="utf-8",
    )
    output = tmp_path / "mode-a-output"

    workflow = ManuscriptWorkflow(str(manuscript), str(bib), str(output))
    result = workflow.run(mode="A", dry_run=True)

    assert result["status"] == "waiting_confirmation"
    assert result["phase"] == 1
    assert result["gate"] == "IF_CONFIRM"
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["data"]["used_references"] == 1
    assert result["data"]["pending_references"] == 1

    confirmed = workflow.confirm("IF_CONFIRM")
    assert confirmed["status"] == "completed"
    assert confirmed["phase"] == 1
    assert confirmed["entry"] == PRODUCTION_ENTRY_ID
