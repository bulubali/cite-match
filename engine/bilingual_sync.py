"""
CiteMatch v2 双语引用同步引擎

功能:
- 英文引用 [@key] 与中文引用 [@key_cn] 的同步
- 检测中英文版本之间的引用差异
- 保持引用顺序一致性
- 生成同步报告

使用场景:
  论文同时有中文版和英文版草稿，引用必须保持一致。
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from cm_types import CitationPosition
from citation_registry import CitationRegistry
from md_ast import MarkdownAST


@dataclass
class SyncDiff:
    """同步差异项"""
    citekey: str
    en_position: Optional[CitationPosition] = None
    zh_position: Optional[CitationPosition] = None
    diff_type: str = ""  # "missing_in_zh", "missing_in_en", "order_mismatch", "ok"


@dataclass
class SyncReport:
    """同步报告"""
    en_file: str = ""
    zh_file: str = ""
    total_en_citations: int = 0
    total_zh_citations: int = 0
    matched: int = 0
    missing_in_zh: list[str] = field(default_factory=list)
    missing_in_en: list[str] = field(default_factory=list)
    order_issues: list[str] = field(default_factory=list)
    diffs: list[SyncDiff] = field(default_factory=list)

    @property
    def is_synced(self) -> bool:
        return (len(self.missing_in_zh) == 0 and
                len(self.missing_in_en) == 0 and
                len(self.order_issues) == 0)


class BilingualSyncEngine:
    """双语引用同步引擎"""

    def __init__(self, registry: CitationRegistry):
        self._registry = registry
        self._en_citations: list[CitationPosition] = []
        self._zh_citations: list[CitationPosition] = []
        self._en_text: str = ""
        self._zh_text: str = ""

    # ---- Public API ----

    def load_documents(self, en_text: str, zh_text: str) -> None:
        """加载中英文文档"""
        self._en_text = en_text
        self._zh_text = zh_text

        en_ast = MarkdownAST(en_text)
        en_ast.parse()
        self._en_citations = en_ast.find_existing_pandoc_citations()

        zh_ast = MarkdownAST(zh_text)
        zh_ast.parse()
        self._zh_citations = zh_ast.find_existing_pandoc_citations()

    def compare(self) -> SyncReport:
        """对比中英文引用差异"""
        report = SyncReport()
        report.total_en_citations = len(self._en_citations)
        report.total_zh_citations = len(self._zh_citations)

        # 提取 citekeys
        en_keys = self._extract_keys(self._en_citations)
        zh_keys = self._extract_keys(self._zh_citations)

        # 计算差异
        en_set = set(en_keys)
        zh_set = set(zh_keys)

        report.missing_in_zh = sorted(en_set - zh_set)
        report.missing_in_en = sorted(zh_set - en_set)
        report.matched = len(en_set & zh_set)

        # 顺序检查
        order_ok = self._check_order(en_keys, zh_keys)
        if not order_ok:
            report.order_issues.append("Citation order differs between EN and ZH versions")

        # 构建详细 diff
        for key in sorted(en_set | zh_set):
            en_pos = self._find_position(key, self._en_citations)
            zh_pos = self._find_position(key, self._zh_citations)

            if en_pos and not zh_pos:
                dt = "missing_in_zh"
            elif zh_pos and not en_pos:
                dt = "missing_in_en"
            elif en_pos and zh_pos:
                dt = "ok"
            else:
                dt = "unknown"

            report.diffs.append(SyncDiff(
                citekey=key,
                en_position=en_pos,
                zh_position=zh_pos,
                diff_type=dt,
            ))

        return report

    def sync_missing_citations(self, report: SyncReport) -> str:
        """将英文版缺失的引用从中文版同步过来（返回需要添加到英文版的引用）

        策略: 对于中文版有但英文版缺失的引用，生成插入建议。
        """
        suggestions = []
        for key in report.missing_in_en:
            zh_pos = self._find_position(key, self._zh_citations)
            if zh_pos:
                suggestions.append({
                    "citekey": key,
                    "zh_context": self._get_context(self._zh_text, zh_pos),
                    "action": f"Add [@_{key}] to English version",
                })

        # 基于建议更新英文文档
        if suggestions:
            return self._generate_sync_patch(suggestions)
        return ""

    def verify_consistency(self) -> bool:
        """快速验证双语引用一致性"""
        en_keys = set(self._extract_keys(self._en_citations))
        zh_keys = set(self._extract_keys(self._zh_citations))
        return en_keys == zh_keys

    def lock_synced_keys(self) -> None:
        """锁定双语中共同存在的引用"""
        en_keys = set(self._extract_keys(self._en_citations))
        zh_keys = set(self._extract_keys(self._zh_citations))
        common = en_keys & zh_keys
        for key in common:
            self._registry.lock(key)

    # ---- Internal ----

    @staticmethod
    def _extract_keys(citations: list[CitationPosition]) -> list[str]:
        """从 CitationPosition 列表提取 citekey 列表（保持顺序）"""
        keys = []
        for cit in citations:
            # raw_text 如 "[@Chen2023; @Wang2024]"
            found = re.findall(r'@(\w+)', cit.raw_text)
            keys.extend(found)
        return keys

    @staticmethod
    def _find_position(
        citekey: str,
        citations: list[CitationPosition],
    ) -> Optional[CitationPosition]:
        """在引用列表中查找 citekey"""
        for cit in citations:
            if citekey in cit.raw_text:
                return cit
        return None

    @staticmethod
    def _get_context(text: str, position: CitationPosition, window: int = 80) -> str:
        """获取引用位置的上下文"""
        lines = text.split('\n')
        line_idx = position.line_number - 1
        if line_idx < 0 or line_idx >= len(lines):
            return ""

        line = lines[line_idx]
        start = max(0, position.column_start - window)
        end = min(len(line), position.column_end + window)
        return line[start:end]

    @staticmethod
    def _check_order(en_keys: list[str], zh_keys: list[str]) -> bool:
        """检查引用顺序是否一致（基于共同子序列）"""
        # 提取共同 key
        en_order = [k for k in en_keys if k in zh_keys]
        zh_order = [k for k in zh_keys if k in en_keys]

        # 对比相对顺序
        en_index = {k: i for i, k in enumerate(en_keys)}
        zh_index = {k: i for i, k in enumerate(zh_keys)}

        # 检查共同 key 的相对顺序
        for i in range(len(en_order) - 1):
            for j in range(i + 1, len(en_order)):
                a, b = en_order[i], en_order[j]
                if a in zh_index and b in zh_index:
                    if zh_index[a] > zh_index[b]:
                        return False

        return True

    @staticmethod
    def _generate_sync_patch(suggestions: list[dict]) -> str:
        """生成同步补丁文本"""
        lines = ["=== Bilingual Sync Patch ===\n"]
        lines.append("The following citations need to be added to the English version:\n")
        for s in suggestions:
            lines.append(f"  [{s['citekey']}] — {s['action']}")
            if s.get('zh_context'):
                lines.append(f"    ZH context: ...{s['zh_context']}...")
        return '\n'.join(lines)
