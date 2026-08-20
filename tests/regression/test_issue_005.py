"""ISSUE-005: production-entry interface continuation tests."""
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = PROJECT_ROOT / "workflows"
sys.path.insert(0, str(WORKFLOW_DIR))

from manuscript_workflow import ManuscriptWorkflow, PRODUCTION_ENTRY_ID

ENGINE_DIR = PROJECT_ROOT / "engine"
sys.path.insert(0, str(ENGINE_DIR))

from candidate_adapter import adapt_semantic_candidates
from citation_registry import CitationRegistry
from injector import CitationInjector
from literature_intel import PaperIntel
from semantic_mapper import CitationCandidate
from body_if_gate import BodyCitationIFGate, IFGateResult
from policy_manager import PolicyManager, get_policy
from environment_checker import EnvironmentChecker
from pandoc_adapter import PandocAdapter


def _write_fixture(tmp_path):
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        "# Introduction\n\n"
        "Flexible pressure sensors support continuous monitoring [@Old2024].\n",
        encoding="utf-8",
    )
    bib = tmp_path / "references.bib"
    bib.write_text(
        """@article{Old2024,
  author = {Old, A.},
  title = {Existing monitoring study},
  year = {2024},
  journal = {Journal A},
  file = {D:/papers/old.pdf}
}
@article{New2025,
  author = {New, B.},
  title = {Flexible pressure sensors support continuous monitoring},
  abstract = {Flexible pressure sensors support continuous monitoring.},
  year = {2025},
  journal = {Journal B},
  file = {D:/papers/new.pdf}
}
""",
        encoding="utf-8",
    )
    return manuscript, bib


def _write_floating_fixture(tmp_path):
    manuscript = tmp_path / "floating-manuscript.md"
    manuscript.write_text(
        "# Introduction\n\nExisting background statement.\n",
        encoding="utf-8",
    )
    bib = tmp_path / "floating-references.bib"
    bib.write_text(
        """@article{Review2025,
  author = {Review, R.},
  title = {Review of unrelated galaxies},
  abstract = {A perspective on unrelated galaxies.},
  year = {2025},
  journal = {Nature},
  file = {D:/papers/review.pdf}
}
""",
        encoding="utf-8",
    )
    return manuscript, bib


def _advance_to_phase5(manuscript, bib, output, dry_run=True):
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=dry_run
    )
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM", body_if="disable", dry_run=dry_run
    )
    return ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).confirm("SUMMARY_CONFIRM", dry_run=dry_run)


def _preflight_config(**overrides):
    config = {
        "body_if": "disable",
        "table_if": "disable",
        "journal": "nature",
        "all_authors": "no",
        "floating_policy": "keep",
    }
    config.update(overrides)
    return config


def _if_candidate(citekey, journal, target_sentence):
    return CitationCandidate(
        paper=PaperIntel(
            citekey=citekey, title="IF candidate", paper_type="research",
            journal=journal, technical_keywords=["sensor"],
            semantic_anchors=["sensor"],
        ),
        target_sentence=target_sentence, section="Introduction",
        similarity_score=0.9, reason="test",
    )


def test_phase1_structured_confirm_resumes_phase2_after_restart(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    started = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True
    )
    assert started["gate"] == "IF_CONFIRM"

    resumed = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM", body_if="disable", table_if=15, dry_run=True
    )
    assert resumed["status"] == "waiting_confirmation"
    assert resumed["phase"] == 2
    assert resumed["gate"] == "SUMMARY_CONFIRM"
    assert resumed["entry"] == PRODUCTION_ENTRY_ID

    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert state["context"]["if_runtime_policy"]["disabled"] is True
    assert state["context"]["table_if_policy"]["threshold"] == 15.0
    assert state["context"]["candidate_state"]["papers"][0]["citekey"] == "New2025"


def test_phase2_confirm_resumes_phase3_after_restart(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True
    )
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM", body_if="disable", dry_run=True
    )

    phase3 = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "SUMMARY_CONFIRM", dry_run=True
    )
    assert phase3["status"] == "waiting_confirmation"
    assert phase3["phase"] == 5
    assert phase3["gate"] == "INJECTION_CONFIRM"
    assert phase3["entry"] == PRODUCTION_ENTRY_ID
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert state["context"]["current_phase"] == 5
    assert state["context"]["candidate_state"]["candidates"]


