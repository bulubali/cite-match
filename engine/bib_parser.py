"""
CiteMatch v2 BibTeX 解析器 — 鲁棒的 .bib 文件解析

改进（相对 v1 正则方案）:
- 正确处理嵌套花括号
- 支持所有 entry 类型（article, book, inproceedings, ...）
- 处理字符串缩写（@string）
- 跨行字段值
- LaTeX 转义保留
"""
import re
from typing import Optional
from cm_types import BibEntry


class BibParseError(Exception):
    """BibTeX 解析错误"""
    pass


class BibTeXParser:
    """鲁棒的 BibTeX 解析器

    使用混合正则+状态机方法正确处理嵌套花括号和多行值。
    """

    def __init__(self):
        self._entries: dict[str, BibEntry] = {}
        self._strings: dict[str, str] = {}  # @string 宏定义
        self._warnings: list[str] = []

    # ---- Public API ----

    def parse(self, text: str) -> dict[str, BibEntry]:
        """解析 BibTeX 文本，返回 citekey → BibEntry 映射"""
        self._entries.clear()
        self._strings.clear()
        self._warnings.clear()

        text = self._strip_comments(text)

        # 第一遍: 解析 @string 宏
        text = self._resolve_strings_pass(text)

        # 第二遍: 解析所有 entry
        self._parse_entries(text)

        return dict(self._entries)

    def parse_file(self, filepath: str) -> dict[str, BibEntry]:
        """从文件解析"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return self.parse(f.read())

    @property
    def warnings(self) -> list[str]:
        return list(self._warnings)

    # ---- Internal helpers ----

    @staticmethod
    def _strip_comments(text: str) -> str:
        """移除注释"""
        lines = []
        for line in text.split('\n'):
            stripped = line.strip()
            if not stripped.startswith('%'):
                lines.append(line)
        return '\n'.join(lines)

    def _resolve_strings_pass(self, text: str) -> str:
        """解析 @string{name = value} 定义"""
        string_pattern = re.compile(
            r'@string\s*\{\s*(\w+)\s*=\s*"([^"]*)"\s*\}',
            re.IGNORECASE
        )
        for match in string_pattern.finditer(text):
            name = match.group(1)
            value = match.group(2)
            self._strings[name.lower()] = value
        return text

    def _parse_entries(self, text: str) -> None:
        """解析所有 BibTeX 条目 — 使用 entry-level 正则 + 平衡花括号匹配"""
        # 匹配每个 entry 的起始: @type{citekey,
        entry_start_pattern = re.compile(
            r'@(\w+)\s*\{\s*([^,}]+)\s*,', re.IGNORECASE
        )

        for match in entry_start_pattern.finditer(text):
            entry_type = match.group(1).lower()

            # 跳过非 entry 类型
            if entry_type in ('string', 'comment', 'preamble'):
                continue

            citekey = match.group(2).strip()

            # 从 citekey 后的逗号开始，找到匹配的闭合花括号
            fields_start = match.end()  # citekey 后逗号的位置
            # 找到 entry 整体的闭合花括号
            content_end = self._find_matching_close(text, match.start() + len(f'@{entry_type}'))

            if content_end < 0:
                self._warnings.append(f"Unclosed entry: {citekey}")
                continue

            # 提取字段内容（citekey 的逗号后到 entry 末尾 }
            fields_body = text[fields_start:content_end].strip()

            # 解析字段
            fields = self._parse_fields(fields_body)

            self._entries[citekey] = BibEntry(
                citekey=citekey,
                entry_type=entry_type,
                fields=fields,
            )

    @staticmethod
    def _find_matching_close(text: str, open_brace_pos: int) -> int:
        """找到与 open_brace_pos 处的 { 匹配的 } 位置

        Args:
            text: 文本
            open_brace_pos: 开括号 { 的位置

        Returns:
            匹配的 } 的位置，如果未找到返回 -1
        """
        if open_brace_pos >= len(text) or text[open_brace_pos] != '{':
            return -1

        depth = 1
        i = open_brace_pos + 1
        while i < len(text) and depth > 0:
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
            i += 1

        return i - 1 if depth == 0 else -1

    @staticmethod
    def _extract_braced_value(text: str, start: int) -> tuple[str, int]:
        """从 start 位置的 { 开始提取花括号包围的值

        Args:
            text: 文本
            start: { 的位置

        Returns:
            (值内容, 值后面的位置)
        """
        if start >= len(text) or text[start] != '{':
            return "", start

        depth = 1
        i = start + 1
        while i < len(text) and depth > 0:
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
            i += 1

        return text[start + 1:i - 1], i

    def _parse_fields(self, fields_body: str) -> dict[str, str]:
        """解析字段内容字符串为键值对字典

        Example input:
            author    = {Chen, Y. and Wang, L. and Zhang, H.},
            title     = {Flexible Piezoelectric Blood Pressure Sensor},
            journal   = {Advanced Materials},
            year      = {2023},
        """
        fields: dict[str, str] = {}
        if not fields_body.strip():
            return fields

        pos = 0
        body_len = len(fields_body)

        while pos < body_len:
            # 跳过空白和逗号
            while pos < body_len and fields_body[pos] in ' \t\n\r,':
                pos += 1
            if pos >= body_len:
                break

            # 查找字段名（遇到 = 为止）
            eq_pos = fields_body.find('=', pos)
            if eq_pos == -1:
                break

            field_name = fields_body[pos:eq_pos].strip().lower()
            if not field_name:
                pos = eq_pos + 1
                continue

            # 跳过 = 和空白
            pos = eq_pos + 1
            while pos < body_len and fields_body[pos] in ' \t\n\r':
                pos += 1

            if pos >= body_len:
                break

            # 提取值
            value = ""
            if fields_body[pos] == '{':
                value, pos = self._extract_braced_value(fields_body, pos)
            elif fields_body[pos] == '"':
                quote_end = fields_body.find('"', pos + 1)
                if quote_end == -1:
                    value = fields_body[pos + 1:]
                    pos = body_len
                else:
                    value = fields_body[pos + 1:quote_end]
                    pos = quote_end + 1
            else:
                # 数字或缩写
                end_chars = [fields_body.find(',', pos), fields_body.find('}', pos)]
                end_chars = [e for e in end_chars if e != -1]
                end = min(end_chars) if end_chars else body_len
                value = fields_body[pos:end].strip()
                pos = end

            if field_name:
                fields[field_name] = value.strip()

        return fields
