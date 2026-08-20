import os
import sys

import pytest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "engine"))

from phase_gate import WorkflowGate


def test_workflow_context_survives_new_process_object(tmp_path):
    state_file = str(tmp_path / "workflow_state.json")
    required_context = {
        "current_phase": 2,
        "mode": "A",
        "manuscript_path": "/input/manuscript.md",
        "working_markdown_path": "/run/migrated.md",
        "bib_path": "/input/references.bib",
        "used_keys": ["Old2024"],
        "pending_keys": ["New2025"],
        "if_runtime_policy": {"body": 8.0, "disabled": False},
        "table_if_policy": {"threshold": 15.0, "disabled": False},
        "candidate_state": [{"citekey": "New2025"}],
        "generated_report_paths": {"summary": "/run/References_Summary.md"},
        "output_directory": "/run",
        "journal": "nature",
        "all_authors": True,
        "confirmation_state": {"gate": "SUMMARY_CONFIRM"},
    }

    gate = WorkflowGate(state_file)
    gate.start_phase(2)
    gate.set_context(required_context)
    gate.require_confirmation("SUMMARY_CONFIRM")

    restored = WorkflowGate(state_file)
    assert restored.phase == 2
    assert restored.confirmation_type == "SUMMARY_CONFIRM"
    assert restored.context == required_context


def test_workflow_context_rejects_non_json_objects(tmp_path):
    gate = WorkflowGate(str(tmp_path / "workflow_state.json"))
    with pytest.raises(ValueError, match="JSON-compatible"):
        gate.set_context({"invalid": object()})