def test_phase3_persisted_candidate_adapts_to_existing_injector(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True
    )
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM", body_if="disable", dry_run=True
    )
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "SUMMARY_CONFIRM", dry_run=True
    )

    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    candidate_data = state["context"]["candidate_state"]["candidates"][0]
    paper = PaperIntel(**candidate_data.pop("paper"))
    candidate = CitationCandidate(paper=paper, **candidate_data)
    manuscript_text = manuscript.read_text(encoding="utf-8")
    plan = adapt_semantic_candidates([candidate], manuscript_text)

    registry = CitationRegistry()
    registry.register(paper.citekey)
    injector = CitationInjector(registry)
    injector.set_document(manuscript_text)
    injected = injector.inject_candidates(plan, auto_confirm=False)
    assert f"[@{paper.citekey}]" in injected


def test_all_structured_answers_are_json_persisted(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True
    )
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM",
        body_if=8,
        table_if="disable",
        journal="nature",
        all_authors="yes",
        floating="no",
        dry_run=True,
    )
    context = json.loads(
        (output / "workflow_state.json").read_text(encoding="utf-8")
    )["context"]
    assert context["if_runtime_policy"] == {"threshold": 8.0, "disabled": False}
    assert context["table_if_policy"] == {"threshold": None, "disabled": True}
    assert context["journal"] == "nature"
    assert context["all_authors"] is True
    assert context["floating_confirmed"] is False


def test_invalid_structured_confirmation_fails_closed(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True
    )
    result = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_CONFIRM", body_if="high", dry_run=True
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "INVALID_CONFIRMATION_VALUE"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert state["approved"] is False
    assert state["waiting_confirmation"] is True


