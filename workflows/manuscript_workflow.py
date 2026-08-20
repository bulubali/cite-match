#!/usr/bin/env python3
"""CiteMatch production workflow.

``ManuscriptWorkflow`` is the single external production entry for Skill,
CLI, regression, and production-validation callers.  It coordinates existing
modules and returns structured state; it never talks to the user directly.
"""
import argparse
from dataclasses import asdict
import json
import os
import re
import sys
import tempfile
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_DIR = os.path.join(PROJECT_ROOT, "engine")
CONVERTERS_DIR = os.path.join(PROJECT_ROOT, "converters")
EXPORTERS_DIR = os.path.join(PROJECT_ROOT, "exporters")
INSTALLERS_DIR = os.path.join(PROJECT_ROOT, "installers")
for module_dir in (
    PROJECT_ROOT, ENGINE_DIR, CONVERTERS_DIR, EXPORTERS_DIR, INSTALLERS_DIR,
):
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)


PRODUCTION_ENTRY_ID = "citematch.workflows.manuscript_workflow.ManuscriptWorkflow"
SUPPORTED_MANUSCRIPT_EXTENSIONS = {".md", ".docx"}
REFERENCE_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s*(?:References|参考文献)\s*|"
    r"\*\*(?:References|参考文献)\*\*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
LEGACY_CITATION_RE = re.compile(r"\^\\\[([^\]]+?)\\\]\^")


