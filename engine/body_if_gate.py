"""
CiteMatch v2.2.3 — Body Citation IF Gate

Pipeline position:
  Literature Intelligence → Semantic Matching → IF Validation → Injection

Enforces journal quality confirmation before any new body citation injection.

Rules:
  - IF >= threshold: allow injection (ELITE_PASS or GLOBAL_PASS)
  - IF <  threshold: route to Floating_Reference_Report (BELOW_THRESHOLD)
  - IF unavailable:   require manual confirmation (UNKNOWN)
  - Table citations:  stricter threshold (IF_THRESHOLD_ELITE)
  - Review papers:    Introduction only (unchanged from semantic_mapper)
  - Figure captions:  forbidden for new injection (unchanged)
  - Abstract:         forbidden (unchanged)
"""
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class IFGateResult(Enum):
    ELITE_PASS = "elite_pass"        # IF >= elite threshold (tables)
    GLOBAL_PASS = "global_pass"      # IF >= global threshold (body)
    NOT_APPLIED = "not_applied"      # the relevant IF policy is disabled
    BELOW_THRESHOLD = "below"        # IF < threshold → floating
    UNKNOWN = "unknown"              # IF unavailable → manual confirm
    REJECTED_ZONE = "rejected_zone"  # Abstract/fig caption/this-work


@dataclass
class IFGateDecision:
    """Single paper IF gate decision"""
    citekey: str
    journal: str
    impact_factor: float
    threshold: float
    gate_type: str          # "body" / "table" / "review"
    result: IFGateResult
    reason: str = ""
    target_sentence: str = ""
    section: str = ""

    def to_row(self) -> str:
        status = {
            IFGateResult.ELITE_PASS: 'ELITE_PASS',
            IFGateResult.GLOBAL_PASS: 'GLOBAL_PASS',
            IFGateResult.NOT_APPLIED: 'IF_NOT_APPLIED',
            IFGateResult.BELOW_THRESHOLD: 'BELOW_THRESHOLD',
            IFGateResult.UNKNOWN: 'UNKNOWN',
            IFGateResult.REJECTED_ZONE: 'REJECTED_ZONE',
        }.get(self.result, '?')
        return (
            f'| @{self.citekey} | {self.journal[:30]} | {self.impact_factor:.1f} | '
            f'{self.gate_type} | {status} | {self.reason[:50]} |'
        )


@dataclass
class IFGateReport:
    """IF gate validation report for all candidates"""
    threshold_global: float
    threshold_elite: float
    decisions: list[IFGateDecision] = field(default_factory=list)
    user_threshold: Optional[float] = None
    user_confirmed: bool = False

    @property
    def passed(self) -> list[IFGateDecision]:
        return [d for d in self.decisions
                if d.result in (
                    IFGateResult.ELITE_PASS,
                    IFGateResult.GLOBAL_PASS,
                    IFGateResult.NOT_APPLIED,
                )]

    @property
    def blocked(self) -> list[IFGateDecision]:
        return [d for d in self.decisions
                if d.result in (IFGateResult.BELOW_THRESHOLD, IFGateResult.UNKNOWN)]

    @property
    def rejected_zones(self) -> list[IFGateDecision]:
        return [d for d in self.decisions if d.result == IFGateResult.REJECTED_ZONE]

    @property
    def pass_count(self) -> int:
        return len(self.passed)

    @property
    def block_count(self) -> int:
        return len(self.blocked)

    def summary_table(self) -> str:
        lines = [
            '# CiteMatch v2.2.3 — IF Gate Validation Report',
            '',
            f'**User threshold**: IF > {self.user_threshold or "not set"}',
            f'**Elite threshold (tables)**: IF > {self.threshold_elite}',
            f'**Global threshold (body)**: IF > {self.threshold_global}',
            f'**User confirmed**: {self.user_confirmed}',
            '',
            '| CiteKey | Journal | IF | Gate | Result | Reason |',
            '|---------|---------|----|------|--------|--------|',
        ]
        for d in self.decisions:
            lines.append(d.to_row())
        lines.append('')
        lines.append(f'**Passed**: {self.pass_count} | **Blocked**: {self.block_count} | **Rejected Zone**: {len(self.rejected_zones)}')
        return '\n'.join(lines)