def test_cli_confirmation_uses_same_workflow_entry(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "run"
    script = PROJECT_ROOT / "workflows" / "manuscript_workflow.py"
    start = subprocess.run(
        [sys.executable, str(script), str(manuscript), str(bib),
         "--mode", "A", "--output", str(output)],
        capture_output=True, text=True, check=True,
    )
    assert json.loads(start.stdout)["entry"] == PRODUCTION_ENTRY_ID

    confirm = subprocess.run(
        [sys.executable, str(script), str(manuscript), str(bib),
         "--output", str(output), "--confirm", "IF_CONFIRM",
         "--body-if", "disable", "--table-if", "12"],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(confirm.stdout)
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["phase"] == 2


def test_installed_skill_routes_to_cli_and_workflow_entry():
    skill = PROJECT_ROOT / "skill" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    expected = "workflows/manuscript_workflow.py"
    assert expected in text
    assert "citematch.workflows.manuscript_workflow.ManuscriptWorkflow" in text
    assert "_phase" not in text
    for flag in (
        "--preflight", "--confirm", "--body-if", "--table-if", "--journal",
        "--all-authors", "--floating-policy", "--floating", "--csl",
        "--pandoc-path",
    ):
        assert flag in text
    assert "Preflight Configuration" in text


def test_phase3_routes_persisted_floaters_to_phase4_gate(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-run"
    result = _advance_to_phase5(manuscript, bib, output, dry_run=False)

    assert result["status"] == "waiting_confirmation"
    assert result["phase"] == 4
    assert result["gate"] == "FLOATING_CONFIRM"
    assert result["data"]["floating_references"] == 1
    report = Path(result["outputs"]["floating_report"])
    assert report.name == "Floating_Reference_Report.md"
    assert report.exists()
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    expansion = state["context"]["floating_state"]["expansions"][0]
    assert expansion["citekey"] == "Review2025"
    assert expansion["target_section"] == "Introduction"
    assert "【AI扩写区开始】" in expansion["approved_expansion"]


def test_phase4_confirmation_applies_persisted_text_then_waits_phase5(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-resume"
    _advance_to_phase5(manuscript, bib, output, dry_run=False)
    before = json.loads(
        (output / "workflow_state.json").read_text(encoding="utf-8")
    )["context"]["floating_state"]["expansions"][0]

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).confirm("FLOATING_CONFIRM", floating="yes", dry_run=False)

    assert result["status"] == "waiting_confirmation"
    assert result["phase"] == 5
    assert result["gate"] == "INJECTION_CONFIRM"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    applied = Path(state["context"]["working_markdown_path"])
    text = applied.read_text(encoding="utf-8")
    assert before["approved_expansion"] in text
    candidate = state["context"]["candidate_state"]["candidates"][0]
    assert candidate["target_sentence"] == before["target_sentence"]
    assert candidate["is_rejected"] is False


def test_phase5_injects_then_phase6_waits_for_export_values(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "phase6-wait"
    _advance_to_phase5(manuscript, bib, output, dry_run=False)

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).confirm("INJECTION_CONFIRM", dry_run=False)

    assert result["status"] == "waiting_confirmation"
    assert result["phase"] == 6
    assert result["gate"] == "EXPORT_CONFIRM"
    injected = output / "injected_manuscript.md"
    assert injected.exists()
    text = injected.read_text(encoding="utf-8")
    assert "[@Old2024; @New2025]" in text


def test_phase6_to_phase7_completed_with_final_outputs(
    tmp_path, monkeypatch
):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "full-run"
    pandoc = tmp_path / "pandoc.exe"
    pandoc.write_bytes(b"")
    observed = {}

    from docx_exporter import DocxExporter

    def fake_export(self, markdown_path, **kwargs):
        observed.update(kwargs)
        self._last_command = [
            kwargs["pandoc_path"], markdown_path, "-o", kwargs["output_path"],
            "--filter", "pandoc-crossref", "--citeproc",
            "--bibliography", kwargs["bibliography"],
            "--csl", "resolved.csl", "-M", "link-citations=true",
        ]
        Path(kwargs["output_path"]).write_bytes(b"new docx")
        return kwargs["output_path"]

    monkeypatch.setattr(DocxExporter, "export_manuscript", fake_export)
    _advance_to_phase5(manuscript, bib, output, dry_run=False)
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).confirm(
        "INJECTION_CONFIRM",
        journal="nature",
        all_authors="no",
        pandoc_path=str(pandoc),
        dry_run=False,
    )

    assert result["status"] == "completed"
    assert result["phase"] == 7
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert observed["journal"] == "nature"
    assert observed["all_authors"] is False
    assert observed["pandoc_path"] == str(pandoc.resolve())
    for key in (
        "references_summary", "floating_report", "injected_manuscript",
        "mapping_md", "mapping_csv", "final_docx",
    ):
        assert result["outputs"][key]
        assert Path(result["outputs"][key]).exists()
    assert Path(result["outputs"]["mapping_csv"]).read_text(
        encoding="utf-8"
    ).startswith("\ufeff")
    assert result["data"]["missing_keys"] == []


def test_full_mode_a_state_survives_cli_processes(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "cli-full-run"
    script = PROJECT_ROOT / "workflows" / "manuscript_workflow.py"

    commands = [
        ["--mode", "A"],
        ["--confirm", "IF_CONFIRM", "--body-if", "disable"],
        ["--confirm", "SUMMARY_CONFIRM"],
        ["--confirm", "INJECTION_CONFIRM"],
        ["--confirm", "EXPORT_CONFIRM", "--journal", "nature",
         "--all-authors", "no"],
    ]
    results = []
    for arguments in commands:
        completed = subprocess.run(
            [sys.executable, str(script), str(manuscript), str(bib),
             "--output", str(output), *arguments],
            capture_output=True, text=True, check=True,
        )
        results.append(json.loads(completed.stdout))

    assert [item["phase"] for item in results] == [1, 2, 5, 6, 7]
    assert results[-1]["status"] == "completed"
    assert all(item["entry"] == PRODUCTION_ENTRY_ID for item in results)
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert state["context"]["current_phase"] == 7
    assert state["context"]["mapping_state"]["missing_keys"] == []


def test_preflight_once_runs_summary_injection_and_full_mode_a_to_phase7(
    tmp_path, monkeypatch
):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "preflight-full"
    pandoc = tmp_path / "pandoc.exe"
    pandoc.write_bytes(b"")

    from docx_exporter import DocxExporter

    def fake_export(self, markdown_path, **kwargs):
        Path(kwargs["output_path"]).write_bytes(b"new docx")
        return kwargs["output_path"]

    monkeypatch.setattr(DocxExporter, "export_manuscript", fake_export)
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A",
        dry_run=False,
        runtime_config=_preflight_config(pandoc_path=str(pandoc)),
    )

    assert result["status"] == "completed"
    assert result["phase"] == 7
    assert result["entry"] == PRODUCTION_ENTRY_ID
    for name in (
        "references_summary", "floating_report", "injected_manuscript",
        "mapping_md", "mapping_csv", "final_docx",
    ):
        assert Path(result["outputs"][name]).exists()

    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    context = state["context"]
    assert context["preflight_mode"] is True
    assert context["preflight_config"]["floating_policy"] == "keep"
    assert context["internal_validation_state"]["summary"]["status"] == "completed"
    assert context["internal_validation_state"]["injection_preview"]["status"] == "completed"
    ordinary_waits = {
        item.get("type") for item in state["history"]
        if item.get("action") == "require_confirmation"
    }
    assert ordinary_waits == {"IF_CONFIRM"}


def test_floating_keep_records_but_does_not_block(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-keep"
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A", dry_run=True, runtime_config=_preflight_config()
    )
    assert result["status"] == "completed"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    floating = state["context"]["floating_state"]
    assert len(floating["expansions"]) == 1
    assert floating["applied"] is False
    assert floating["skipped_by_user"] is True


def test_floating_expand_applies_marked_text_without_second_prompt(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-expand"
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(floating_policy="expand"),
    )
    assert result["status"] == "completed"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    context = state["context"]
    assert context["floating_state"]["applied"] is True
    assert "【AI扩写区开始】" in context["working_manuscript_text"]


def test_floating_ask_interrupts_only_when_expansion_exists(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-ask"
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(floating_policy="ask"),
    )
    assert result["status"] == "waiting_confirmation"
    assert result["gate"] == "FLOATING_CONFIRM"
    assert result["data"]["floating_references"] == 1

    matched_dir = tmp_path / "matched"
    matched_dir.mkdir()
    manuscript2, bib2 = _write_fixture(matched_dir)
    output2 = tmp_path / "matched-output"
    no_floating = ManuscriptWorkflow(
        str(manuscript2), str(bib2), str(output2)
    ).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(floating_policy="ask"),
    )
    assert no_floating["status"] == "completed"
    assert no_floating["phase"] == 7


def test_preflight_state_survives_restart_and_safety_resume(tmp_path):
    manuscript, bib = _write_floating_fixture(tmp_path)
    output = tmp_path / "floating-restart"
    ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(
            body_if=8, table_if=12, floating_policy="ask"
        ),
    )

    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).confirm("FLOATING_CONFIRM", floating="no", dry_run=True)
    assert result["status"] == "completed"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    config = state["context"]["preflight_config"]
    assert config["body_if"]["threshold"] == 8.0
    assert config["table_if"]["threshold"] == 12.0
    assert config["journal"] == "nature"
    assert config["floating_policy"] == "ask"


