"""
CiteMatch v2 核心类型定义
"""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Any


class WorkflowPhase(Enum):
    """工作流阶段 — 状态机状态"""
    IDLE = auto()                # 空闲
    LOADING_BIB = auto()         # 加载 .bib 文件
    PARSING_BIB = auto()         # 解析 BibTeX 条目
    LOADING_DRAFT = auto()       # 加载草稿
    PARSING_AST = auto()         # 解析 Markdown AST
    SCANNING_CITATIONS = auto()  # 扫描现有引用
    MATCHING = auto()            # 匹配引用
    INJECTING = auto()           # 注入引用
    VERIFYING = auto()           # 验证守恒
    SYNCING = auto()             # 双语同步
    DONE = auto()                # 完成
    ERROR = auto()               # 错误状态


class MatchStrategy(Enum):
    """引用匹配策略（按置信度降序）"""
    DOI = (auto(), 1.0)           # DOI 精确匹配 → 置信度 1.0
    AUTHOR_YEAR_JOURNAL = (auto(), 0.95)  # 作者+年份+期刊
    AUTHOR_YEAR_TITLE = (auto(), 0.85)    # 作者+年份+标题关键词
    FIRST_AUTHOR_YEAR = (auto(), 0.70)    # 第一作者+年份
    TITLE_KEYWORD = (auto(), 0.50)        # 标题关键词
    MANUAL = (auto(), 1.0)       # 手动指定 → 置信度 1.0

    def __new__(cls, value, confidence):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.confidence = confidence
        return obj


@dataclass
class CitationPosition:
    """文档中的引用位置"""
    line_number: int
    column_start: int
    column_end: int
    raw_text: str                    # 原始文本，如 "[1]" 或 "[@key]"
    section: str = ""                # 所在章节
    is_in_table: bool = False        # 是否在表格内
    is_in_code_block: bool = False   # 是否在代码块内
    is_superscript: bool = False     # 是否上标格式
    is_in_protected_zone: bool = False  # Abstract/Keywords: no NEW injection


@dataclass
class BibEntry:
    """单个 BibTeX 条目"""
    citekey: str
    entry_type: str = "article"       # article, book, inproceedings, etc.
    fields: dict = field(default_factory=dict)

    @property
    def first_author_surname(self) -> str:
        authors = self.fields.get("author", "")
        if not authors:
            return ""
        # "Last, First and Last2, First2" → "Last"
        return authors.split(" and ")[0].split(",")[0].strip()

    @property
    def year(self) -> str:
        return self.fields.get("year", "")

    @property
    def doi(self) -> str:
        return self.fields.get("doi", "").lower()

    @property
    def title(self) -> str:
        return self.fields.get("title", "")

    @property
    def journal(self) -> str:
        return self.fields.get("journal", "")


@dataclass
class MatchResult:
    """单次匹配结果"""
    citekey: str
    confidence: float
    strategy: MatchStrategy
    bib_entry: Optional[BibEntry] = None
    evidence: str = ""  # 匹配依据（如 DOI=10.xxx/yyy）


@dataclass(frozen=True)
class CitationRecord:
    """引用注册表中的一条记录 — 不可变 (frozen)"""
    citekey: str
    positions: tuple[CitationPosition, ...] = field(default_factory=tuple)
    bib_entry: Optional[BibEntry] = None
    is_injected: bool = False     # 是否已被注入
    is_locked: bool = False       # 是否锁定（禁止修改）
    metadata: dict = field(default_factory=dict)


@dataclass
class RegistrySnapshot:
    """引用注册表快照 — 用于守恒验证"""
    total_citekeys: int
    injected_count: int
    orphan_count: int             # 有 key 但未在正文中引用
    missing_count: int            # 正文引用但无对应 BibTeX 条目
    citekeys: list[str]
    orphans: list[str]
    missing: list[str]
    table_citations: list[str]    # 表格内的引用（受保护）


@dataclass
class WorkflowBlockedError(Exception):
    """工作流被阻断 — 不可恢复，必须重新 raise"""
    def __init__(self, phase: str, reason: str):
        self.phase = phase
        self.reason = reason
        super().__init__(f"[BLOCKED at {phase}] {reason}")


class WriteBlockedError(Exception):
    """文件写入被阻断 — 缺少 backup / dry_run / validation"""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Write blocked: {reason}")


@dataclass
class PipelineReport:
    """管道执行报告"""
    phase: WorkflowPhase
    success: bool
    message: str = ""
    data: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
