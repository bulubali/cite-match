"""
CiteMatch v2.3 — Policy Manager

Loads, validates, and exposes citation policy profiles.
Replaces hardcoded constants across all engine modules.

Usage:
    from policy_manager import PolicyManager

    pm = PolicyManager()
    pm.load_profile("advanced_materials_review")
    threshold = pm.get_rule("if_gate.body.threshold")  # → 6
"""
import os
import yaml
from typing import Any, Optional

# Default profile directory relative to this file
DEFAULT_PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles"
)


class PolicyError(Exception):
    """Policy loading or validation error"""
    pass


class PolicyManager:
    """Singleton policy manager — loads YAML profiles and exposes rules"""

    _instance: Optional["PolicyManager"] = None

    def __init__(self):
        self._profile: dict = {}
        self._profile_name: str = ""
        self._profiles_dir: str = DEFAULT_PROFILES_DIR

    # ---- Singleton ----

    @classmethod
    def instance(cls) -> "PolicyManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)"""
        cls._instance = None

    # ---- Profile Loading ----

    def load_profile(self, name: str, profiles_dir: Optional[str] = None) -> dict:
        """Load a named profile from YAML file

        Args:
            name: profile name (without .yaml), e.g. "advanced_materials_review"
            profiles_dir: override profiles directory

        Returns:
            loaded profile dict
        """
        if profiles_dir:
            self._profiles_dir = profiles_dir

        path = os.path.join(self._profiles_dir, f"{name}.yaml")
        if not os.path.exists(path):
            # Safe fallback: try default.yaml
            default_path = os.path.join(self._profiles_dir, "default.yaml")
            if os.path.exists(default_path) and name != "default":
                return self.load_profile("default", profiles_dir)
            raise PolicyError(f"Profile not found: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self._profile = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            # Safe fallback: corrupted YAML → default
            default_path = os.path.join(self._profiles_dir, "default.yaml")
            if os.path.exists(default_path) and name != "default":
                return self.load_profile("default", profiles_dir)
            raise PolicyError(f"YAML parse error in {path}: {e}")

        self._profile_name = name
        try:
            self._validate()
        except PolicyError:
            # Schema validation failed → fallback to default
            if name != "default":
                return self.load_profile("default", profiles_dir)
            raise
        return self._profile

    def load_profile_dict(self, data: dict, name: str = "inline") -> dict:
        """Load profile from a dict (for testing)"""
        self._profile = data
        self._profile_name = name
        self._validate()
        return self._profile

    def resolve_profile(self, name: Optional[str] = None) -> dict:
        """Load one explicit runtime profile and expose its IF recommendations.

        An omitted profile intentionally resolves to the existing ``default``
        profile.  Callers receive only values owned by the loaded policy; no
        presentation layer needs to copy profile thresholds.
        """
        self.load_profile(str(name or "default").strip() or "default")
        return {
            "profile_name": self.profile_name,
            "recommended_body_if": self.body_if_threshold,
            "recommended_table_if": self.table_if_threshold,
            "body_if_enabled": self.body_if_enabled,
            "table_if_enabled": self.table_if_enabled,
        }

    # ---- Rule Access ----

    def get_rule(self, path: str, default: Any = None) -> Any:
        """Get a rule by dot-separated path

        Examples:
            pm.get_rule("if_gate.body.threshold") → 6
            pm.get_rule("density.sentence.max") → 3
            pm.get_rule("zones.abstract.new_citation") → False
        """
        keys = path.split('.')
        value = self._profile
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def get_section_keywords(self, section_type: str) -> list[str]:
        """Get section classification keywords"""
        return self.get_rule(f"sections.{section_type}_keywords", [])

    def get_contribution_routing(self, contrib_type: str) -> list[str]:
        """Get contribution routing keywords"""
        return self.get_rule(f"contribution_routing.{contrib_type}", [])

    def get_zone_rules(self, zone: str) -> dict:
        """Get all rules for a zone"""
        return self.get_rule(f"zones.{zone}", {})

    # ---- Convenience Accessors ----

    @property
    def body_if_enabled(self) -> bool:
        return self.get_rule("if_gate.body.enabled", False)

    @property
    def body_if_threshold(self) -> float:
        return float(self.get_rule("if_gate.body.default_threshold",
                    self.get_rule("if_gate.body.threshold", 0)))  # backward compat

    @property
    def body_if_require_confirmation(self) -> bool:
        return self.get_rule("if_gate.body.require_confirmation", False)

    @property
    def table_if_enabled(self) -> bool:
        return self.get_rule("if_gate.table.enabled", False)

    @property
    def table_if_threshold(self) -> float:
        return float(self.get_rule("if_gate.table.default_threshold",
                    self.get_rule("if_gate.table.threshold", 0)))  # backward compat

    @property
    def table_if_require_confirmation(self) -> bool:
        return self.get_rule("if_gate.table.require_confirmation", False)

    @property
    def review_intro_only(self) -> bool:
        return self.get_rule("review_paper.introduction_only", False)

    @property
    def review_forbidden_quantitative(self) -> bool:
        return self.get_rule("review_paper.forbidden_in_quantitative_claims", False)

    @property
    def review_forbidden_results(self) -> bool:
        return self.get_rule("review_paper.forbidden_in_results", False)

    @property
    def sentence_max_citations(self) -> int:
        return int(self.get_rule("density.sentence.max", 5))

    @property
    def paragraph_normal_max(self) -> int:
        return int(self.get_rule("density.paragraph.normal_max", 12))

    @property
    def paragraph_review_max(self) -> int:
        return int(self.get_rule("density.paragraph.review_max", 18))

    @property
    def abstract_new_citation(self) -> bool:
        return self.get_rule("zones.abstract.new_citation", False)

    @property
    def figure_migrate_existing(self) -> bool:
        return self.get_rule("zones.figure_caption.migrate_existing", True)

    @property
    def figure_allow_new(self) -> bool:
        return self.get_rule("zones.figure_caption.allow_new_injection", False)

    @property
    def min_similarity(self) -> float:
        return float(self.get_rule("semantic.min_similarity_threshold", 0.15))

    @property
    def rejected_sections(self) -> list[str]:
        return self.get_rule("semantic.rejected_sections", ["abstract"])

    @property
    def this_work_patterns(self) -> list[str]:
        return self.get_rule("semantic.this_work_patterns", ["this work", "we propose"])

    @property
    def quantitative_patterns(self) -> list[str]:
        return self.get_rule("sections.quantitative_claim_patterns", [])

    @property
    def profile_name(self) -> str:
        return self._profile_name

    # ---- Validation ----

    def _validate(self) -> None:
        """Validate profile has required sections"""
        required = ["profile", "if_gate", "review_paper", "density", "zones", "semantic"]
        for section in required:
            if section not in self._profile:
                raise PolicyError(
                    f"Profile '{self._profile_name}' missing required section: '{section}'"
                )

    # ---- Section Classifier ----

    def load_section_classifier(self, path: Optional[str] = None) -> dict:
        """Load multilingual section classifier YAML"""
        if path is None:
            path = os.path.join(self._profiles_dir, "section_classifier.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_section_type(self, heading_text: str, lang: str = "en") -> str:
        """Classify a section heading into a type (introduction/results/etc.)"""
        classifier = self.load_section_classifier()
        languages = classifier.get("languages", {})
        lang_data = languages.get(lang, languages.get("en", {}))
        text_lower = heading_text.lower()
        for sec_type, keywords in lang_data.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    return sec_type
        return "body"

    def is_rejected_section(self, heading_text: str, lang: str = "en") -> bool:
        """Check if section is a rejected zone (abstract/keywords)"""
        classifier = self.load_section_classifier()
        rejected = classifier.get("rejected", {})
        lang_rejected = rejected.get(lang, rejected.get("en", []))
        text_lower = heading_text.lower()
        for kw in lang_rejected:
            if kw.lower() in text_lower:
                return True
        return False

    def get_this_work_patterns(self, lang: str = "en") -> list[str]:
        """Get 'this work' patterns for a language"""
        classifier = self.load_section_classifier()
        patterns = classifier.get("this_work_patterns", {})
        return patterns.get(lang, patterns.get("en", []))

    def get_quantitative_patterns(self, lang: str = "en") -> list[str]:
        """Get quantitative claim patterns for a language"""
        classifier = self.load_section_classifier()
        claims = classifier.get("quantitative_claims", {})
        return claims.get(lang, claims.get("en", []))

    # ---- Section Routing ----

    def load_section_routing(self, path: Optional[str] = None) -> dict:
        """Load topic-to-section routing map"""
        if path is None:
            path = os.path.join(self._profiles_dir, "section_routing.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}

    def route_topic_to_section(self, title: str, abstract: str = "",
                               paper_type: str = "research") -> str:
        """Route a paper to a manuscript section based on topic keywords"""
        if paper_type == "review":
            return "Introduction"

        routing = self.load_section_routing()
        routes = routing.get("routes", {})
        text = (title + " " + abstract).lower()

        for topic_key, route_data in routes.items():
            keywords = route_data.get("keywords", [])
            for kw in keywords:
                if kw.lower() in text:
                    return route_data.get("section", "General")

        return "General"

    # ---- Journal IF Database ----

    def load_journal_if_database(self, path: Optional[str] = None) -> dict[str, float]:
        """Load journal IF database from YAML"""
        if path is None:
            path = os.path.join(self._profiles_dir, "journals", "if_database.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                return data.get("journals", {})
        return {}

    def load_journal_aliases(self, path: Optional[str] = None) -> dict[str, str]:
        """Load explicit journal-title aliases from the canonical IF YAML."""
        if path is None:
            path = os.path.join(self._profiles_dir, "journals", "if_database.yaml")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
                aliases = data.get("aliases", {})
                return {
                    str(alias).lower().strip(): str(canonical).lower().strip()
                    for alias, canonical in aliases.items()
                }
        return {}

    def summary(self) -> str:
        """Human-readable profile summary"""
        return (
            f"Profile: {self._profile_name}\n"
            f"  Body IF:  enabled={self.body_if_enabled}, threshold={self.body_if_threshold}\n"
            f"  Table IF: enabled={self.table_if_enabled}, threshold={self.table_if_threshold}\n"
            f"  Review:   intro_only={self.review_intro_only}, "
            f"forbid_quant={self.review_forbidden_quantitative}\n"
            f"  Density:  sentence_max={self.sentence_max_citations}, "
            f"para_normal={self.paragraph_normal_max}\n"
            f"  Zones:    abstract_new={self.abstract_new_citation}, "
            f"figure_new={self.figure_allow_new}\n"
            f"  Semantic: min_similarity={self.min_similarity}"
        )


# Module-level convenience accessor
def get_policy() -> PolicyManager:
    """Get the singleton policy manager instance"""
    return PolicyManager.instance()