def test_preflight_missing_or_ambiguous_config_fails_closed(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    missing = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "missing")
    ).run(
        mode="A", dry_run=True,
        runtime_config={"body_if": "disable"},
    )
    assert missing["reason"] == "PREFLIGHT_CONFIG_REQUIRED"

    ambiguous = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "ambiguous")
    ).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(journal="advanced"),
    )
    assert ambiguous["status"] == "blocked"
    assert ambiguous["reason"] == "JOURNAL_AMBIGUOUS"


def test_preflight_preserves_legacy_and_dependency_safety_blocks(
    tmp_path, monkeypatch
):
    manuscript, bib = _write_fixture(tmp_path)
    manuscript.write_text(
        "# Introduction\n\nLegacy citation ^\\[1\\]^.\n\n# References\n\n1. Unsafe.\n",
        encoding="utf-8",
    )

    def unsafe_mapping(self, markdown_text, conversion, dry_run):
        return self._blocked(
            "LEGACY_MAPPING_UNSAFE", {"issues": [{"type": "ambiguous"}]},
            phase="MODE_C",
        )

    monkeypatch.setattr(ManuscriptWorkflow, "_run_mode_c", unsafe_mapping)
    legacy = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "legacy")
    ).run(
        mode="A", dry_run=True, runtime_config=_preflight_config()
    )
    assert legacy["status"] == "blocked"
    assert legacy["reason"] == "LEGACY_MAPPING_UNSAFE"

    monkeypatch.setattr(
        ManuscriptWorkflow, "_validate_environment_and_inputs",
        lambda self, pandoc_path=None: self._blocked(
            "PANDOC_REQUIRED", {"dependency": "pandoc"}, phase=0
        ),
    )
    dependency = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "dependency")
    ).run(
        mode="A", dry_run=True, runtime_config=_preflight_config()
    )
    assert dependency["status"] == "blocked"
    assert dependency["reason"] == "PANDOC_REQUIRED"


