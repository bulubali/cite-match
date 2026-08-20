"""
CiteMatch v2 Markdown AST 解析器

改进（相对 v1 正则方案）:
- 结构化 AST 解析（基于 mistune 或手写解析器）
- 正确识别: 表格、代码块、标题、段落、列表
- 区分正文引用 vs 表格内引用（表格内引用受保护）
- 识别上标引用格式（^[N]^）
- 定位每个引用节点的行号和列号
"""
import re
from typing import Optional
from dataclasses import dataclass, field
from cm_types import CitationPosition


@dataclass(frozen=True)
class SectionContext:
    """Normalized section state for one Markdown source line."""
    title: str = ""
    section_type: str = "body"
    protected: bool = False
    is_heading: bool = False


def _canonical_section_text(value: str) -> str:
    """Normalize heading text without coupling protection to Markdown syntax."""
    value = value.casefold().strip()
    value = re.sub(r'^\d+(?:\.\d+)*[.、\s]*', '', value)
    value = value.rstrip(':：').strip()
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', value)


def get_section_classifier_terms() -> tuple[dict[str, list[str]], set[str]]:
    """Load multilingual section and rejected-zone terms from existing policy."""
    try:
        from policy_manager import PolicyManager
        classifier = PolicyManager.instance().load_section_classifier()
    except Exception:
        classifier = {}

    section_terms: dict[str, list[str]] = {}
    for language in classifier.get("languages", {}).values():
        for section_type, terms in language.items():
            section_terms.setdefault(section_type, []).extend(terms or [])

    rejected_terms = {
        _canonical_section_text(term)
        for terms in classifier.get("rejected", {}).values()
        for term in (terms or [])
    }

    # Fail-safe only for the mandatory core zones if policy loading fails.
    if not section_terms:
        section_terms = {
            "abstract": ["abstract", "摘要"],
            "keywords": ["keywords", "key words", "关键词"],
            "introduction": ["introduction", "引言"],
        }
    if not rejected_terms:
        rejected_terms = {
            _canonical_section_text(term)
            for term in ("abstract", "摘要", "keywords", "key words", "关键词")
        }
    return section_terms, rejected_terms


def is_protected_section_title(
    title: str,
    classifier_terms: Optional[tuple[dict[str, list[str]], set[str]]] = None,
) -> bool:
    """Classify an already-resolved section title using shared policy terms."""
    section_terms, rejected_terms = classifier_terms or get_section_classifier_terms()
    canonical = _canonical_section_text(title)
    protected_types = {"abstract", "keywords"}
    for section_type, terms in section_terms.items():
        if section_type not in protected_types:
            continue
        if any(
            (term_key := _canonical_section_text(term)) and
            (canonical == term_key or term_key in canonical)
            for term in terms
        ):
            return True
    return any(term and (canonical == term or term in canonical)
               for term in rejected_terms)


def parse_section_heading(
    line: str,
    classifier_terms: Optional[tuple[dict[str, list[str]], set[str]]] = None,
) -> Optional[SectionContext]:
    """Recognize ATX and Pandoc-produced section-label paragraphs.

    Plain text is accepted only when it exactly names a configured section;
    full-line bold text is treated as Pandoc heading output and may name any
    body section.  This keeps Abstract/Keywords protection active until the
    next real section instead of ending it at an arbitrary paragraph.
    """
    stripped = line.strip()
    if not stripped:
        return None

    atx = re.match(r'^#{1,6}\s+(.+?)\s*#*$', stripped)
    bold = re.fullmatch(r'\*\*(.+?)\*\*', stripped)
    explicit_heading = bool(atx or bold)
    if atx:
        title = atx.group(1).strip()
    elif bold:
        title = bold.group(1).strip()
    else:
        title = stripped

    title = title.rstrip(':：').strip()
    canonical = _canonical_section_text(title)
    section_terms, rejected_terms = classifier_terms or get_section_classifier_terms()

    section_type = "body"
    recognized = False
    for candidate_type, terms in section_terms.items():
        for term in terms:
            term_key = _canonical_section_text(term)
            if term_key and (canonical == term_key or
                             (explicit_heading and term_key in canonical)):
                section_type = candidate_type
                recognized = True
                break
        if recognized:
            break

    if not explicit_heading and not recognized:
        return None

    protected = is_protected_section_title(title, (section_terms, rejected_terms))
    return SectionContext(
        title=title,
        section_type=section_type,
        protected=protected,
        is_heading=True,
    )


