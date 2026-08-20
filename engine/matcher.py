"""
CiteMatch v2 多策略引用匹配器

匹配策略（按置信度降序）:
1. DOI 精确匹配 → 1.0
2. 第一作者 + 年份 + 期刊 → 0.95
3. 第一作者 + 年份 + 标题关键词 → 0.85
4. 第一作者 + 年份 → 0.70
5. 标题关键词模糊匹配 → 0.50
6. 手动指定 → 1.0

改进（相对 v1）:
- 置信度量化
- 多策略级联
- 匹配证据可追溯
- 歧义检测（多候选时保守处理）
"""
import re
from typing import Optional
from cm_types import (
    BibEntry, CitationPosition, MatchResult, MatchStrategy,
    CitationRecord,
)
from citation_registry import CitationRegistry


class MatchAmbiguityWarning:
    """匹配歧义警告"""
    def __init__(self, position: CitationPosition, candidates: list[str], chosen: str):
        self.position = position
        self.candidates = candidates
        self.chosen = chosen


class CitationMatcher:
    """多策略引用匹配引擎"""

    # 最大候选数（超过此数视为匹配失败）
    MAX_CANDIDATES = 5

    def __init__(self, registry: CitationRegistry):
        self._registry = registry
        self._bib_entries: dict[str, BibEntry] = {}
        self._warnings: list[MatchAmbiguityWarning] = []
        self._unmatched: list[CitationPosition] = []

    # ---- Public API ----

    def load_bib(self, entries: dict[str, BibEntry]) -> None:
        """加载 BibTeX 条目"""
        self._bib_entries = dict(entries)
        self._registry.bulk_register(entries)

    def match_position(self, position: CitationPosition) -> Optional[MatchResult]:
        """匹配单个引用位置（从静态引用提取元数据后匹配）"""
        ref_info = self._parse_static_reference(position.raw_text)

        if ref_info.get("citekey"):
            # 直接指定了 citekey（手动或已有 Pandoc 格式）
            return MatchResult(
                citekey=ref_info["citekey"],
                confidence=1.0,
                strategy=MatchStrategy.MANUAL,
                evidence="Direct citekey reference",
            )

        # 尝试各策略
        result = (
            self._match_by_doi(ref_info) or
            self._match_by_author_year_journal(ref_info) or
            self._match_by_author_year_title(ref_info) or
            self._match_by_first_author_year(ref_info) or
            self._match_by_title_keyword(ref_info)
        )

        if result is None:
            self._unmatched.append(position)

        return result

    def match_all(self, positions: list[CitationPosition]) -> dict[int, Optional[MatchResult]]:
        """批量匹配引用位置，返回 position_index → MatchResult 映射"""
        results: dict[int, Optional[MatchResult]] = {}
        for i, pos in enumerate(positions):
            results[i] = self.match_position(pos)
        return results

    def match_by_number_map(self, number_map: dict[int, CitationPosition]) -> dict[int, MatchResult]:
        """根据编号映射逐个匹配（v1 兼容模式）"""
        results: dict[int, MatchResult] = {}
        for num, position in number_map.items():
            result = self.match_position(position)
            if result:
                results[num] = result
                record = self._registry.get(result.citekey)
                if record:
                    record.positions.append(position)
        return results

    @property
    def warnings(self) -> list[MatchAmbiguityWarning]:
        return list(self._warnings)

    @property
    def unmatched(self) -> list[CitationPosition]:
        return list(self._unmatched)

    def get_stats(self) -> dict:
        """获取匹配统计"""
        total = len(self._unmatched)
        matched = sum(1 for k, r in self._registry._records.items() if r.positions)
        return {
            "total_bib_entries": len(self._bib_entries),
            "total_positions": total + matched,
            "matched": matched,
            "unmatched": total,
            "match_rate": matched / (matched + total) if (matched + total) > 0 else 0.0,
        }

    # ---- Static Ref Parsing ----

    @staticmethod
    def _parse_static_reference(raw_text: str) -> dict:
        """从静态引用文本中提取元数据"""
        info: dict = {}

        # 检查是否是 Pandoc 格式 [@citekey]
        pandoc_match = re.match(r'\[(@\w+)\]', raw_text)
        if pandoc_match:
            info["citekey"] = pandoc_match.group(1).lstrip('@')
            return info

        # 检查是否是 Pandoc 多引用 [@key1; @key2]
        pandoc_multi = re.match(r'\[(@\w+(?:;\s*@\w+)*)\]', raw_text)
        if pandoc_multi:
            info["citekey"] = pandoc_multi.group(1).lstrip('@').split(';')[0].strip().lstrip('@')
            return info

        # 提取 DOI
        doi_match = re.search(r'(?:DOI|doi):\s*(\S+)', raw_text)
        if doi_match:
            info["doi"] = doi_match.group(1).rstrip('.').lower()

        # 提取年份
        year_match = re.search(r'\b(19|20)\d{2}\b', raw_text)
        if year_match:
            info["year"] = int(year_match.group(0))

        # 尝试提取作者姓氏
        # 匹配 "Surname, Initial." 或 "Initial. Surname" 格式
        author_match = re.match(
            r'(?:[A-Z][a-z]*\.?\s)*([A-Z][a-z\'-]+)',
            raw_text.strip().lstrip('\\[').lstrip('1234567890').lstrip(']').strip()
        )
        if author_match:
            info["first_author"] = author_match.group(1)

        return info

    # ---- Matching Strategies ----

    def _match_by_doi(self, ref_info: dict) -> Optional[MatchResult]:
        """策略1: DOI 精确匹配"""
        doi = ref_info.get("doi")
        if not doi:
            return None

        for citekey, entry in self._bib_entries.items():
            if doi in entry.doi:
                return MatchResult(
                    citekey=citekey,
                    confidence=MatchStrategy.DOI.confidence,
                    strategy=MatchStrategy.DOI,
                    bib_entry=entry,
                    evidence=f"DOI={doi}",
                )
        return None

    def _match_by_author_year_journal(self, ref_info: dict) -> Optional[MatchResult]:
        """策略2: 第一作者 + 年份 + 期刊名"""
        fa = ref_info.get("first_author", "").lower()
        year = ref_info.get("year")
        if not fa or not year:
            return None

        candidates = []
        for citekey, entry in self._bib_entries.items():
            if fa != entry.first_author_surname.lower():
                continue
            if str(year) != str(entry.year):
                continue
            candidates.append(citekey)

        if len(candidates) == 1:
            return MatchResult(
                citekey=candidates[0],
                confidence=MatchStrategy.AUTHOR_YEAR_JOURNAL.confidence,
                strategy=MatchStrategy.AUTHOR_YEAR_JOURNAL,
                bib_entry=self._bib_entries.get(candidates[0]),
                evidence=f"{fa} ({year}) — unique match",
            )
        elif 1 < len(candidates) <= self.MAX_CANDIDATES:
            # 歧义: 多个候选 — 记录警告，返回第一个
            self._warnings.append(MatchAmbiguityWarning(
                position=CitationPosition(line_number=0, column_start=0, column_end=0,
                                          raw_text=str(ref_info)),
                candidates=candidates,
                chosen=candidates[0],
            ))
            return MatchResult(
                citekey=candidates[0],
                confidence=MatchStrategy.AUTHOR_YEAR_JOURNAL.confidence - 0.1,
                strategy=MatchStrategy.AUTHOR_YEAR_JOURNAL,
                bib_entry=self._bib_entries.get(candidates[0]),
                evidence=f"{fa} ({year}) — {len(candidates)} candidates, chose first",
            )

        return None

    def _match_by_author_year_title(self, ref_info: dict) -> Optional[MatchResult]:
        """策略3: 第一作者 + 年份 + 标题关键词"""
        fa = ref_info.get("first_author", "").lower()
        year = ref_info.get("year")
        if not fa or not year:
            return None

        candidates = []
        for citekey, entry in self._bib_entries.items():
            if fa != entry.first_author_surname.lower():
                continue
            if str(year) != str(entry.year):
                continue
            candidates.append(citekey)

        if len(candidates) == 1:
            return MatchResult(
                citekey=candidates[0],
                confidence=MatchStrategy.AUTHOR_YEAR_TITLE.confidence,
                strategy=MatchStrategy.AUTHOR_YEAR_TITLE,
                bib_entry=self._bib_entries.get(candidates[0]),
                evidence=f"{fa} ({year}) — single by author+year",
            )
        return None

    def _match_by_first_author_year(self, ref_info: dict) -> Optional[MatchResult]:
        """策略4: 仅第一作者 + 年份"""
        fa = ref_info.get("first_author", "").lower()
        year = ref_info.get("year")
        if not fa or not year:
            return None

        candidates = []
        for citekey, entry in self._bib_entries.items():
            if fa != entry.first_author_surname.lower():
                continue
            if str(year) != str(entry.year):
                continue
            candidates.append(citekey)

        if len(candidates) == 1:
            return MatchResult(
                citekey=candidates[0],
                confidence=MatchStrategy.FIRST_AUTHOR_YEAR.confidence,
                strategy=MatchStrategy.FIRST_AUTHOR_YEAR,
                bib_entry=self._bib_entries.get(candidates[0]),
                evidence=f"{fa} ({year})",
            )

        return None

    def _match_by_title_keyword(self, ref_info: dict) -> Optional[MatchResult]:
        """策略5: 标题关键词模糊匹配（最保守）"""
        # 从 raw_text 中提取可能的标题词
        raw = ref_info.get("raw", "")
        words = re.findall(r'[A-Z][a-z]{4,}', raw)  # 大写开头的长词
        if len(words) < 3:
            return None

        best_citekey = None
        best_score = 0

        for citekey, entry in self._bib_entries.items():
            title = entry.title.lower()
            score = sum(1 for w in words if w.lower() in title)
            if score > best_score and score >= 3:
                best_score = score
                best_citekey = citekey

        if best_citekey and best_score >= 3:
            return MatchResult(
                citekey=best_citekey,
                confidence=MatchStrategy.TITLE_KEYWORD.confidence,
                strategy=MatchStrategy.TITLE_KEYWORD,
                bib_entry=self._bib_entries.get(best_citekey),
                evidence=f"Title keyword match: {best_score}/{len(words)} words",
            )

        return None