def test_preflight_export_failure_remains_a_safety_block(tmp_path, monkeypatch):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "export-failure"
    pandoc = tmp_path / "pandoc.exe"
    pandoc.write_bytes(b"")

    from docx_exporter import DocxExporter
    monkeypatch.setattr(
        DocxExporter, "export_manuscript", lambda self, *args, **kwargs: None
    )
    result = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A", dry_run=False,
        runtime_config=_preflight_config(pandoc_path=str(pandoc)),
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "DOCX_EXPORT_FAILED"


def test_am_resolves_to_the_existing_cached_csl(tmp_path, monkeypatch):
    from journal_compiler import JournalResolver, JournalStyleManager

    cache = tmp_path / "csl-cache"
    cache.mkdir()
    csl = cache / "advanced-materials.csl"
    csl.write_text("<style/>", encoding="utf-8")
    monkeypatch.setattr(JournalStyleManager, "CSL_CACHE_DIR", str(cache))

    config = JournalResolver.resolve("AM")
    assert config.csl_name == "advanced-materials"
    assert JournalStyleManager().get_or_download_csl(config.csl_name) == str(csl)


def test_phase6_export_failure_persists_and_formally_resumes_once(
    tmp_path, monkeypatch
):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "phase6-retry"
    pandoc = tmp_path / "pandoc.exe"
    pandoc.write_bytes(b"")
    calls = []

    from docx_exporter import DocxExporter

    def flaky_export(self, markdown_path, **kwargs):
        calls.append((markdown_path, kwargs))
        if len(calls) == 1:
            return None
        Path(kwargs["output_path"]).write_bytes(b"new docx")
        return kwargs["output_path"]

    monkeypatch.setattr(DocxExporter, "export_manuscript", flaky_export)
    first = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(
        mode="A", dry_run=False,
        runtime_config=_preflight_config(
            journal="AM", pandoc_path=str(pandoc)
        ),
    )

    assert first["status"] == "blocked"
    assert first["reason"] == "DOCX_EXPORT_FAILED"
    state_path = output / "workflow_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    context = state["context"]
    assert state["phase"] == 6
    assert context["current_phase"] == 6
    assert context["phase6_state"]["status"] == "blocked"
    assert context["preflight_config"]["journal"] == "AM"
    assert context.get("if_unknown_review", {}) == {}
    assert context["floating_state"]["applied"] is False
    injected = Path(context["working_markdown_path"])
    injected_before = injected.read_text(encoding="utf-8")

    resumed = ManuscriptWorkflow(
        str(manuscript), str(bib), str(output)
    ).run(mode="B", phase=6, dry_run=False)

    assert resumed["status"] == "completed"
    assert resumed["phase"] == 7
    assert len(calls) == 2
    assert injected.read_text(encoding="utf-8") == injected_before
    assert Path(resumed["outputs"]["final_docx"]).exists()
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert final_state["context"]["current_phase"] == 7