class ManuscriptWorkflow:
    """Single external production entry for CiteMatch."""

    def __init__(self, manuscript_path: str, bib_path: str,
                 output_dir: Optional[str] = None,
                 state_file: Optional[str] = None):
        self._manuscript_path = os.path.abspath(manuscript_path)
        self._bib_path = os.path.abspath(bib_path)
        self._output_dir = os.path.abspath(
            output_dir or os.path.join(PROJECT_ROOT, "output")
        )
        self._state_file = state_file or os.path.join(
            self._output_dir, "workflow_state.json"
        )
        self._errors: list[str] = []
        self._mode: str = ""
        self._last_markdown: str = ""

    def validate_inputs(self) -> bool:
        """Validate production input paths and supported file types."""
        self._errors = []
        if not os.path.exists(self._manuscript_path):
            self._errors.append(f"Manuscript not found: {self._manuscript_path}")
        elif os.path.splitext(self._manuscript_path)[1].lower() not in \
                SUPPORTED_MANUSCRIPT_EXTENSIONS:
            self._errors.append(
                "Unsupported manuscript type: "
                f"{os.path.splitext(self._manuscript_path)[1]}"
            )
        if not os.path.exists(self._bib_path):
            self._errors.append(f"Bib file not found: {self._bib_path}")
        elif os.path.splitext(self._bib_path)[1].lower() != ".bib":
            self._errors.append(f"Bibliography must be .bib: {self._bib_path}")
        return len(self._errors) == 0

    def run(
        self,
        mode: str = "A",
        phase: Optional[int] = None,
        dry_run: bool = True,
        runtime_config: Optional[dict] = None,
    ) -> dict:
        """Run the canonical production route and return structured state.

        The first stabilization stage integrates input preparation, Mode C,
        Used/Pending detection, and Phase-1 confirmation state.  Later phases
        fail closed until their existing modules are connected here.
        """
        if runtime_config is not None:
            return self.run_preflight(runtime_config, dry_run=dry_run)

        mode = str(mode).upper().strip()
        if mode not in {"A", "B", "C"}:
            return self._blocked(
                "INVALID_MODE", {"mode": mode, "allowed": ["A", "B", "C"]}
            )
        self._mode = mode

        # Phase 6 is the one standalone phase whose input artifact and
        # complete runtime configuration are already persisted by the
        # production workflow.  This permits a retry after a recoverable
        # external export dependency failure without replaying Phase 1-5.
        if mode == "B" and phase == 6:
            return self._resume_phase6(dry_run)

        validation = self._validate_environment_and_inputs()
        if validation["status"] == "blocked":
            return validation

        try:
            markdown_text, conversion = self._prepare_markdown(dry_run=dry_run)
        except Exception as exc:
            return self._blocked(
                "INPUT_PREPARATION_FAILED", {"error": str(exc)}
            )

        if mode == "C":
            return self._run_mode_c(markdown_text, conversion, dry_run)

        if mode == "B":
            return self._blocked(
                "STANDALONE_PHASE_NOT_INTEGRATED",
                {
                    "mode": mode,
                    "phase": phase,
                    "entry": PRODUCTION_ENTRY_ID,
                    "fallback_allowed": False,
                },
                phase=phase,
            )

        legacy_count = len(LEGACY_CITATION_RE.findall(markdown_text))
        if legacy_count:
            return self._blocked(
                "LEGACY_MIGRATION_REQUIRED",
                {
                    "legacy_occurrences": legacy_count,
                    "required_mode": "C",
                    "entry": PRODUCTION_ENTRY_ID,
                },
                phase=1,
            )

        return self._start_mode_a(
            markdown_text, conversion, validation["data"], dry_run
        )

    def _resume_phase6(self, dry_run: bool) -> dict:
        """Resume only a persisted Phase-6 export after a recoverable failure."""
        from phase_gate import WorkflowGate

        gate = WorkflowGate(state_file=self._state_file)
        context = gate.context
        required = (
            "preflight_config", "journal", "all_authors", "bib_path",
            "pandoc_path", "working_markdown_path", "output_directory",
            "final_output_path",
        )
        missing = [key for key in required if context.get(key) is None]
        if gate.phase != 6 or gate.is_waiting or missing:
            return self._blocked(
                "PHASE6_RESUME_UNAVAILABLE",
                {
                    "phase": gate.phase,
                    "waiting_confirmation": gate.is_waiting,
                    "missing": missing,
                },
                phase=gate.phase,
            )
        if os.path.abspath(context["output_directory"]) != self._output_dir:
            return self._blocked(
                "PHASE6_RESUME_OUTPUT_MISMATCH",
                {
                    "state_output": context["output_directory"],
                    "requested_output": self._output_dir,
                },
                phase=6,
            )
        if os.path.abspath(context["bib_path"]) != self._bib_path:
            return self._blocked(
                "PHASE6_RESUME_INPUT_MISMATCH",
                {
                    "state_bib": context["bib_path"],
                    "requested_bib": self._bib_path,
                },
                phase=6,
            )
        return self._run_phase6(context, dry_run)

    def _start_mode_a(
        self, markdown_text: str, conversion: dict,
        validation_data: dict, dry_run: bool,
    ) -> dict:
        """Initialize the existing Phase-1 state and compatibility gate."""
        from phase_gate import WorkflowGate

        used_pending = self._compute_used_pending(markdown_text)
        os.makedirs(self._output_dir, exist_ok=True)
        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(1)
        gate.require_confirmation("IF_CONFIRM")
        working_markdown = conversion.get("source_markdown")
        if (not working_markdown and
                os.path.splitext(self._manuscript_path)[1].lower() == ".md"):
            working_markdown = self._manuscript_path
        gate.set_context({
            "current_phase": 1,
            "mode": "A",
            "manuscript_path": self._manuscript_path,
            "working_markdown_path": working_markdown,
            "bib_path": self._bib_path,
            "used_keys": used_pending["used_keys"],
            "pending_keys": used_pending["pending_keys"],
            "if_runtime_policy": {"threshold": None, "disabled": False},
            "table_if_policy": {"threshold": None, "disabled": False},
            "candidate_state": {"papers": [], "candidates": []},
            "generated_report_paths": {},
            "output_directory": self._output_dir,
            "journal": None,
            "all_authors": None,
            "csl_path": None,
            "pandoc_path": None,
            "final_output_path": os.path.join(
                self._output_dir, "Final_Manuscript.docx"
            ),
            "floating_confirmed": None,
            "floating_policy": None,
            "preflight_mode": False,
            "preflight_config": None,
            "working_manuscript_text": markdown_text,
            "confirmation_state": {
                "gate": "IF_CONFIRM", "approved": False,
            },
        })
        return {
            "status": "waiting_confirmation",
            "phase": 1,
            "gate": "IF_CONFIRM",
            "mode": "A",
            "entry": PRODUCTION_ENTRY_ID,
            "data": {
                **validation_data,
                **conversion,
                **used_pending,
            },
        }

    def run_preflight(self, runtime_config: dict, dry_run: bool = True) -> dict:
        """Run Mode C and Phase 1-7 after one complete user preflight.

        Normal validation checkpoints remain persisted internally.  Only a
        genuine safety decision (currently floating policy ``ask`` with actual
        expansions) may return ``waiting_confirmation``.
        """
        if not isinstance(runtime_config, dict):
            return self._blocked(
                "INVALID_PREFLIGHT_CONFIG",
                {"error": "runtime_config must be a mapping"},
                phase="PREFLIGHT",
            )
        required = (
            "body_if", "table_if", "journal", "all_authors",
            "floating_policy",
        )
        missing = [name for name in required if runtime_config.get(name) is None]
        if missing:
            return self._blocked(
                "PREFLIGHT_CONFIG_REQUIRED", {"missing": missing},
                phase="PREFLIGHT",
            )
        try:
            profile = self.get_preflight_defaults(runtime_config.get("profile"))
            body_policy = self._parse_threshold(
                runtime_config["body_if"], "body-if"
            )
            table_policy = self._parse_threshold(
                runtime_config["table_if"], "table-if"
            )
            journal = self._validate_journal_choice(
                runtime_config["journal"], runtime_config.get("csl_path")
            )
            all_authors = self._parse_yes_no(
                runtime_config["all_authors"], "all-authors"
            )
            floating_policy = str(
                runtime_config["floating_policy"]
            ).strip().lower()
            if floating_policy not in {"keep", "ask", "expand"}:
                raise ValueError(
                    "floating-policy must be 'keep', 'ask', or 'expand'"
                )
            csl_path = runtime_config.get("csl_path")
            if csl_path is not None:
                csl_path = self._validate_existing_file(csl_path, "csl")
            pandoc_path = runtime_config.get("pandoc_path")
            if pandoc_path is not None:
                pandoc_path = self._validate_existing_file(
                    pandoc_path, "pandoc-path"
                )
        except ValueError as exc:
            reason = (
                "JOURNAL_AMBIGUOUS"
                if str(exc).startswith("journal is ambiguous")
                else "INVALID_PREFLIGHT_CONFIG"
            )
            return self._blocked(
                reason, {"error": str(exc)}, phase="PREFLIGHT"
            )

        validation = self._validate_environment_and_inputs(
            pandoc_path=pandoc_path
        )
        if validation["status"] == "blocked":
            return validation
        try:
            markdown_text, conversion = self._prepare_markdown(
                dry_run=dry_run, pandoc_path=pandoc_path
            )
        except Exception as exc:
            return self._blocked(
                "INPUT_PREPARATION_FAILED", {"error": str(exc)}
            )

        migration = None
        needs_migration = bool(
            LEGACY_CITATION_RE.search(markdown_text)
            or self._count_static_numeric_citations(markdown_text)
            or REFERENCE_HEADING_RE.search(markdown_text)
        )
        if needs_migration:
            migration = self._run_mode_c(markdown_text, conversion, dry_run)
            if migration.get("status") != "completed":
                return migration
            markdown_text = self._last_markdown
            conversion = {
                "converted": conversion.get("converted", False),
                "source_markdown": migration.get("outputs", {}).get("markdown"),
            }

        started = self._start_mode_a(
            markdown_text, conversion, validation["data"], dry_run
        )
        if started.get("status") != "waiting_confirmation":
            return started

        from phase_gate import WorkflowGate
        gate = WorkflowGate(state_file=self._state_file)
        context = gate.context
        context.update({
            "preflight_mode": True,
            "floating_policy": floating_policy,
            "floating_confirmed": (
                True if floating_policy == "expand"
                else False if floating_policy == "keep" else None
            ),
            "preflight_config": {
                "profile": profile,
                "body_if": body_policy,
                "table_if": table_policy,
                "journal": journal,
                "all_authors": all_authors,
                "floating_policy": floating_policy,
                "csl_path": csl_path,
                "pandoc_path": pandoc_path,
            },
            "migration_state": (
                migration.get("data") if migration else {"required": False}
            ),
            "internal_validation_state": {},
        })
        gate.set_context(context)
        return self.confirm(
            "IF_CONFIRM",
            body_if=runtime_config["body_if"],
            table_if=runtime_config["table_if"],
            journal=journal,
            all_authors=all_authors,
            csl_path=csl_path,
            pandoc_path=pandoc_path,
            dry_run=dry_run,
        )

    def confirm(
        self,
        gate_name: str,
        body_if=None,
        table_if=None,
        journal: Optional[str] = None,
        all_authors=None,
        floating=None,
        if_unknown=None,
        csl_path: Optional[str] = None,
        pandoc_path: Optional[str] = None,
        dry_run: bool = True,
    ) -> dict:
        """Approve a gate, persist structured answers, and resume safely."""
        from cm_types import WorkflowBlockedError
        from phase_gate import WorkflowGate

        gate = WorkflowGate(state_file=self._state_file)
        context = gate.context
        structured = any(value is not None for value in (
            body_if, table_if, journal, all_authors, floating,
            if_unknown, csl_path, pandoc_path,
        ))
        try:
            if gate_name == "FLOATING_CONFIRM" and floating is None:
                raise ValueError("floating confirmation requires 'yes' or 'no'")
            if gate_name == "IF_UNKNOWN_REVIEW":
                if if_unknown not in {"approve", "exclude"}:
                    raise ValueError(
                        "IF unknown review requires 'approve' or 'exclude'"
                    )
                review = dict(context.get("if_unknown_review", {}))
                if if_unknown == "exclude":
                    unknown_targets = {
                        (item.get("citekey"), item.get("target_sentence"))
                        for item in review.get("candidates", [])
                    }
                    for candidate in context.get("candidate_state", {}).get(
                        "candidates", []
                    ):
                        identity = (
                            candidate.get("paper", {}).get("citekey"),
                            candidate.get("target_sentence"),
                        )
                        if identity in unknown_targets:
                            candidate["is_rejected"] = True
                            candidate["rejection_reason"] = (
                                "IF UNKNOWN excluded by user review"
                            )
                review["resolution"] = if_unknown
                context["if_unknown_review"] = review
            if body_if is not None:
                context["if_runtime_policy"] = self._parse_threshold(
                    body_if, "body-if"
                )
            if table_if is not None:
                context["table_if_policy"] = self._parse_threshold(
                    table_if, "table-if"
                )
            if journal is not None:
                clean_journal = str(journal).strip()
                if not clean_journal or any(ch in clean_journal for ch in "\r\n\x00"):
                    raise ValueError("journal must be a non-empty single-line value")
                context["journal"] = clean_journal
            if all_authors is not None:
                context["all_authors"] = self._parse_yes_no(
                    all_authors, "all-authors"
                )
            if floating is not None:
                context["floating_confirmed"] = self._parse_yes_no(
                    floating, "floating"
                )
            if csl_path is not None:
                context["csl_path"] = self._validate_existing_file(
                    csl_path, "csl"
                )
            if pandoc_path is not None:
                context["pandoc_path"] = self._validate_existing_file(
                    pandoc_path, "pandoc-path"
                )
            if gate_name == "EXPORT_CONFIRM":
                if not context.get("journal"):
                    raise ValueError("journal is required for export confirmation")
                if context.get("all_authors") is None:
                    raise ValueError(
                        "all-authors is required for export confirmation"
                    )
        except ValueError as exc:
            return self._blocked(
                "INVALID_CONFIRMATION_VALUE",
                {"gate": gate_name, "error": str(exc)},
                phase=gate.phase,
            )

        try:
            gate.approve(gate_name)
        except WorkflowBlockedError as exc:
            return self._blocked(
                "CONFIRMATION_REJECTED", {"error": str(exc), "gate": gate_name}
            )
        context["confirmation_state"] = {
            "gate": gate_name, "approved": True,
        }
        gate.set_context(context)

        # Backward-compatible gate-only approval.  Structured production
        # confirmation resumes Phase 1; SUMMARY_CONFIRM always resumes.
        if gate_name == "IF_CONFIRM" and structured:
            return self._run_phase2(context, dry_run)
        if gate_name == "SUMMARY_CONFIRM":
            return self._run_phase3(context, dry_run)
        if gate_name == "FLOATING_CONFIRM":
            return self._resume_phase4(context, dry_run)
        if gate_name == "IF_UNKNOWN_REVIEW":
            return self._run_phase4(context, dry_run)
        if gate_name == "INJECTION_CONFIRM":
            return self._run_phase5(context, dry_run)
        if gate_name == "EXPORT_CONFIRM":
            return self._run_phase6(context, dry_run)

        return {
            "status": "completed",
            "phase": gate.phase,
            "gate": gate_name,
            "entry": PRODUCTION_ENTRY_ID,
            "outputs": {"confirmation_state": gate.get_state()},
        }

    @staticmethod
    def _parse_threshold(value, name: str) -> dict:
        if isinstance(value, str) and value.strip().lower() == "disable":
            return {"threshold": None, "disabled": True}
        try:
            threshold = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a non-negative float or 'disable'")
        if threshold < 0:
            raise ValueError(f"{name} must be a non-negative float or 'disable'")
        return {"threshold": threshold, "disabled": False}

    @staticmethod
    def get_preflight_defaults(profile_name: Optional[str] = None) -> dict:
        """Resolve the profile-owned recommendations for one Preflight.

        This is a read-only query on the canonical PolicyManager.  Omitting a
        profile deliberately selects the existing ``default`` policy.
        """
        from policy_manager import get_policy
        return get_policy().resolve_profile(profile_name)

    @staticmethod
    def _parse_yes_no(value, name: str) -> bool:
        if isinstance(value, bool):
            return value
        clean = str(value).strip().lower()
        if clean == "yes":
            return True
        if clean == "no":
            return False
        raise ValueError(f"{name} must be 'yes' or 'no'")

    @staticmethod
    def _validate_existing_file(value, name: str) -> str:
        path = os.path.abspath(os.path.expanduser(str(value).strip()))
        if not str(value).strip() or not os.path.isfile(path):
            raise ValueError(f"{name} must be an existing file")
        return path

    @staticmethod
    def _validate_journal_choice(value, csl_path=None) -> str:
        """Reject only genuinely ambiguous journal aliases at preflight."""
        clean = str(value).strip()
        if not clean or any(ch in clean for ch in "\r\n\x00"):
            raise ValueError("journal must be a non-empty single-line value")
        if csl_path:
            return clean

        from journal_compiler import JOURNAL_ALIASES
        lowered = clean.lower()
        if lowered in JOURNAL_ALIASES or lowered in set(JOURNAL_ALIASES.values()):
            return clean
        matches = {
            csl_name for alias, csl_name in JOURNAL_ALIASES.items()
            if alias in lowered or lowered in alias
        }
        if len(matches) > 1:
            raise ValueError(
                "journal is ambiguous: " + ", ".join(sorted(matches))
            )
        return clean

    def _run_phase2(self, context: dict, dry_run: bool) -> dict:
        from literature_intel import LiteratureIntelligence
        from phase_gate import WorkflowGate

        try:
            intel = LiteratureIntelligence()
            intel.load_bib(context["bib_path"])
            papers = intel.analyze_pending(context.get("pending_keys", []))
            summary_path = None
            if not dry_run:
                os.makedirs(context["output_directory"], exist_ok=True)
                summary_path = os.path.join(
                    context["output_directory"], "References_Summary.md"
                )
                intel.generate_summary(papers, summary_path)
        except Exception as exc:
            return self._blocked(
                "PHASE_2_FAILED", {"error": str(exc)}, phase=2
            )

        candidate_state = dict(context.get("candidate_state", {}))
        candidate_state["papers"] = [asdict(paper) for paper in papers]
        context["candidate_state"] = candidate_state
        context["current_phase"] = 2
        if summary_path:
            reports = dict(context.get("generated_report_paths", {}))
            reports["references_summary"] = summary_path
            context["generated_report_paths"] = reports

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(2)
        if context.get("preflight_mode"):
            validations = dict(context.get("internal_validation_state", {}))
            validations["summary"] = {
                "status": "completed",
                "path": summary_path,
                "papers_analyzed": len(papers),
            }
            context["internal_validation_state"] = validations
            context["confirmation_state"] = {
                "gate": "SUMMARY_CONFIRM", "approved": True,
                "internal": True,
            }
            gate.set_context(context)
            return self._run_phase3(context, dry_run)

        gate.require_confirmation("SUMMARY_CONFIRM")
        context["confirmation_state"] = {
            "gate": "SUMMARY_CONFIRM", "approved": False,
        }
        gate.set_context(context)
        return {
            "status": "waiting_confirmation",
            "phase": 2,
            "gate": "SUMMARY_CONFIRM",
            "mode": context.get("mode", "A"),
            "entry": PRODUCTION_ENTRY_ID,
            "data": {"papers_analyzed": len(papers)},
            "outputs": {"references_summary": summary_path, "dry_run": dry_run},
        }

    def _run_phase3(self, context: dict, dry_run: bool) -> dict:
        from body_if_gate import BodyCitationIFGate
        from literature_intel import PaperIntel
        from phase_gate import WorkflowGate
        from semantic_mapper import SemanticMapper

        paper_state = context.get("candidate_state", {}).get("papers", [])
        if not paper_state:
            return self._blocked(
                "WORKFLOW_STATE_INCOMPLETE", {"missing": "Phase 2 paper state"},
                phase=3,
            )
        try:
            manuscript_text = self._context_manuscript_text(context)
            papers = [PaperIntel(**paper) for paper in paper_state]
            mapper = SemanticMapper()
            candidates = mapper.map_papers_to_manuscript(papers, manuscript_text)

            if_gate = BodyCitationIFGate()
            body_policy = context.get("if_runtime_policy", {})
            table_policy = context.get("table_if_policy", {})
            if_gate.apply_runtime_policy(
                body_threshold=body_policy.get("threshold"),
                table_threshold=table_policy.get("threshold"),
                body_if_enabled=not bool(body_policy.get("disabled")),
                table_if_enabled=not bool(table_policy.get("disabled")),
            )
            if_report = if_gate.validate_candidates(candidates)

            candidate_table_path = None
            if not dry_run:
                candidate_table_path = os.path.join(
                    context["output_directory"], "Citation_Candidate_Report.md"
                )
                with open(candidate_table_path, "w", encoding="utf-8") as handle:
                    handle.write(mapper.generate_candidate_table(candidates))
        except Exception as exc:
            return self._blocked(
                "PHASE_3_FAILED", {"error": str(exc)}, phase=3
            )

        candidate_state = dict(context.get("candidate_state", {}))
        candidate_state["candidates"] = [asdict(candidate) for candidate in candidates]
        context["candidate_state"] = candidate_state
        context["current_phase"] = 3
        if candidate_table_path:
            reports = dict(context.get("generated_report_paths", {}))
            reports["citation_candidates"] = candidate_table_path
            context["generated_report_paths"] = reports
        context["confirmation_state"] = {"gate": None, "approved": True}

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(3)
        gate.set_context(context)
        context["phase3_result"] = {
            "candidates": len(candidates),
            "accepted": len([c for c in candidates if not c.is_rejected]),
            "if_passed": if_report.pass_count,
            "if_blocked": if_report.block_count,
        }
        unknown_candidates = [
            {
                "citekey": decision.citekey,
                "journal": decision.journal,
                "gate_type": decision.gate_type,
                "threshold": decision.threshold,
                "target_sentence": decision.target_sentence,
                "section": decision.section,
            }
            for decision in if_report.blocked
            if decision.result.value == "unknown"
        ]
        if unknown_candidates:
            context["if_unknown_review"] = {
                "candidates": unknown_candidates,
                "resolution": None,
            }
            context["confirmation_state"] = {
                "gate": "IF_UNKNOWN_REVIEW", "approved": False,
                "safety_interrupt": True,
            }
            gate.require_confirmation("IF_UNKNOWN_REVIEW")
            gate.set_context(context)
            return {
                "status": "waiting_confirmation",
                "phase": 3,
                "gate": "IF_UNKNOWN_REVIEW",
                "mode": context.get("mode", "A"),
                "entry": PRODUCTION_ENTRY_ID,
                "data": {
                    "reason": "IF_UNKNOWN_REVIEW_REQUIRED",
                    "unknown_candidates": unknown_candidates,
                },
                "outputs": {"dry_run": dry_run},
            }
        gate.set_context(context)
        return self._run_phase4(context, dry_run)

    def _run_phase4(self, context: dict, dry_run: bool) -> dict:
        """Generate floating suggestions from persisted Phase-3 candidates."""
        from floating_refs import FloatingRefHandler
        from phase_gate import WorkflowGate

        try:
            manuscript_text = self._context_manuscript_text(context)
            candidates = self._deserialize_candidates(context)
            handler = FloatingRefHandler()
            floaters = handler.identify_floating_references(candidates)

            report_path = None
            if not dry_run:
                os.makedirs(context["output_directory"], exist_ok=True)
                report_path = os.path.join(
                    context["output_directory"],
                    "Floating_Reference_Report.md",
                )
            handler.generate_report(floaters, report_path or "")
        except Exception as exc:
            return self._blocked(
                "PHASE_4_FAILED", {"error": str(exc)}, phase=4
            )

        expansions = [
            {
                "citekey": floater.paper.citekey,
                "approved_expansion": floater.expansion_with_markers(),
                "target_sentence": floater.suggested_expansion,
                "target_section": floater.suggested_section,
                "target_location": "section_end",
            }
            for floater in floaters
        ]
        context["floating_state"] = {
            "expansions": expansions,
            "applied": False,
        }
        context["working_manuscript_text"] = manuscript_text
        context["current_phase"] = 4
        reports = dict(context.get("generated_report_paths", {}))
        reports["floating_report"] = report_path
        context["generated_report_paths"] = reports

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(4)
        if expansions:
            floating_policy = context.get("floating_policy")
            if context.get("preflight_mode") and floating_policy != "ask":
                context["floating_confirmed"] = floating_policy == "expand"
                context["confirmation_state"] = {
                    "gate": "FLOATING_CONFIRM", "approved": True,
                    "internal": True,
                    "policy": floating_policy,
                }
                gate.set_context(context)
                return self._resume_phase4(context, dry_run)

            gate.require_confirmation("FLOATING_CONFIRM")
            context["confirmation_state"] = {
                "gate": "FLOATING_CONFIRM", "approved": False,
            }
            gate.set_context(context)
            return {
                "status": "waiting_confirmation",
                "phase": 4,
                "gate": "FLOATING_CONFIRM",
                "mode": context.get("mode", "A"),
                "entry": PRODUCTION_ENTRY_ID,
                "data": {
                    "floating_references": len(expansions),
                    "expansions": expansions,
                },
                "outputs": {
                    "floating_report": report_path,
                    "dry_run": dry_run,
                },
            }

        context["confirmation_state"] = {"gate": None, "approved": True}
        gate.set_context(context)
        return self._prepare_phase5(context, dry_run)

    def _resume_phase4(self, context: dict, dry_run: bool) -> dict:
        """Apply only the exact floating expansions persisted before approval."""
        from floating_refs import FloatingRefHandler

        floating_state = context.get("floating_state")
        if not isinstance(floating_state, dict):
            return self._blocked(
                "WORKFLOW_STATE_INCOMPLETE",
                {"missing": "floating_state"},
                phase=4,
            )
        try:
            manuscript_text = self._context_manuscript_text(context)
            output_path = None
            if context.get("floating_confirmed"):
                expansions = floating_state.get("expansions", [])
                if not expansions:
                    return self._blocked(
                        "WORKFLOW_STATE_INCOMPLETE",
                        {"missing": "floating_state.expansions"},
                        phase=4,
                    )
                if not dry_run:
                    output_path = os.path.join(
                        context["output_directory"], "floating_applied.md"
                    )
                handler = FloatingRefHandler()
                for expansion in expansions:
                    result = handler.apply_confirmed_expansion(
                        manuscript_text=manuscript_text,
                        approved_expansion=expansion["approved_expansion"],
                        target_section=expansion["target_section"],
                        target_location=expansion["target_location"],
                        output_path=output_path or "",
                    )
                    if result.get("status") != "completed":
                        return self._blocked(
                            "FLOATING_EXPANSION_APPLY_BLOCKED",
                            {
                                "citekey": expansion.get("citekey"),
                                "apply_result": result,
                            },
                            phase=4,
                        )
                    manuscript_text = result["manuscript"]
                candidate_items = context.get("candidate_state", {}).get(
                    "candidates", []
                )
                expansion_by_key = {
                    item["citekey"]: item for item in expansions
                }
                for candidate in candidate_items:
                    citekey = candidate.get("paper", {}).get("citekey")
                    approved = expansion_by_key.get(citekey)
                    if approved:
                        candidate["target_sentence"] = approved["target_sentence"]
                        candidate["section"] = approved["target_section"]
                        candidate["is_rejected"] = False
                        candidate["rejection_reason"] = ""
                        candidate["reason"] = "User-approved floating expansion"
                floating_state["applied"] = True
            else:
                floating_state["applied"] = False
                floating_state["skipped_by_user"] = True
        except Exception as exc:
            return self._blocked(
                "PHASE_4_FAILED", {"error": str(exc)}, phase=4
            )

        context["floating_state"] = floating_state
        context["working_manuscript_text"] = manuscript_text
        if output_path:
            context["working_markdown_path"] = output_path
        context["current_phase"] = 4
        return self._prepare_phase5(context, dry_run)

    def _prepare_phase5(self, context: dict, dry_run: bool) -> dict:
        """Persist the injection snapshot and require final write approval."""
        from phase_gate import WorkflowGate

        try:
            manuscript_text = self._context_manuscript_text(context)
        except Exception as exc:
            return self._blocked(
                "WORKFLOW_STATE_INCOMPLETE", {"error": str(exc)}, phase=5
            )
        context["pre_injection_snapshot"] = manuscript_text
        context["working_manuscript_text"] = manuscript_text
        context["current_phase"] = 5
        context["confirmation_state"] = {
            "gate": "INJECTION_CONFIRM", "approved": False,
        }

        if context.get("preflight_mode"):
            validations = dict(context.get("internal_validation_state", {}))
            validations["injection_preview"] = {
                "status": "completed",
                "path": context.get("generated_report_paths", {}).get(
                    "citation_candidates"
                ),
                "candidates": context.get("phase3_result", {}).get(
                    "candidates", 0
                ),
            }
            context["internal_validation_state"] = validations
            context["confirmation_state"] = {
                "gate": "INJECTION_CONFIRM", "approved": True,
                "internal": True,
            }
            gate = WorkflowGate(state_file=self._state_file)
            gate.set_context(context)
            return self._run_phase5(context, dry_run)

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(5)
        gate.require_confirmation("INJECTION_CONFIRM")
        gate.set_context(context)
        return {
            "status": "waiting_confirmation",
            "phase": 5,
            "gate": "INJECTION_CONFIRM",
            "mode": context.get("mode", "A"),
            "entry": PRODUCTION_ENTRY_ID,
            "data": {
                **context.get("phase3_result", {}),
                "floating": len(
                    context.get("floating_state", {}).get("expansions", [])
                ),
            },
            "outputs": {
                **context.get("generated_report_paths", {}),
                "dry_run": dry_run,
            },
        }

    def _run_phase5(self, context: dict, dry_run: bool) -> dict:
        """Inject the persisted semantic decisions through existing modules."""
        from candidate_adapter import adapt_semantic_candidates
        from citation_registry import CitationRegistry
        from crossref_guard import merge_adjacent_citations
        from file_guard import WriteGuard
        from injector import CitationInjector
        from phase_gate import WorkflowGate

        try:
            manuscript_text = self._context_manuscript_text(context)
            candidates = self._deserialize_candidates(context)
            plan = adapt_semantic_candidates(candidates, manuscript_text)
            registry = CitationRegistry()
            for _, match in plan:
                registry.register(match.citekey)
            injector = CitationInjector(registry)
            injector.set_document(manuscript_text)
            injected = injector.inject_candidates(plan, auto_confirm=True)
            failures = [
                item for item in injector.injection_log
                if item.get("action") in {"error", "skip_locked", "defer_table"}
            ]
            if failures:
                return self._blocked(
                    "CITATION_INJECTION_INCOMPLETE",
                    {"failures": failures},
                    phase=5,
                )
            injected = merge_adjacent_citations(injected)

            injected_path = None
            if not dry_run:
                injected_path = os.path.join(
                    context["output_directory"], "injected_manuscript.md"
                )
                guard = WriteGuard(workspace_root=context["output_directory"])
                guard.set_dry_run_completed()
                skipped_table_keys = {
                    item["citekey"] for item in injector.injection_log
                    if item.get("action") == "skip_unsafe_table"
                }
                expected_keys = {
                    match.citekey for _, match in plan
                    if match.citekey not in skipped_table_keys
                }
                guard.set_validator(lambda: all(
                    f"@{key}" in injected for key in expected_keys
                ))
                if not guard.validate():
                    return self._blocked(
                        "INJECTION_VALIDATION_FAILED",
                        {"expected_keys": sorted(expected_keys)},
                        phase=5,
                    )
                guard.safe_write(injected, injected_path)
        except Exception as exc:
            return self._blocked(
                "PHASE_5_FAILED", {"error": str(exc)}, phase=5
            )

        context["working_manuscript_text"] = injected
        if injected_path:
            context["working_markdown_path"] = injected_path
        context["injection_state"] = {
            "planned": len(plan),
            "injected_keys": registry.get_injected_keys(),
            "log": injector.injection_log,
        }
        reports = dict(context.get("generated_report_paths", {}))
        reports["injected_manuscript"] = injected_path
        context["generated_report_paths"] = reports
        context["current_phase"] = 5
        context["confirmation_state"] = {
            "gate": "INJECTION_CONFIRM", "approved": True,
        }

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(5)
        gate.set_context(context)
        return self._run_phase6(context, dry_run)

    def _run_phase6(self, context: dict, dry_run: bool) -> dict:
        """Resolve style settings and dispatch the existing DOCX exporter."""
        from docx_exporter import DocxExporter
        from phase_gate import WorkflowGate

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(6)
        context["current_phase"] = 6
        context["phase6_state"] = {
            "status": "running",
            "journal": context.get("journal"),
            "csl_path": context.get("csl_path"),
            "pandoc_path": context.get("pandoc_path"),
            "working_markdown_path": context.get("working_markdown_path"),
            "final_output_path": context.get("final_output_path"),
        }
        gate.set_context(context)
        if not context.get("journal") or context.get("all_authors") is None:
            gate.require_confirmation("EXPORT_CONFIRM")
            context["confirmation_state"] = {
                "gate": "EXPORT_CONFIRM", "approved": False,
            }
            gate.set_context(context)
            return {
                "status": "waiting_confirmation",
                "phase": 6,
                "gate": "EXPORT_CONFIRM",
                "mode": context.get("mode", "A"),
                "entry": PRODUCTION_ENTRY_ID,
                "data": {
                    "journal_required": not bool(context.get("journal")),
                    "all_authors_required": (
                        context.get("all_authors") is None
                    ),
                },
                "outputs": {
                    **context.get("generated_report_paths", {}),
                    "dry_run": dry_run,
                },
            }

        csl_path = context.get("csl_path")
        pandoc_path = context.get("pandoc_path")
        if csl_path and not os.path.isfile(csl_path):
            context["phase6_state"] = {
                **context["phase6_state"], "status": "blocked",
                "reason": "CSL_PATH_INVALID", "details": {"path": csl_path},
            }
            gate.set_context(context)
            return self._blocked(
                "CSL_PATH_INVALID", {"path": csl_path}, phase=6
            )
        if pandoc_path and not os.path.isfile(pandoc_path):
            context["phase6_state"] = {
                **context["phase6_state"], "status": "blocked",
                "reason": "PANDOC_PATH_INVALID", "details": {"path": pandoc_path},
            }
            gate.set_context(context)
            return self._blocked(
                "PANDOC_PATH_INVALID", {"path": pandoc_path}, phase=6
            )

        final_docx = None
        compile_command = []
        if not dry_run:
            working_path = context.get("working_markdown_path")
            if not working_path or not os.path.isfile(working_path):
                context["phase6_state"] = {
                    **context["phase6_state"], "status": "blocked",
                    "reason": "WORKFLOW_STATE_INCOMPLETE",
                    "details": {"missing": "injected working_markdown_path"},
                }
                gate.set_context(context)
                return self._blocked(
                    "WORKFLOW_STATE_INCOMPLETE",
                    {"missing": "injected working_markdown_path"},
                    phase=6,
                )
            exporter = DocxExporter(context["output_directory"])
            final_docx = exporter.export_manuscript(
                working_path,
                bibliography=context["bib_path"],
                csl=csl_path,
                journal=context["journal"],
                all_authors=bool(context["all_authors"]),
                output_path=context["final_output_path"],
                pandoc_path=pandoc_path,
            )
            compile_command = exporter.last_command
            if not final_docx:
                context["phase6_state"] = {
                    **context["phase6_state"], "status": "blocked",
                    "reason": "DOCX_EXPORT_FAILED",
                    "details": {
                        "journal": context["journal"],
                        "pandoc_path": pandoc_path,
                    },
                }
                gate.set_context(context)
                return self._blocked(
                    "DOCX_EXPORT_FAILED",
                    {
                        "journal": context["journal"],
                        "pandoc_path": pandoc_path,
                    },
                    phase=6,
                )

        reports = dict(context.get("generated_report_paths", {}))
        reports["final_docx"] = final_docx
        context["generated_report_paths"] = reports
        context["compile_state"] = {
            "command": compile_command,
            "journal": context["journal"],
            "all_authors": bool(context["all_authors"]),
            "csl": csl_path,
            "pandoc_path": pandoc_path,
        }
        context["phase6_state"] = {
            **context["phase6_state"], "status": "completed",
            "final_docx": final_docx,
        }
        context["confirmation_state"] = {
            "gate": "EXPORT_CONFIRM", "approved": True,
        }
        gate.set_context(context)
        return self._run_phase7(context, dry_run)

    def _run_phase7(self, context: dict, dry_run: bool) -> dict:
        """Generate mapping reports and return the complete output manifest."""
        from mapping_report import MappingReportGenerator
        from phase_gate import WorkflowGate

        original_text = context.get("pre_injection_snapshot")
        final_text = context.get("working_manuscript_text")
        if not isinstance(original_text, str) or not isinstance(final_text, str):
            return self._blocked(
                "WORKFLOW_STATE_INCOMPLETE",
                {"missing": "pre-injection or final manuscript snapshot"},
                phase=7,
            )
        try:
            generator = MappingReportGenerator()
            report = generator.generate(original_text, final_text)
            mapping_md = None
            mapping_csv = None
            if not dry_run:
                mapping_md = os.path.join(
                    context["output_directory"],
                    "CiteMatch_Mapping_Report.md",
                )
                mapping_csv = os.path.join(
                    context["output_directory"],
                    "CiteMatch_Mapping_Report.csv",
                )
                generator.save_markdown(report, mapping_md)
                generator.save_csv(report, mapping_csv)
        except Exception as exc:
            return self._blocked(
                "PHASE_7_FAILED", {"error": str(exc)}, phase=7
            )

        reports = dict(context.get("generated_report_paths", {}))
        reports["mapping_md"] = mapping_md
        reports["mapping_csv"] = mapping_csv
        context["generated_report_paths"] = reports
        context["mapping_state"] = {
            "missing_keys": report.missing_keys,
            "total_citations": report.total_citations,
            "new_citations": report.new_citations,
            "warnings": report.warnings,
        }
        context["current_phase"] = 7
        context["confirmation_state"] = {"gate": None, "approved": True}

        gate = WorkflowGate(state_file=self._state_file)
        gate.start_phase(7)
        gate.set_context(context)
        if report.missing_keys:
            return self._blocked(
                "MISSING_CITATION_KEYS",
                {
                    "missing_keys": report.missing_keys,
                    "mapping_md": mapping_md,
                    "mapping_csv": mapping_csv,
                },
                phase=7,
            )

        return {
            "status": "completed",
            "phase": 7,
            "mode": context.get("mode", "A"),
            "entry": PRODUCTION_ENTRY_ID,
            "data": context["mapping_state"],
            "outputs": {
                "references_summary": reports.get("references_summary"),
                "floating_report": reports.get("floating_report"),
                "injected_manuscript": reports.get("injected_manuscript"),
                "mapping_md": mapping_md,
                "mapping_csv": mapping_csv,
                "final_docx": reports.get("final_docx"),
                "dry_run": dry_run,
            },
        }

    @staticmethod
    def _deserialize_candidates(context: dict) -> list:
        from literature_intel import PaperIntel
        from semantic_mapper import CitationCandidate

        serialized = context.get("candidate_state", {}).get("candidates")
        if not isinstance(serialized, list):
            raise ValueError("candidate_state.candidates is missing")
        candidates = []
        for item in serialized:
            data = dict(item)
            paper_data = data.pop("paper", None)
            if not isinstance(paper_data, dict):
                raise ValueError("candidate paper state is invalid")
            candidates.append(
                CitationCandidate(paper=PaperIntel(**paper_data), **data)
            )
        return candidates

    @staticmethod
    def _context_manuscript_text(context: dict) -> str:
        persisted = context.get("working_manuscript_text")
        if isinstance(persisted, str):
            return persisted
        working_path = context.get("working_markdown_path")
        if not working_path or not os.path.isfile(working_path):
            raise ValueError("working manuscript is unavailable")
        with open(working_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _validate_environment_and_inputs(
        self, pandoc_path: Optional[str] = None,
    ) -> dict:
        if not self.validate_inputs():
            return self._blocked("INPUT_VALIDATION_FAILED", {"errors": self.errors})

        from bib_parser import BibTeXParser
        from environment_checker import EnvironmentChecker
        from zotero_workflow import ZoteroWorkflow

        zotero = ZoteroWorkflow(self._bib_path)
        if not zotero.is_valid:
            return self._blocked(
                "BIB_VALIDATION_FAILED", {"errors": list(zotero._errors)}
            )

        try:
            bib_entries = BibTeXParser().parse_file(self._bib_path)
        except Exception as exc:
            return self._blocked("BIB_PARSE_FAILED", {"error": str(exc)})
        if not bib_entries:
            return self._blocked("BIB_PARSE_FAILED", {"error": "0 BibTeX entries"})

        environment = EnvironmentChecker().check_all(
            self._bib_path, pandoc_path=pandoc_path
        )
        manuscript_ext = os.path.splitext(self._manuscript_path)[1].lower()
        if manuscript_ext == ".docx" and not environment["pandoc"]["available"]:
            return self._blocked(
                "PANDOC_REQUIRED",
                {"environment": environment, "input_type": manuscript_ext},
                phase=0,
            )

        return {
            "status": "completed",
            "phase": 0,
            "data": {
                "environment": environment,
                "bib_entries": len(bib_entries),
                "input_type": manuscript_ext,
            },
        }

    def _prepare_markdown(
        self, dry_run: bool, pandoc_path: Optional[str] = None,
    ) -> tuple[str, dict]:
        manuscript_ext = os.path.splitext(self._manuscript_path)[1].lower()
        if manuscript_ext == ".md":
            with open(self._manuscript_path, "r", encoding="utf-8") as handle:
                text = handle.read()
            return text, {
                "converted": False,
                "source_markdown": self._manuscript_path,
            }

        from pandoc_adapter import PandocAdapter

        adapter = PandocAdapter(pandoc_path=pandoc_path)
        if dry_run:
            text = adapter.convert_docx_to_markdown(self._manuscript_path)
            return text, {"converted": True, "source_markdown": None}

        os.makedirs(self._output_dir, exist_ok=True)
        markdown_path = os.path.join(self._output_dir, "draft.md")
        adapter.convert_docx_to_markdown(self._manuscript_path, markdown_path)
        with open(markdown_path, "r", encoding="utf-8") as handle:
            text = handle.read()
        return text, {"converted": True, "source_markdown": markdown_path}

    def _run_mode_c(
        self, markdown_text: str, conversion: dict, dry_run: bool
    ) -> dict:
        from legacy_migration import apply_migration, build_migration

        mapping_source = None
        try:
            if conversion.get("source_markdown"):
                mapping_source = conversion["source_markdown"]
            else:
                temp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", encoding="utf-8", delete=False
                )
                with temp:
                    temp.write(markdown_text)
                mapping_source = temp.name

            mapping, report = build_migration(mapping_source, self._bib_path)
        except Exception as exc:
            return self._blocked(
                "LEGACY_MAPPING_FAILED", {"error": str(exc)}, phase="MODE_C"
            )
        finally:
            if mapping_source and not conversion.get("source_markdown"):
                try:
                    os.unlink(mapping_source)
                except OSError:
                    pass

        mapping_issues = self._validate_legacy_mapping(mapping, report)
        if mapping_issues:
            return self._blocked(
                "LEGACY_MAPPING_UNSAFE",
                {
                    "mapping": self._mapping_summary(report),
                    "issues": mapping_issues,
                    "references_preserved": True,
                },
                phase="MODE_C",
            )

        cleaned_text, removal = self._remove_references_safely(markdown_text)
        if removal.get("status") == "blocked":
            return removal

        legacy_before = len(LEGACY_CITATION_RE.findall(cleaned_text))
        static_before = self._count_static_numeric_citations(cleaned_text)
        additional_numeric_before = max(0, static_before - legacy_before)
        migrated_text, migrated_count = apply_migration(cleaned_text, mapping)
        residual_superscript = len(LEGACY_CITATION_RE.findall(migrated_text))
        residual_numeric = self._count_static_numeric_citations(migrated_text)
        if (migrated_count != static_before or residual_superscript != 0 or
                residual_numeric != 0):
            return self._blocked(
                "LEGACY_MIGRATION_INCOMPLETE",
                {
                    "legacy_before": legacy_before,
                    "additional_numeric_before": additional_numeric_before,
                    "expected_total_migrations": static_before,
                    "migrated": migrated_count,
                    "residual_superscript": residual_superscript,
                    "residual_numeric": residual_numeric,
                    "references_preserved": True,
                },
                phase="MODE_C",
            )

        self._last_markdown = migrated_text
        used_pending = self._compute_used_pending(migrated_text)
        output_path = None
        if not dry_run:
            os.makedirs(self._output_dir, exist_ok=True)
            output_path = os.path.join(self._output_dir, "migrated.md")
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write(migrated_text)

        return {
            "status": "completed",
            "phase": "MODE_C",
            "mode": "C",
            "entry": PRODUCTION_ENTRY_ID,
            "data": {
                **conversion,
                "mapping": self._mapping_summary(report),
                "legacy_occurrences": legacy_before,
                "migrated_occurrences": legacy_before - residual_superscript,
                "legacy_numeric_occurrences": additional_numeric_before,
                "migrated_numeric_occurrences": (
                    additional_numeric_before - residual_numeric
                ),
                "total_legacy_occurrences": static_before,
                "total_migrated_occurrences": migrated_count,
                "residual_superscript": residual_superscript,
                "residual_numeric": residual_numeric,
                "references_removed": True,
                **used_pending,
            },
            "outputs": {"markdown": output_path, "dry_run": dry_run},
        }

    @staticmethod
    def _mapping_summary(report: dict) -> dict:
        return {
            "total": report.get("total", 0),
            "mapped": report.get("mapped", 0),
            "unmapped": report.get("unmapped_count", 0),
            "ambiguous": report.get("ambiguous_count", 0),
            "unsafe": report.get("unsafe_count", 0),
            "mapping_pct": report.get("mapping_pct", 0.0),
        }

    @staticmethod
    def _validate_legacy_mapping(mapping: dict, report: dict) -> list[dict]:
        issues = []
        total = report.get("total", 0)
        if total == 0:
            issues.append({"type": "no_references", "numbers": []})
        if report.get("unmapped_count", 0):
            issues.append({
                "type": "unmapped",
                "references": report.get("unmapped_list", []),
            })
        for detail in report.get("ambiguous_list", []):
            issues.append({
                "type": "ambiguous",
                "number": detail.get("num"),
                "reference": detail.get("raw", ""),
                "candidates": detail.get("candidate_details", []),
            })
        for detail in report.get("unsafe_list", []):
            issues.append({
                "type": "unsafe",
                "number": detail.get("num"),
                "reference": detail.get("raw", ""),
                "reason": detail.get("decision_reason", ""),
                "candidates": detail.get("candidate_details", []),
            })

        verified_many_to_one = {
            (item.get("citekey"), tuple(item.get("numbers", [])))
            for item in report.get("many_to_one_list", [])
            if item.get("verified_duplicate")
        }

        key_to_numbers: dict[str, list[str]] = {}
        for number, key in mapping.items():
            key_to_numbers.setdefault(key, []).append(str(number))
        for key, numbers in key_to_numbers.items():
            if len(numbers) > 1:
                ordered_numbers = sorted(numbers, key=int)
                if (key, tuple(ordered_numbers)) in verified_many_to_one:
                    continue
                issues.append({
                    "type": "duplicate_candidate",
                    "citekey": key,
                    "numbers": ordered_numbers,
                })
        if len(mapping) != total and not any(
                issue["type"] in {"unmapped", "ambiguous", "unsafe"}
                for issue in issues):
            issues.append({
                "type": "mapping_incomplete",
                "mapped": len(mapping),
                "total": total,
            })
        return issues

    @staticmethod
    def _remove_references_safely(text: str) -> tuple[str, dict]:
        from md_ast import MarkdownAST

        headings = list(REFERENCE_HEADING_RE.finditer(text))
        if not headings:
            return text, {
                "status": "blocked",
                "phase": "MODE_C",
                "reason": "REFERENCE_HEADING_NOT_FOUND",
                "details": {"references_preserved": True},
                "entry": PRODUCTION_ENTRY_ID,
            }
        heading = headings[-1]
        ast = MarkdownAST(text)
        ast.parse()
        ref_range = ast.find_reference_list()
        if ref_range is None:
            return text, {
                "status": "blocked",
                "phase": "MODE_C",
                "reason": "REFERENCE_LIST_NOT_FOUND",
                "details": {"references_preserved": True},
                "entry": PRODUCTION_ENTRY_ID,
            }
        heading_line = text[:heading.start()].count("\n")
        if ref_range[0] <= heading_line:
            return text, {
                "status": "blocked",
                "phase": "MODE_C",
                "reason": "REFERENCE_BOUNDARY_UNSAFE",
                "details": {
                    "heading_line": heading_line + 1,
                    "reference_line": ref_range[0] + 1,
                    "references_preserved": True,
                },
                "entry": PRODUCTION_ENTRY_ID,
            }
        return text[:heading.start()].rstrip() + "\n", {
            "status": "completed",
            "heading_line": heading_line + 1,
        }

    @staticmethod
    def _count_static_numeric_citations(text: str) -> int:
        from md_ast import MarkdownAST

        ast = MarkdownAST(text)
        ast.parse()
        return len(ast.find_static_citations())

    def _compute_used_pending(self, text: str) -> dict:
        from bib_parser import BibTeXParser
        from md_ast import MarkdownAST

        bib_entries = BibTeXParser().parse_file(self._bib_path)
        ast = MarkdownAST(text)
        ast.parse()
        used = set()
        for citation in ast.find_existing_pandoc_citations():
            for key in re.findall(r"@([A-Za-z0-9_:-]+)", citation.raw_text):
                if not key.lower().startswith(("fig:", "tbl:", "eq:", "sec:")):
                    used.add(key)
        all_keys = set(bib_entries)
        pending = all_keys - used
        return {
            "used_references": len(used),
            "pending_references": len(pending),
            "used_keys": sorted(used),
            "pending_keys": sorted(pending),
        }

    @staticmethod
    def _blocked(reason: str, details: dict, phase=None) -> dict:
        return {
            "status": "blocked",
            "phase": phase,
            "reason": reason,
            "details": details,
            "entry": PRODUCTION_ENTRY_ID,
        }

    def run_migration(self, dry_run: bool = True) -> dict:
        """Backward-compatible citation-migrator API.

        Production callers must use :meth:`run`; this method remains for the
        existing v2.4 test/API surface until its separate deprecation cycle.
        """
        if not self.validate_inputs():
            return {"success": False, "errors": self._errors}

        try:
            from citation_migrator import build_mapping_from_manuscript, CitationMigrator
            from bib_parser import BibTeXParser

            parser = BibTeXParser()
            bib = parser.parse_file(self._bib_path)

            with open(self._manuscript_path, "r", encoding="utf-8") as f:
                text = f.read()

            num_to_key = build_mapping_from_manuscript(text, bib)
            migrator = CitationMigrator(num_to_key)
            migrated, report = migrator.migrate_all(text)

            result = {
                "success": True,
                "migrated_count": report.total_migrated,
                "coverage": {
                    "body": f"{report.body_migrated}/{report.body_citations}",
                    "figure": f"{report.figure_migrated}/{report.figure_citations}",
                    "table": f"{report.table_migrated}/{report.table_citations}",
                },
                "dry_run": dry_run,
            }

            # Issue #1: persist migrated manuscript when not dry_run
            if not dry_run:
                os.makedirs(self._output_dir, exist_ok=True)
                output_path = os.path.join(self._output_dir, "migrated.md")
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(migrated)
                result["output_markdown"] = output_path

            return result
        except Exception as e:
            return {"success": False, "errors": [str(e)]}

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    @property
    def last_markdown(self) -> str:
        return self._last_markdown