class BodyCitationIFGate:
    """IF validation gate between semantic matching and injection

    Usage:
        gate = BodyCitationIFGate()
        gate.set_user_threshold(6.0)  # from user input
        report = gate.validate_candidates(candidates, journal_if_map)
        if report.block_count > 0:
            # route blocked to Floating_Reference_Report
    """

    # Default thresholds — None means "disabled" (safe fallback).
    # When Policy Manager is unavailable, IF filtering is OFF.
    # No manuscript-specific threshold should activate silently.
    DEFAULT_GLOBAL_THRESHOLD = None
    DEFAULT_ELITE_THRESHOLD = None

    @staticmethod
    def _get_default_global() -> float:
        try:
            from policy_manager import get_policy
            t = get_policy().body_if_threshold
            return float(t) if t > 0 else 0.0
        except Exception:
            return 0.0

    @staticmethod
    def _get_default_elite() -> float:
        try:
            from policy_manager import get_policy
            t = get_policy().table_if_threshold
            return float(t) if t > 0 else 0.0
        except Exception:
            return 0.0

    # Journal IF database — loaded from YAML, with hardcoded fallback
    # for backward compatibility when YAML is unavailable.
    JOURNAL_IF_MAP: dict[str, float] = {}

    @classmethod
    def _load_journal_if_map(cls) -> dict[str, float]:
        """Load journal IF from YAML, fall back to empty dict"""
        try:
            from policy_manager import get_policy
            db = get_policy().load_journal_if_database()
            if db:
                return db
        except Exception:
            pass
        return {}

    @classmethod
    def _load_journal_aliases(cls) -> dict[str, str]:
        """Load explicit aliases owned by the canonical IF database."""
        try:
            from policy_manager import get_policy
            return get_policy().load_journal_aliases()
        except Exception:
            return {}

    def __init__(self):
        self._global_threshold = self._get_default_global()
        self._elite_threshold = self._get_default_elite()
        self._user_threshold: Optional[float] = None
        self._user_confirmed: bool = False
        self._if_disabled: bool = False
        self._body_if_enabled = self._get_default_body_enabled()
        self._table_if_enabled = self._get_default_table_enabled()
        self._custom_if_map: dict[str, float] = {}
        self._policy_available: bool = True

        # Safe fallback: if Policy Manager unavailable, disable IF filtering
        try:
            from policy_manager import get_policy
            get_policy()
        except Exception:
            self._policy_available = False
            self._if_disabled = True
            self._body_if_enabled = False
            self._table_if_enabled = False
            self._global_threshold = 0.0
            self._elite_threshold = 0.0

    def fallback_warning(self) -> str:
        """Emit warning when running in unrestricted (no-policy) mode"""
        if not self._policy_available:
            return (
                "IF policy unavailable. Running in unrestricted mode. "
                "No papers will be rejected by IF gate."
            )
        return ""

    @staticmethod
    def _get_default_body_enabled() -> bool:
        try:
            from policy_manager import get_policy
            policy = get_policy()
            return bool(policy.body_if_enabled and policy.body_if_threshold > 0)
        except Exception:
            return False

    @staticmethod
    def _get_default_table_enabled() -> bool:
        try:
            from policy_manager import get_policy
            policy = get_policy()
            return bool(policy.table_if_enabled and policy.table_if_threshold > 0)
        except Exception:
            return False

    # ---- User Confirmation (v2.3.2) ----

    def confirmation_prompt(self) -> str:
        """Generate the interactive IF gate confirmation prompt"""
        try:
            from policy_manager import get_policy
            pm = get_policy()
            profile = pm.profile_name
            body_default = pm.body_if_threshold
            table_default = pm.table_if_threshold
            body_confirm = pm.body_if_require_confirmation
            table_confirm = pm.table_if_require_confirmation
        except Exception:
            profile = "unknown"
            body_default = self._global_threshold
            table_default = self._elite_threshold
            body_confirm = True
            table_confirm = True

        lines = [
            f'Current profile: {profile}',
            '',
            'Recommended quality thresholds:',
            '',
            f'  Body citations:  IF > {body_default:.0f}  (require confirmation: {body_confirm})',
            f'  Table citations: IF > {table_default:.0f}  (require confirmation: {table_confirm})',
            '',
            'Options:',
            '  accept  — use recommended defaults',
            '  body=N  — customize body threshold (e.g. body=8)',
            '  table=N — customize table threshold (e.g. table=15)',
            '  disable — disable IF filtering',
        ]
        return '\n'.join(lines)

    def apply_runtime_policy(
        self,
        body_threshold: Optional[float] = None,
        table_threshold: Optional[float] = None,
        disable_if: bool = False,
        body_if_enabled: Optional[bool] = None,
        table_if_enabled: Optional[bool] = None,
    ) -> None:
        """Apply runtime override without modifying YAML profile.

        Args:
            body_threshold: override body IF threshold (None = use default)
            table_threshold: override table IF threshold (None = use default)
            disable_if: legacy compatibility switch that disables all IF filtering
            body_if_enabled: independently enable/disable body IF filtering
            table_if_enabled: independently enable/disable table IF filtering
        """
        if disable_if:
            self._if_disabled = True
            self._body_if_enabled = False
            self._table_if_enabled = False
            self._global_threshold = 0.0
            self._elite_threshold = 0.0
            self._user_confirmed = True
            return

        self._if_disabled = False
        if body_if_enabled is not None:
            self._body_if_enabled = bool(body_if_enabled)
        elif body_threshold is not None:
            self._body_if_enabled = True
        if table_if_enabled is not None:
            self._table_if_enabled = bool(table_if_enabled)
        elif table_threshold is not None:
            self._table_if_enabled = True

        if body_threshold is not None:
            self._user_threshold = body_threshold
            self._global_threshold = max(body_threshold, 0.0)

        if table_threshold is not None:
            self._elite_threshold = max(table_threshold, 0.0)

        self._user_confirmed = True

    # ---- Legacy User Interaction (backward compat) ----

    def set_user_threshold(self, threshold: Optional[float]) -> None:
        """Set user-specified IF threshold (legacy API).

        Args:
            threshold: minimum IF (e.g. 6.0), or None for no restriction
        """
        self._user_threshold = threshold
        if threshold is not None:
            self._global_threshold = max(threshold, 0.0)
            self._body_if_enabled = True
        self._user_confirmed = True

    def confirm(self) -> None:
        """Mark user confirmation as complete"""
        self._user_confirmed = True

    @property
    def is_confirmed(self) -> bool:
        return self._user_confirmed

    @property
    def effective_threshold(self) -> float:
        if self._user_threshold is not None:
            return self._user_threshold
        return self._global_threshold

    def user_prompt(self) -> str:
        """Generate the user confirmation prompt"""
        return (
            'Please specify minimum journal quality requirement '
            'for new body citations:\n'
            '  IF>5   — moderate threshold\n'
            '  IF>10  — high-impact only\n'
            '  Q1     — top quartile journals\n'
            '  none   — no restriction\n'
            f'\nCurrent default: IF > {self._global_threshold:.0f}'
        )

    def add_custom_if(self, journal: str, impact_factor: float) -> None:
        """Add custom journal IF to the lookup map"""
        self._custom_if_map[journal.lower().strip()] = impact_factor

    # ---- Validation ----

    def validate_candidates(
        self,
        candidates: list,
        extra_if_map: Optional[dict[str, float]] = None,
    ) -> IFGateReport:
        """Validate all candidates against IF gate

        Args:
            candidates: list of CitationCandidate from SemanticMapper
            extra_if_map: additional journal IF data

        Returns:
            IFGateReport with per-paper decisions
        """
        # If IF filtering is disabled, pass all candidates
        if self._if_disabled:
            report = IFGateReport(
                threshold_global=0.0, threshold_elite=0.0,
                user_threshold=None, user_confirmed=True,
            )
            for c in candidates:
                report.decisions.append(IFGateDecision(
                    citekey=c.paper.citekey, journal=c.paper.journal or 'Unknown',
                    impact_factor=0.0, threshold=0.0, gate_type='body',
                    result=IFGateResult.GLOBAL_PASS,
                    reason='IF filtering disabled by user',
                    target_sentence=c.target_sentence, section=c.section,
                ))
            return report

        report = IFGateReport(
            threshold_global=self._global_threshold,
            threshold_elite=self._elite_threshold,
            user_threshold=self._user_threshold,
            user_confirmed=self._user_confirmed,
        )

        # Merge IF maps: YAML database → custom overrides → extra map
        if_map = self._load_journal_if_map()
        if not if_map:
            if_map = dict(self.JOURNAL_IF_MAP)  # backward compat fallback
        if_map.update(self._custom_if_map)
        if extra_if_map:
            if_map.update({k.lower().strip(): v for k, v in extra_if_map.items()})

        for c in candidates:
            decision = self._decide_one(c, if_map)
            report.decisions.append(decision)

            # Below-threshold candidates are routed away from their current
            # target. UNKNOWN candidates remain unchanged until the Workflow
            # returns its explicit safety interrupt.
            if decision.result in (IFGateResult.BELOW_THRESHOLD,):
                if not c.is_rejected:
                    c.is_rejected = True
                    c.rejection_reason = (
                        f'IF GATE: {decision.journal} IF={decision.impact_factor:.1f} '
                        f'< threshold {decision.threshold:.0f}'
                    )

        return report

    # ---- Internal ----

    def _decide_one(self, candidate, if_map: dict) -> IFGateDecision:
        """Make IF gate decision for one candidate"""
        paper = candidate.paper
        journal = paper.journal or 'Unknown'
        citekey = paper.citekey

        # Already rejected by semantic mapper → pass through as rejected zone
        if candidate.is_rejected and 'FLOATING' in candidate.rejection_reason:
            return IFGateDecision(
                citekey=citekey, journal=journal, impact_factor=0.0,
                threshold=self._global_threshold,
                gate_type='body', result=IFGateResult.REJECTED_ZONE,
                reason=candidate.rejection_reason,
                target_sentence=candidate.target_sentence,
                section=candidate.section,
            )

        # Resolve IF
        impact_factor = self._resolve_if(journal, if_map)

        # Determine gate type
        is_table = '|' in candidate.target_sentence and candidate.target_sentence.count('|') >= 2
        is_review = paper.paper_type == 'review'
        gate_type = 'table' if is_table else ('review' if is_review else 'body')

        # Unknown IF
        if is_table and not self._table_if_enabled:
            return IFGateDecision(
                citekey=citekey, journal=journal, impact_factor=impact_factor,
                threshold=0.0, gate_type=gate_type, result=IFGateResult.NOT_APPLIED,
                reason='Table IF filtering disabled by user',
                target_sentence=candidate.target_sentence, section=candidate.section,
            )
        if not is_table and not self._body_if_enabled:
            return IFGateDecision(
                citekey=citekey, journal=journal, impact_factor=impact_factor,
                threshold=0.0, gate_type=gate_type, result=IFGateResult.NOT_APPLIED,
                reason='Body IF filtering disabled by user',
                target_sentence=candidate.target_sentence, section=candidate.section,
            )

        if impact_factor <= 0:
            return IFGateDecision(
                citekey=citekey, journal=journal, impact_factor=0.0,
                threshold=self._global_threshold,
                gate_type=gate_type, result=IFGateResult.UNKNOWN,
                reason=f'IF unavailable for "{journal}" — manual confirmation required',
                target_sentence=candidate.target_sentence,
                section=candidate.section,
            )

        # Elite threshold for tables
        if is_table:
            if impact_factor >= self._elite_threshold:
                result = IFGateResult.ELITE_PASS
                reason = f'IF {impact_factor:.1f} >= {self._elite_threshold} (elite)'
            else:
                result = IFGateResult.BELOW_THRESHOLD
                reason = f'IF {impact_factor:.1f} < {self._elite_threshold} (elite table gate)'
            threshold = self._elite_threshold
        else:
            # Body threshold
            if impact_factor >= self._global_threshold:
                result = IFGateResult.GLOBAL_PASS
                reason = f'IF {impact_factor:.1f} >= {self._global_threshold} (global)'
            else:
                result = IFGateResult.BELOW_THRESHOLD
                reason = f'IF {impact_factor:.1f} < {self._global_threshold} (global gate)'
            threshold = self._global_threshold

        return IFGateDecision(
            citekey=citekey, journal=journal, impact_factor=impact_factor,
            threshold=threshold, gate_type=gate_type, result=result,
            reason=reason,
            target_sentence=candidate.target_sentence,
            section=candidate.section,
        )

    @staticmethod
    def _resolve_if(journal: str, if_map: dict) -> float:
        """Resolve journal impact factor from lookup map"""
        if not journal:
            return 0.0

        def normalize(value: str) -> str:
            # Formatting normalization only.  Semantic expansions remain in
            # the reviewed explicit alias map below.
            return value.lower().strip().replace('.', '').replace(',', '').replace(' ', '')

        j_norm = normalize(journal)

        # Explicit aliases are resolved before lookup.  An alias is only
        # usable when its canonical target is actually present in the IF map;
        # otherwise the decision stays UNKNOWN rather than inventing an IF.
        aliases = BodyCitationIFGate._load_journal_aliases()
        for alias, canonical in aliases.items():
            if normalize(alias) == j_norm and canonical in if_map:
                return if_map[canonical]

        # Exact match
        for j_name, j_if in if_map.items():
            if normalize(j_name) == j_norm:
                return j_if

        # Prefix match (first 20 chars)
        for j_name, j_if in if_map.items():
            short_name = normalize(j_name)[:20]
            if j_norm[:20] == short_name:
                return j_if

        return 0.0