def test_cli_preflight_is_the_same_single_workflow_route(tmp_path):
    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "cli-preflight"
    script = PROJECT_ROOT / "workflows" / "manuscript_workflow.py"
    completed = subprocess.run(
        [
            sys.executable, str(script), str(manuscript), str(bib),
            "--output", str(output), "--mode", "A", "--preflight",
            "--body-if", "disable", "--table-if", "disable",
            "--journal", "nature", "--all-authors", "no",
            "--floating-policy", "keep",
        ],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["entry"] == PRODUCTION_ENTRY_ID
    assert result["status"] == "completed"
    assert result["phase"] == 7


def test_independent_body_and_table_if_policies_cover_all_combinations():
    PolicyManager.reset()
    get_policy().resolve_profile("advanced_materials_review")
    cases = [
        (False, None, False, None, IFGateResult.NOT_APPLIED, IFGateResult.NOT_APPLIED),
        (True, 6, False, None, IFGateResult.GLOBAL_PASS, IFGateResult.NOT_APPLIED),
        (False, None, True, 10, IFGateResult.NOT_APPLIED, IFGateResult.BELOW_THRESHOLD),
        (True, 6, True, 10, IFGateResult.GLOBAL_PASS, IFGateResult.BELOW_THRESHOLD),
        (True, 8, True, 12, IFGateResult.GLOBAL_PASS, IFGateResult.BELOW_THRESHOLD),
    ]
    try:
        for body_enabled, body_threshold, table_enabled, table_threshold, body_result, table_result in cases:
            gate = BodyCitationIFGate()
            gate.apply_runtime_policy(
                body_threshold=body_threshold,
                table_threshold=table_threshold,
                body_if_enabled=body_enabled,
                table_if_enabled=table_enabled,
            )
            body = _if_candidate("Body", "ACS Sens.", "Body sentence.")
            table = _if_candidate("Table", "ACS Sens.", "| Material | Ref |\n| PDMS | [1] |")
            report = gate.validate_candidates([body, table])
            assert [d.result for d in report.decisions] == [body_result, table_result]
            assert body.is_rejected is (body_result == IFGateResult.BELOW_THRESHOLD)
            assert table.is_rejected is (table_result == IFGateResult.BELOW_THRESHOLD)
    finally:
        PolicyManager.reset()


def test_workflow_resolves_profile_recommendations_from_policy_manager():
    PolicyManager.reset()
    try:
        assert ManuscriptWorkflow.get_preflight_defaults("advanced_materials_review") == {
            "profile_name": "advanced_materials_review",
            "recommended_body_if": 6.0,
            "recommended_table_if": 10.0,
            "body_if_enabled": True,
            "table_if_enabled": True,
        }
        assert ManuscriptWorkflow.get_preflight_defaults("nature_review")[
            "recommended_body_if"
        ] == 15.0
        assert ManuscriptWorkflow.get_preflight_defaults("nature_review")[
            "recommended_table_if"
        ] == 20.0
        assert ManuscriptWorkflow.get_preflight_defaults()["profile_name"] == "default"
    finally:
        PolicyManager.reset()


def test_unknown_if_is_independent_review_not_rejection_or_injection(tmp_path):
    PolicyManager.reset()
    get_policy().resolve_profile("advanced_materials_review")
    try:
        gate = BodyCitationIFGate()
        gate.apply_runtime_policy(
            body_if_enabled=False, table_if_enabled=True, table_threshold=10,
        )
        body = _if_candidate("UnknownBody", "Unknown Journal", "Body sentence.")
        table = _if_candidate(
            "UnknownTable", "Unknown Journal", "| Material | Ref |\n| PDMS | [1] |"
        )
        report = gate.validate_candidates([body, table])
        assert [d.result for d in report.decisions] == [
            IFGateResult.NOT_APPLIED, IFGateResult.UNKNOWN,
        ]
        assert not body.is_rejected
        assert not table.is_rejected
    finally:
        PolicyManager.reset()

    manuscript, bib = _write_fixture(tmp_path)
    output = tmp_path / "unknown-review"
    result = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=False,
        runtime_config=_preflight_config(body_if=6, profile="advanced_materials_review"),
    )
    assert result["status"] == "waiting_confirmation"
    assert result["gate"] == "IF_UNKNOWN_REVIEW"
    assert result["data"]["unknown_candidates"]
    assert not (output / "injected_manuscript.md").exists()

    resumed = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).confirm(
        "IF_UNKNOWN_REVIEW", if_unknown="exclude", dry_run=True,
    )
    assert resumed["status"] == "completed"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert all(
        candidate["is_rejected"]
        for candidate in state["context"]["candidate_state"]["candidates"]
    )
    PolicyManager.reset()