def main() -> int:
    p = argparse.ArgumentParser(description="CiteMatch Production Entry")
    p.add_argument("manuscript", help="Path to manuscript (.md or .docx)")
    p.add_argument("bib", help="Path to Better BibTeX .bib file")
    p.add_argument("--output", help="Output directory")
    p.add_argument("--mode", choices=["A", "B", "C"], default="A")
    p.add_argument("--phase", type=int, help="Standalone Mode B phase")
    p.add_argument("--write", action="store_true",
                   help="Write outputs; default is dry-run")
    p.add_argument(
        "--preflight", action="store_true",
        help="Run Phase 00-7 from one complete preflight configuration",
    )
    p.add_argument("--confirm", help="Approve a pending gate")
    p.add_argument("--body-if", help="Body IF threshold or 'disable'")
    p.add_argument("--table-if", help="Table IF threshold or 'disable'")
    p.add_argument(
        "--profile",
        help="Existing policy profile name; defaults explicitly to 'default'",
    )
    p.add_argument(
        "--preflight-info", action="store_true",
        help="Return profile-owned Preflight recommendations without running",
    )
    p.add_argument("--journal", help="Journal name for CSL resolution")
    p.add_argument("--all-authors", choices=["yes", "no"])
    p.add_argument("--floating", choices=["yes", "no"])
    p.add_argument("--if-unknown", choices=["approve", "exclude"])
    p.add_argument("--floating-policy", choices=["keep", "ask", "expand"])
    p.add_argument("--csl", help="Existing CSL file path")
    p.add_argument("--pandoc-path", help="Explicit Pandoc executable path")
    args = p.parse_args()

    wf = ManuscriptWorkflow(args.manuscript, args.bib, args.output)
    if args.preflight_info:
        validation = wf._validate_environment_and_inputs(
            pandoc_path=args.pandoc_path
        )
        if validation["status"] == "blocked":
            result = validation
        else:
            try:
                _text, conversion = wf._prepare_markdown(
                    dry_run=True, pandoc_path=args.pandoc_path
                )
            except Exception as exc:
                result = wf._blocked(
                    "INPUT_PREPARATION_FAILED", {"error": str(exc)}
                )
            else:
                result = {
                    "status": "completed",
                    "phase": "PREFLIGHT",
                    "entry": PRODUCTION_ENTRY_ID,
                    "data": {
                        **wf.get_preflight_defaults(args.profile),
                        "phase0": validation["data"],
                        "input_preparation": conversion,
                    },
                }
    elif args.preflight:
        result = wf.run(
            mode="A",
            dry_run=not args.write,
            runtime_config={
                "body_if": args.body_if,
                "table_if": args.table_if,
                "journal": args.journal,
                "all_authors": args.all_authors,
                "floating_policy": args.floating_policy,
                "profile": args.profile,
                "csl_path": args.csl,
                "pandoc_path": args.pandoc_path,
            },
        )
    elif args.confirm:
        result = wf.confirm(
            args.confirm,
            body_if=args.body_if,
            table_if=args.table_if,
            journal=args.journal,
            all_authors=args.all_authors,
            floating=args.floating,
            if_unknown=args.if_unknown,
            csl_path=args.csl,
            pandoc_path=args.pandoc_path,
            dry_run=not args.write,
        )
    else:
        result = wf.run(
            mode=args.mode, phase=args.phase, dry_run=not args.write
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
