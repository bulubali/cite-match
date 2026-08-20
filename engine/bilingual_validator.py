"""
CiteMatch v2.1 双语引用守恒验证器

双文件引用守恒:
- 中英文两份 manuscript 的 citation keys 必须完全一致
- 数量不同 → CitationIntegrityError
- key 不同 → CitationIntegrityError
- 顺序不同 → WARNING only (不阻断，中英文句子结构天然不同)

v2.1 Adjustment:
- Citation order divergence → WARNING only (not failure)
- is_valid 不再依赖 order_consistent
- raise_if_invalid() 不因 order 问题抛出
- 新增 order_divergence_level (LOW/MEDIUM/HIGH) 基于 section-level overlap
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
from cm_types import CitationPosition
from citation_registry import CitationIntegrityError


class OrderDivergenceLevel(Enum):
    """引用顺序发散程度"""
    NONE = "none"        # 完全一致
    LOW = "low"          # 同一 section 内 citation overlap > 90%
    MEDIUM = "medium"    # 同一 section 内 citation overlap 70-90%
    HIGH = "high"        # 缺失 citation blocks 或 overlap < 70%


@dataclass
class BilingualCitationReport:
    """双语引用对比报告"""
    en_file: str = ""
    zh_file: str = ""
    en_total: int = 0              # EN 总出现次数
    zh_total: int = 0              # ZH 总出现次数
    en_unique: int = 0             # EN 唯一 key 数量
    zh_unique: int = 0             # ZH 唯一 key 数量
    common_count: int = 0
    missing_in_chinese: list[str] = field(default_factory=list)
    missing_in_english: list[str] = field(default_factory=list)
    count_difference: int = 0      # unique count difference
    order_consistent: bool = True
    order_issues: list[str] = field(default_factory=list)
    order_divergence_level: str = "none"  # LOW / MEDIUM / HIGH / none
    section_overlap_ratio: float = 1.0    # 0.0–1.0
    is_valid: bool = True           # 不因 order 问题变 False

    def raise_if_invalid(self) -> None:
        """missing keys / extra keys / count difference → CitationIntegrityError

        注意: order 问题不触发异常（仅 warning）。
        """
        issues = []
        if self.missing_in_chinese:
            preview = (', '.join(self.missing_in_chinese[:5]))
            if len(self.missing_in_chinese) > 5:
                preview += "..."
            issues.append(
                f"Missing in Chinese: {len(self.missing_in_chinese)} keys ({preview})"
            )
        if self.missing_in_english:
            preview = (', '.join(self.missing_in_english[:5]))
            if len(self.missing_in_english) > 5:
                preview += "..."
            issues.append(
                f"Missing in English: {len(self.missing_in_english)} keys ({preview})"
            )
        if self.count_difference != 0:
            issues.append(
                f"Count difference: EN={self.en_unique}, ZH={self.zh_unique} "
                f"(diff={self.count_difference})"
            )

        if issues:
            raise CitationIntegrityError(
                "Bilingual citation conservation violated:\n  " +
                "\n  ".join(issues)
            )


class BilingualValidator:
    """双文件引用守恒验证器

    用法:
        validator = BilingualValidator()
        report = validator.compare_manuscripts(en_text, zh_text)
        report.raise_if_invalid()  # 仅 missing/extra/count 异常
        print(report.order_divergence_level)  # 查看顺序发散程度
    """

    def __init__(self):
        self._en_keys: list[str] = []
        self._zh_keys: list[str] = []
        self._en_sections: dict[str, str] = {}  # key → section name
        self._zh_sections: dict[str, str] = {}

    # ---- Public ----

    def extract_keys(self, text: str) -> list[str]:
        """从 Markdown 文本中提取所有 Pandoc citation keys（保持顺序）"""
        keys = []
        pattern = re.compile(r'\[@([^\]]+)\]')
        for match in pattern.finditer(text):
            inner = match.group(1)
            inner_clean = inner.replace('{', '').replace('}', '')
            parts = re.split(r'[;\s]+', inner_clean)
            for part in parts:
                part = part.strip().lstrip('@')
                if part and re.match(r'^\w+$', part):
                    keys.append(part)
        return keys

    def extract_keys_with_sections(self, text: str) -> tuple[list[str], dict[str, str]]:
        """提取 keys 并记录每个 key 所属的 section

        Returns:
            (ordered keys, key→section mapping)
        """
        keys = []
        sections: dict[str, str] = {}
        current_section = "(preamble)"

        lines = text.split('\n')
        pattern = re.compile(r'\[@([^\]]+)\]')

        for line in lines:
            stripped = line.strip()
            # Markdown heading detection
            if re.match(r'^#{1,6}\s+', stripped):
                current_section = re.sub(r'^#{1,6}\s+', '', stripped)[:80]

            for match in pattern.finditer(line):
                inner = match.group(1)
                inner_clean = inner.replace('{', '').replace('}', '')
                parts = re.split(r'[;\s]+', inner_clean)
                for part in parts:
                    part = part.strip().lstrip('@')
                    if part and re.match(r'^\w+$', part):
                        keys.append(part)
                        # First occurrence wins for section assignment
                        if part not in sections:
                            sections[part] = current_section

        return keys, sections

    def compare_manuscripts(self, en_text: str, zh_text: str,
                           en_path: str = "", zh_path: str = "") -> BilingualCitationReport:
        """对比中英文两份 manuscript 的引用一致性"""
        self._en_keys, self._en_sections = self.extract_keys_with_sections(en_text)
        self._zh_keys, self._zh_sections = self.extract_keys_with_sections(zh_text)

        en_set = set(self._en_keys)
        zh_set = set(self._zh_keys)

        report = BilingualCitationReport(
            en_file=en_path,
            zh_file=zh_path,
            en_total=len(self._en_keys),
            zh_total=len(self._zh_keys),
            en_unique=len(en_set),
            zh_unique=len(zh_set),
            common_count=len(en_set & zh_set),
            missing_in_chinese=sorted(en_set - zh_set),
            missing_in_english=sorted(zh_set - en_set),
            count_difference=len(en_set) - len(zh_set),
        )

        # Order check — WARNING only, never invalidates
        report.order_consistent, report.order_issues = self._check_order(
            self._en_keys, self._zh_keys
        )
        report.order_divergence_level, report.section_overlap_ratio = \
            self._compute_divergence_level()

        # is_valid depends ONLY on key completeness, NOT on order
        report.is_valid = (
            len(report.missing_in_chinese) == 0 and
            len(report.missing_in_english) == 0 and
            report.count_difference == 0
        )

        return report

    # ---- Internal ----

    @staticmethod
    def _check_order(en_keys: list[str], zh_keys: list[str]) -> tuple[bool, list[str]]:
        """检查引用顺序一致性（pairwise relative order in common subset）"""
        issues = []

        zh_set = set(zh_keys)
        en_common = [k for k in en_keys if k in zh_set]
        zh_common = [k for k in zh_keys if k in set(en_keys)]

        if len(en_common) < 2:
            return True, []

        zh_index = {k: i for i, k in enumerate(zh_keys)}

        for i in range(len(en_common) - 1):
            a, b = en_common[i], en_common[i + 1]
            if a in zh_index and b in zh_index:
                if zh_index[a] > zh_index[b]:
                    issues.append(
                        f"Order mismatch: '{a}' before '{b}' in EN, "
                        f"but '{b}' before '{a}' in ZH"
                    )

        return len(issues) == 0, issues

    def _compute_divergence_level(self) -> tuple[str, float]:
        """Compute order divergence based on section-level citation overlap

        For each section that appears in both manuscripts, compare the set
        of citations used in that section. High overlap = LOW divergence.

        Returns:
            (divergence_level, overlap_ratio)
        """
        # If order is fully consistent → NONE
        if self._en_keys == self._zh_keys:
            return OrderDivergenceLevel.NONE.value, 1.0

        en_common_keys = [k for k in self._en_keys if k in self._zh_sections]
        zh_common_keys = [k for k in self._zh_keys if k in self._en_sections]

        if len(en_common_keys) == 0 and len(zh_common_keys) == 0:
            return OrderDivergenceLevel.HIGH.value, 0.0

        # Count how many keys appear in the same section across languages
        same_section = 0
        total_comparable = 0

        for key in set(self._en_keys) & set(self._zh_keys):
            en_sec = self._en_sections.get(key, "(unknown)")
            zh_sec = self._zh_sections.get(key, "(unknown)")
            total_comparable += 1
            # Fuzzy section match: same section name OR one contains the other
            if en_sec == zh_sec or en_sec in zh_sec or zh_sec in en_sec:
                same_section += 1

        if total_comparable == 0:
            return OrderDivergenceLevel.NONE.value, 1.0

        ratio = same_section / total_comparable

        if ratio > 0.90:
            level = OrderDivergenceLevel.LOW.value
        elif ratio > 0.70:
            level = OrderDivergenceLevel.MEDIUM.value
        else:
            level = OrderDivergenceLevel.HIGH.value

        return level, round(ratio, 4)