def test_preflight_presentation_is_localized_and_does_not_show_internal_values():
    skill_path = PROJECT_ROOT / "skill" / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    section = skill.split("### Preflight Configuration", 1)[1].split(
        "### 模式 A", 1
    )[0]
    assert "正文文献影响因子筛选" in section
    assert "Body IF |" not in section
    displayed = section.split("中文 Preflight：", 1)[1].split(
        "若当前 Profile", 1
    )[0]
    assert "body_if=disable" not in displayed
    assert "English preflight" in section


def test_phase0_accepts_explicit_pandoc_path_without_path_lookup(
    tmp_path, monkeypatch
):
    _markdown, bib = _write_fixture(tmp_path)
    manuscript = tmp_path / "manuscript.docx"
    manuscript.write_bytes(b"placeholder docx")
    explicit_pandoc = tmp_path / "pandoc.exe"
    explicit_pandoc.write_bytes(b"placeholder")
    observed = {}

    def explicit_environment(self, bib_path=None, pandoc_path=None):
        observed["bib_path"] = bib_path
        observed["pandoc_path"] = pandoc_path
        return {
            "python": {"available": True},
            "pandoc": {
                "available": True,
                "path": pandoc_path,
                "explicit": True,
                "pandoc_crossref": {"available": True},
            },
            "zotero_bib": {"available": True},
        }

    monkeypatch.setattr(EnvironmentChecker, "check_all", explicit_environment)
    validation = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "out")
    )._validate_environment_and_inputs(pandoc_path=str(explicit_pandoc))
    assert validation["status"] == "completed"
    assert validation["phase"] == 0
    assert observed["pandoc_path"] == str(explicit_pandoc)


def test_preflight_persists_explicit_pandoc_path_for_restart(tmp_path, monkeypatch):
    manuscript, bib = _write_fixture(tmp_path)
    explicit_pandoc = tmp_path / "pandoc.exe"
    explicit_pandoc.write_bytes(b"placeholder")
    monkeypatch.setattr(
        EnvironmentChecker,
        "_check_pandoc",
        staticmethod(lambda path=None: {"available": True, "path": path}),
    )
    output = tmp_path / "pandoc-state"
    result = ManuscriptWorkflow(str(manuscript), str(bib), str(output)).run(
        mode="A", dry_run=True,
        runtime_config=_preflight_config(pandoc_path=str(explicit_pandoc)),
    )
    assert result["status"] == "completed"
    state = json.loads((output / "workflow_state.json").read_text(encoding="utf-8"))
    assert state["context"]["preflight_config"]["pandoc_path"] == str(
        explicit_pandoc.resolve()
    )


def test_docx_preparation_receives_the_explicit_pandoc_path(tmp_path, monkeypatch):
    manuscript = tmp_path / "manuscript.docx"
    manuscript.write_bytes(b"placeholder docx")
    bib = tmp_path / "references.bib"
    bib.write_text("@article{Ref2025, title={T}, year={2025}}", encoding="utf-8")
    explicit_pandoc = tmp_path / "pandoc.exe"
    explicit_pandoc.write_bytes(b"placeholder")
    observed = {}

    def fake_convert(self, input_path, output_path=None):
        observed["pandoc_path"] = self._pandoc_path
        observed["input_path"] = input_path
        return "# Introduction\n"

    monkeypatch.setattr(PandocAdapter, "convert_docx_to_markdown", fake_convert)
    text, conversion = ManuscriptWorkflow(
        str(manuscript), str(bib), str(tmp_path / "out")
    )._prepare_markdown(dry_run=True, pandoc_path=str(explicit_pandoc))
    assert text == "# Introduction\n"
    assert conversion == {"converted": True, "source_markdown": None}
    assert observed == {
        "pandoc_path": str(explicit_pandoc.resolve()),
        "input_path": str(manuscript.resolve()),
    }
