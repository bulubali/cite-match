"""
CiteMatch v2.5 — Phase 7: Citation Mapping Report

Reads pre-migration and post-migration manuscripts,
extracts citekey sequences, computes context anchors,
and generates CiteMatch_Mapping_Report.md + .csv (UTF-8 BOM).
"""
import re
import csv
import os
import difflib
from typing import Optional
from dataclasses import dataclass, field


BS = chr(92)


@dataclass
class MappingEntry:
    """One citation's before/after mapping"""
    citekey: str = ""
    old_number: str = ""      # e.g. "[15]" or "-"
    new_number: str = ""      # e.g. "[18]" or "-"
    context_before: str = ""  # 40 chars before citation in old manuscript
    context_after: str = ""   # 40 chars before citation in new manuscript
    anchor_similarity: float = 0.0
    status: str = ""          # "normal" / "new" / "warning"


@dataclass
class MappingReport:
    """Complete mapping report"""
    entries: list[MappingEntry] = field(default_factory=list)
    missing_keys: list[str] = field(default_factory=list)
    total_citations: int = 0
    new_citations: int = 0
    warnings: int = 0

    def to_markdown(self) -> str:
        lines = [
            "# CiteMatch — Citation Mapping Report",
            "",
            f"**Total citations**: {self.total_citations}",
            f"**New citations**: {self.new_citations}",
            f"**Warnings**: {self.warnings}",
            f"**Missing keys**: {len(self.missing_keys)}",
            "",
            "| CiteKey | Old # | New # | Anchor Similarity | Status |",
            "|:---|:---|:---|:---|:---|",
        ]
        for e in self.entries:
            pct = f"{e.anchor_similarity:.0%}"
            lines.append(
                f"| @{e.citekey} | {e.old_number} | {e.new_number} "
                f"| {pct} | {e.status} |"
            )

        if self.missing_keys:
            lines.append("")
            lines.append("## ⚠️ Missing Citations")
            for k in self.missing_keys:
                lines.append(f"- `@{k}` — present in original but not in final manuscript")

        return "\n".join(lines)

    def to_csv(self) -> str:
        """Generate CSV content with UTF-8 BOM"""
        result = chr(0xFEFF)  # BOM
        result += "CiteKey,Old Number,New Number,Anchor Similarity,Status\n"
        for e in self.entries:
            result += (
                f'"@{e.citekey}","{e.old_number}","{e.new_number}",'
                f'"{e.anchor_similarity:.0%}","{e.status}"\n'
            )
        return result


class MappingReportGenerator:
    """Generate citation mapping report from pre/post manuscripts

    Usage:
        gen = MappingReportGenerator()
        report = gen.generate(original_text, migrated_text)
        gen.save_markdown(report, "CiteMatch_Mapping_Report.md")
        gen.save_csv(report, "CiteMatch_Mapping_Report.csv")
    """

    CONTEXT_CHARS = 40
    SIMILARITY_WARNING_THRESHOLD = 0.50

    def generate(
        self,
        original_text: str,
        migrated_text: str,
    ) -> MappingReport:
        """Generate mapping report comparing old and new citekey sequences"""
        old_keys, old_contexts = self._extract_keys_with_context(original_text)
        new_keys, new_contexts = self._extract_keys_with_context(migrated_text)

        report = MappingReport()
        report.total_citations = len(new_keys)

        # Build old index: citekey → position
        old_positions: dict[str, int] = {}
        old_order: list[str] = []
        pos = 0
        for k in old_keys:
            old_order.append(k)
            if k not in old_positions:
                old_positions[k] = pos
            pos += 1

        # Build new index
        new_positions: dict[str, int] = {}
        new_order: list[str] = []
        pos = 0
        for k in new_keys:
            new_order.append(k)
            if k not in new_positions:
                new_positions[k] = pos
            pos += 1

        # Map each new key
        all_keys = set(old_keys) | set(new_keys)
        for key in sorted(all_keys):
            entry = MappingEntry(citekey=key)

            if key in old_positions:
                entry.old_number = f"[{old_positions[key] + 1}]"
                entry.context_before = old_contexts.get(key, "")
            else:
                entry.old_number = "-"
                entry.status = "new"
                report.new_citations += 1

            if key in new_positions:
                entry.new_number = f"[{new_positions[key] + 1}]"
                entry.context_after = new_contexts.get(key, "")
            else:
                entry.new_number = "-"
                entry.status = "missing"
                report.missing_keys.append(key)

            # Compute anchor similarity via SequenceMatcher
            if entry.context_before and entry.context_after:
                sm = difflib.SequenceMatcher(
                    None,
                    entry.context_before.lower(),
                    entry.context_after.lower(),
                )
                entry.anchor_similarity = sm.ratio()
            elif entry.status == "new":
                entry.anchor_similarity = 1.0  # new citation has no old context
            else:
                entry.anchor_similarity = 0.0

            # Set status
            if not entry.status:
                if entry.anchor_similarity < self.SIMILARITY_WARNING_THRESHOLD:
                    entry.status = "warning"
                    report.warnings += 1
                else:
                    entry.status = "normal"

            report.entries.append(entry)

        return report

    def save_markdown(self, report: MappingReport, path: str) -> str:
        """Save mapping report as markdown"""
        content = report.to_markdown()
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def save_csv(self, report: MappingReport, path: str) -> str:
        """Save mapping report as CSV with UTF-8 BOM"""
        content = report.to_csv()
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return path

    @staticmethod
    def _extract_keys_with_context(text: str) -> tuple[list[str], dict[str, str]]:
        """Extract ordered citekeys and their context anchors (40 chars before)"""
        keys = []
        contexts: dict[str, str] = {}

        # Match [@citekey] or [@key1; @key2]
        pattern = re.compile(r'\[@([^\]]+)\]')
        for match in pattern.finditer(text):
            # Extract context: CONTEXT_CHARS before the match
            start = max(0, match.start() - MappingReportGenerator.CONTEXT_CHARS)
            ctx = text[start:match.start()].replace("\n", " ").strip()
            if len(ctx) > MappingReportGenerator.CONTEXT_CHARS:
                ctx = "..." + ctx[-MappingReportGenerator.CONTEXT_CHARS:]

            inner = match.group(1)
            inner_clean = inner.replace("{", "").replace("}", "")
            for part in re.split(r'[;\s]+', inner_clean):
                part = part.strip().lstrip("@")
                if part and re.match(r'^\w+$', part):
                    keys.append(part)
                    if part not in contexts:
                        contexts[part] = ctx

        return keys, contexts