@dataclass
class ASTNode:
    """简化的 Markdown AST 节点"""
    type: str  # "heading", "paragraph", "table", "code_block", "list", "text"
    content: str
    line_start: int
    line_end: int
    children: list["ASTNode"] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class MarkdownAST:
    """Markdown 文档的 AST 表示"""

    def __init__(self, source: str):
        self.source: str = source
        self.lines: list[str] = source.split('\n')
        self.root: Optional[ASTNode] = None
        self._citations: list[CitationPosition] = []
        self._table_regions: list[tuple[int, int]] = []  # (start_line, end_line)
        self._table_formats: list[tuple[int, int, str]] = []
        self._code_block_regions: list[tuple[int, int]] = []
        self._section_contexts: dict[int, SectionContext] = {}

    # ---- Public API ----

    def parse(self) -> ASTNode:
        """解析 Markdown 文本为 AST"""
        self._table_regions = []
        self._table_formats = []
        self._code_block_regions = []
        self._build_section_contexts()
        nodes = self._tokenize()
        self.root = ASTNode(
            type="document",
            content="",
            line_start=1,
            line_end=len(self.lines),
            children=nodes,
        )
        return self.root

    def get_section_for_line(self, line_num: int) -> str:
        """Return the normalized section title active at ``line_num``."""
        if not self._section_contexts:
            self._build_section_contexts()
        return self._section_contexts.get(line_num, SectionContext()).title

    def is_heading_line(self, line_num: int) -> bool:
        """Return whether a source line is a recognized section heading."""
        if not self._section_contexts:
            self._build_section_contexts()
        return self._section_contexts.get(line_num, SectionContext()).is_heading

    def is_in_protected_zone(self, line_num: int) -> bool:
        """Return whether NEW citation insertion is forbidden at a line."""
        if not self._section_contexts:
            self._build_section_contexts()
        return self._section_contexts.get(line_num, SectionContext()).protected

    def find_citations(self) -> list[CitationPosition]:
        """查找文档中所有引用位置"""
        self._citations = []

        if self.root is None:
            self.parse()

        self._scan_node(self.root)
        return list(self._citations)

    def find_existing_pandoc_citations(self) -> list[CitationPosition]:
        """查找已有 Pandoc 格式引用 [@citekey]"""
        citations = []
        pattern = re.compile(r'\[(@[^\]]+)\]')

        for i, line in enumerate(self.lines, 1):
            for match in pattern.finditer(line):
                citations.append(CitationPosition(
                    line_number=i,
                    column_start=match.start(),
                    column_end=match.end(),
                    raw_text=match.group(0),
                    section=self._get_section_for_line(i),
                    is_in_table=self._is_in_table(i),
                    is_in_code_block=self._is_in_code_block(i),
                ))
        return citations

    def find_static_citations(self) -> list[CitationPosition]:
        """查找静态编号引用 [N] / ^[N]^ / [N-M] / [N,M]"""
        citations = []
        # 匹配模式
        patterns = [
            # ^[N]^ 上标
            (re.compile(r'\^\[(\d+(?:[,;\s]+\d+)*(?:\s*[-–]+\s*\d+)?)\]\^'), True),
            # \[N\] Pandoc 转义的
            (re.compile(r'\\\[(\d+(?:[,;\s]+\d+)*(?:\s*[-–]+\s*\d+)?)\\\]'), False),
            # plain [N]
            (re.compile(r'(?<!\\)\[(\d+(?:[,;\s]+\d+)*(?:\s*[-–]+\s*\d+)?)\](?!\()'), False),
        ]

        for pattern, is_superscript in patterns:
            for i, line in enumerate(self.lines, 1):
                # 跳过参考文献列表行（以 \[N\] Author 开头）
                if re.match(r'^\\?\[\d+\\?\]\s+[A-Z]', line.strip()):
                    continue
                for match in pattern.finditer(line):
                    # 跳过 Pandoc 引用 [@key]
                    if '@' in match.group(1):
                        continue
                    citations.append(CitationPosition(
                        line_number=i,
                        column_start=match.start(),
                        column_end=match.end(),
                        raw_text=match.group(0),
                        section=self._get_section_for_line(i),
                        is_in_table=self._is_in_table(i),
                        is_in_code_block=self._is_in_code_block(i),
                        is_superscript=is_superscript,
                    ))
        return citations

    def find_reference_list(self) -> Optional[tuple[int, int]]:
        """查找静态参考文献列表的起止行"""
        ref_start = None
        for i, line in enumerate(self.lines):
            # 匹配 \[1\] Author... 或 [1] Author...
            if re.match(r'^\\?\[1\\?\]\s+[A-Z]', line.strip()):
                ref_start = i
                break

        if ref_start is None:
            return None

        # 找到列表结束位置（连续空行后的非引用行）
        ref_end = len(self.lines)
        for j in range(ref_start + 1, len(self.lines)):
            stripped = self.lines[j].strip()
            # 引用行: \[N\] ... 或 [N] ...
            is_ref_line = bool(re.match(r'^\\?\[\d+\\?\]\s+', stripped))
            # 空行允许
            is_empty = stripped == ''
            # 续行（不以 [N] 开头但有内容）
            is_continuation = bool(stripped) and not re.match(r'^\\?\[\d+\\?\]', stripped) and j > ref_start + 1

            if not is_ref_line and not is_empty and not is_continuation:
                ref_end = j
                break

        return (ref_start, ref_end)

    # ---- Internal ----

    def _scan_node(self, node: ASTNode):
        """递归扫描节点中的引用"""
        if node.type == "code_block":
            return  # 跳过代码块

        # 扫描本节点的内容
        self._scan_text_for_citations(node.content, node.line_start, node.line_end,
                                       node.type == "table")

        for child in node.children:
            self._scan_node(child)

    def _scan_text_for_citations(self, text: str, line_start: int, line_end: int,
                                  is_in_table: bool):
        """在文本中扫描引用"""
        # 匹配 [@citekey], [@key1; @key2], [N], ^[N]^
        combined_pattern = re.compile(
            r'(\[@([^\]]+)\])'           # Pandoc: [@key1; @key2]
            r'|(\^\[(\d+[^\]]*)\]\^)'   # 上标: ^[N]^
            r'|(\\\[(\d+[^\]]*)\\\])'   # 转义: \[N]\
            r'|((?<!\\)\[(\d+[^\]]*)\](?!\())'  # 纯数字: [N]
        )

        # 简化: 逐行扫描
        for line_num in range(line_start, min(line_end + 1, len(self.lines) + 1)):
            line = self.lines[line_num - 1] if line_num <= len(self.lines) else ""

            # 检查是否在表格/代码块中
            actual_in_table = is_in_table or self._is_in_table(line_num)
            actual_in_code = self._is_in_code_block(line_num)

            for match in combined_pattern.finditer(line):
                raw = match.group(0)
                if '@' in raw:
                    # Pandoc 格式
                    self._citations.append(CitationPosition(
                        line_number=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        raw_text=raw,
                        section=self._get_section_for_line(line_num),
                        is_in_table=actual_in_table,
                        is_in_code_block=actual_in_code,
                        is_superscript=False,
                    ))
                elif '^' in raw:
                    self._citations.append(CitationPosition(
                        line_number=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        raw_text=raw,
                        section=self._get_section_for_line(line_num),
                        is_in_table=actual_in_table,
                        is_in_code_block=actual_in_code,
                        is_superscript=True,
                    ))
                else:
                    # 纯数字引用 — 可能存在于表格或正文
                    self._citations.append(CitationPosition(
                        line_number=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        raw_text=raw,
                        section=self._get_section_for_line(line_num),
                        is_in_table=actual_in_table,
                        is_in_code_block=actual_in_code,
                        is_superscript=False,
                    ))

    def _tokenize(self) -> list[ASTNode]:
        """将 Markdown 文本分词为 AST 节点"""
        nodes: list[ASTNode] = []
        i = 0
        while i < len(self.lines):
            line = self.lines[i]
            stripped = line.strip()

            # 代码块
            if stripped.startswith('```'):
                code_start = i
                i += 1
                while i < len(self.lines) and not self.lines[i].strip().startswith('```'):
                    i += 1
                code_end = i
                self._code_block_regions.append((code_start + 1, code_end + 1))
                content = '\n'.join(self.lines[code_start:code_end + 1])
                nodes.append(ASTNode(
                    type="code_block", content=content,
                    line_start=code_start + 1, line_end=code_end + 1,
                ))
                i += 1
                continue

            # 标题
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                nodes.append(ASTNode(
                    type="heading", content=stripped,
                    line_start=i + 1, line_end=i + 1,
                    metadata={"level": len(heading_match.group(1)),
                              "title": heading_match.group(2)},
                ))
                i += 1
                continue

            table = self._table_region_at(i)
            if table is not None:
                tbl_end, table_format = table
                self._table_regions.append((i + 1, tbl_end + 1))
                self._table_formats.append((i + 1, tbl_end + 1, table_format))
                content = '\n'.join(self.lines[i:tbl_end + 1])
                nodes.append(ASTNode(
                    type="table", content=content,
                    line_start=i + 1, line_end=tbl_end + 1,
                    metadata={"format": table_format},
                ))
                i = tbl_end + 1
                continue

            # 段落
            para_start = i
            para_lines = []
            while i < len(self.lines):
                s = self.lines[i].strip()
                if (s == '' or s.startswith('```') or s.startswith('#') or
                        self._table_region_at(i) is not None):
                    break
                para_lines.append(self.lines[i])
                i += 1

            if para_lines:
                content = '\n'.join(para_lines)
                nodes.append(ASTNode(
                    type="paragraph", content=content,
                    line_start=para_start + 1, line_end=i,
                ))
            else:
                i += 1

        return nodes

    def _build_section_contexts(self) -> None:
        current = SectionContext()
        contexts: dict[int, SectionContext] = {}
        classifier_terms = get_section_classifier_terms()
        for line_num, line in enumerate(self.lines, 1):
            heading = parse_section_heading(line, classifier_terms)
            if heading is not None:
                current = heading
                contexts[line_num] = heading
            else:
                contexts[line_num] = SectionContext(
                    title=current.title,
                    section_type=current.section_type,
                    protected=current.protected,
                    is_heading=False,
                )
        self._section_contexts = contexts

    def _get_section_for_line(self, line_num: int) -> str:
        """获取行所在的章节标题"""
        return self.get_section_for_line(line_num)

    def _is_in_table(self, line_num: int) -> bool:
        """检查行是否在表格内"""
        return any(start <= line_num <= end for start, end in self._table_regions)

    def table_format_for_line(self, line_num: int) -> Optional[str]:
        """Return the recognized Markdown table format at ``line_num``."""
        for start, end, table_format in self._table_formats:
            if start <= line_num <= end:
                return table_format
        return None

    @staticmethod
    def _is_pipe_separator(line: str) -> bool:
        return bool(re.match(r'^\|?[\s:-]+\|[\s|:-]+\|?$', line.strip()))

    @staticmethod
    def _is_grid_border(line: str) -> bool:
        return bool(re.match(r'^\s*\+(?:[-=]+\+)+\s*$', line))

    @staticmethod
    def _is_simple_border(line: str) -> bool:
        return bool(re.match(r'^\s*-{3,}\s*$', line))

    @staticmethod
    def _is_simple_column_separator(line: str) -> bool:
        return bool(re.match(r'^\s*-{3,}(?:\s+-{3,})+\s*$', line))

    def _table_region_at(self, start: int) -> Optional[tuple[int, str]]:
        """Recognize pipe, Pandoc simple, and Pandoc grid tables at ``start``."""
        line = self.lines[start]
        stripped = line.strip()

        if self._is_grid_border(line):
            end = start + 1
            while end < len(self.lines):
                if self._is_grid_border(self.lines[end]):
                    if end + 1 >= len(self.lines) or not self.lines[end + 1].strip() or \
                            not self.lines[end + 1].lstrip().startswith('|'):
                        return end, "grid"
                end += 1
            return None

        if self._is_simple_border(line) and start + 2 < len(self.lines):
            if self.lines[start + 1].strip() and self._is_simple_column_separator(
                    self.lines[start + 2]):
                end = start + 3
                while end < len(self.lines):
                    if self._is_simple_border(self.lines[end]):
                        return end, "simple"
                    end += 1
                return None

        if '|' in stripped and start + 1 < len(self.lines) and \
                self._is_pipe_separator(self.lines[start + 1]):
            end = start + 2
            while end < len(self.lines) and '|' in self.lines[end]:
                end += 1
            return end - 1, "pipe"

        return None

    def _is_in_code_block(self, line_num: int) -> bool:
        """检查行是否在代码块内"""
        return any(start <= line_num <= end for start, end in self._code_block_regions)
