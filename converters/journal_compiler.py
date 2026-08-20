"""
CiteMatch v2.5 — Journal Style Compile Pipeline (Phase 6)

JournalResolver → JournalStyleManager → CSLModifier → PandocCommandBuilder
"""
import os
import subprocess
from typing import Optional
from dataclasses import dataclass


# Journal alias → full name lookup
JOURNAL_ALIASES = {
    "nature": "nature",
    "science": "science",
    "nc": "nature-communications",
    "nature communications": "nature-communications",
    "nat commun": "nature-communications",
    "nat. commun.": "nature-communications",
    "am": "advanced-materials",
    "advanced materials": "advanced-materials",
    "adv mater": "advanced-materials",
    "adv. mater.": "advanced-materials",
    "afm": "advanced-functional-materials",
    "advanced functional materials": "advanced-functional-materials",
    "adv funct mater": "advanced-functional-materials",
    "aem": "advanced-energy-materials",
    "advanced energy materials": "advanced-energy-materials",
    "acs nano": "acs-nano",
    "nano energy": "nano-energy",
    "small": "small",
    "ieee sensors": "ieee-sensors-journal",
    "ieee sensors journal": "ieee-sensors-journal",
    "ieee access": "ieee-access",
    "sci adv": "science-advances",
    "science advances": "science-advances",
}


@dataclass
class JournalConfig:
    """Resolved journal configuration"""
    name: str           # display name
    csl_name: str       # CSL filename key
    csl_path: str       # local CSL path (may not exist yet)
    is_default: bool = False


class JournalResolver:
    """Resolve journal names and aliases to CSL identifiers"""

    DEFAULT_JOURNAL = "nature"

    @staticmethod
    def resolve(name: Optional[str]) -> JournalConfig:
        """Resolve journal name or alias.

        Args:
            name: user input (e.g. "AM", "nature comm", "")

        Returns:
            JournalConfig with resolved CSL identifier
        """
        if not name or not name.strip():
            return JournalConfig(
                name="Nature",
                csl_name=JournalResolver.DEFAULT_JOURNAL,
                csl_path="",
                is_default=True,
            )

        clean = name.strip().lower()

        # Direct alias lookup
        if clean in JOURNAL_ALIASES:
            csl_name = JOURNAL_ALIASES[clean]
            return JournalConfig(
                name=JournalResolver._display_name(csl_name),
                csl_name=csl_name,
                csl_path="",
            )

        # Partial match
        for alias, csl_name in JOURNAL_ALIASES.items():
            if alias in clean or clean in alias:
                return JournalConfig(
                    name=JournalResolver._display_name(csl_name),
                    csl_name=csl_name,
                    csl_path="",
                )

        # Unknown — return as-is for fallback handling
        return JournalConfig(name=name.strip(), csl_name=clean.replace(" ", "-"), csl_path="")

    @staticmethod
    def _display_name(csl_name: str) -> str:
        return csl_name.replace("-", " ").title()


class JournalStyleManager:
    """Manage CSL files: download, cache, modify"""

    CSL_CACHE_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cache", "csl",
    )

    FALLBACK_OPTIONS = ["nature", "ieee", "apa"]

    def __init__(self):
        os.makedirs(self.CSL_CACHE_DIR, exist_ok=True)

    def get_or_download_csl(self, csl_name: str) -> Optional[str]:
        """Get CSL path from cache or download.

        Returns path to CSL file, or None if unavailable.
        """
        cache_path = os.path.join(self.CSL_CACHE_DIR, f"{csl_name}.csl")
        if os.path.exists(cache_path):
            return cache_path

        # Try downloading from CSL repository
        try:
            import urllib.request
            url = (
                f"https://raw.githubusercontent.com/citation-style-language/"
                f"styles/master/{csl_name}.csl"
            )
            urllib.request.urlretrieve(url, cache_path)
            return cache_path
        except Exception:
            return None

    def get_fallback_prompt(self) -> str:
        """Prompt user to select from fallback styles"""
        lines = [
            "Cannot find CSL for specified journal.",
            "Please select a fallback style:",
        ]
        for i, opt in enumerate(self.FALLBACK_OPTIONS, 1):
            lines.append(f"  {chr(0x2460 + i - 1)} {opt}")
        lines.append(f"  {chr(0x2460 + len(self.FALLBACK_OPTIONS))} I will provide my own CSL file")
        return "\n".join(lines)

    def modify_csl(
        self, csl_path: str, author_style: str = "default"
    ) -> str:
        """Apply CSL modifications via CSLModifier.

        Args:
            csl_path: path to original CSL
            author_style: "default" or "full"

        Returns:
            path to modified CSL
        """
        from converters.csl_modifier import CSLModifier

        modifier = CSLModifier(csl_path)
        modifier.ensure_collapse()
        modifier.ensure_bibliography_numbering()

        if author_style == "full":
            modifier.set_full_author_display()
        else:
            modifier.set_default_author_display()

        return modifier.save()


class PandocCommandBuilder:
    """Build Pandoc compile command with correct parameter order.

    Required order:
      --filter pandoc-crossref → --citeproc → --bibliography → --csl → -M link-citations
    """

    def __init__(self, pandoc_path: Optional[str] = None):
        if pandoc_path is None:
            self._pandoc_executable = "pandoc"
        else:
            executable = os.path.abspath(os.path.expanduser(str(pandoc_path)))
            if not os.path.isfile(executable):
                raise ValueError(f"Pandoc executable not found: {pandoc_path}")
            self._pandoc_executable = executable
        self._input: str = "draft.md"
        self._output: str = "Final_Manuscript.docx"
        self._bibliography: Optional[str] = None
        self._csl: Optional[str] = None
        self._use_crossref: bool = True
        self._use_citeproc: bool = True
        self._link_citations: bool = True

    def set_input(self, path: str) -> "PandocCommandBuilder":
        self._input = path; return self

    def set_output(self, path: str) -> "PandocCommandBuilder":
        self._output = path; return self

    def set_bibliography(self, path: str) -> "PandocCommandBuilder":
        self._bibliography = path; return self

    def set_csl(self, path: str) -> "PandocCommandBuilder":
        self._csl = path; return self

    def build(self) -> list[str]:
        """Build command in required parameter order"""
        cmd = [self._pandoc_executable, self._input, "-o", self._output]
        if self._use_crossref:
            cmd.append("--filter")
            cmd.append("pandoc-crossref")
        if self._use_citeproc:
            cmd.append("--citeproc")
        if self._bibliography:
            cmd.extend(["--bibliography", self._bibliography])
        if self._csl:
            cmd.extend(["--csl", self._csl])
        if self._link_citations:
            cmd.extend(["-M", "link-citations=true"])
        return cmd

    def build_string(self) -> str:
        return " ".join(self.build())

    def execute(self) -> tuple[bool, str]:
        """Execute Pandoc compile. Returns (success, output)."""
        cmd = self.build()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return result.returncode == 0, result.stdout + result.stderr
        except FileNotFoundError:
            return False, "Pandoc not found. Install from https://pandoc.org"
        except Exception as e:
            return False, str(e)
