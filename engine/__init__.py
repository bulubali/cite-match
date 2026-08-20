"""
CiteMatch v2 Engine — 下一代文献引用匹配与注入引擎

架构层次:
- State Machine → 工作流状态控制
- MD-AST Parser → Markdown 结构化解析
- Citation Registry → 引用注册表（守恒验证）
- BibTeX Parser → 鲁棒的 .bib 解析
- Matcher → 多策略引用匹配
- Injector → AST-aware 引用注入
- Bilingual Sync → 双语引用同步
"""

__version__ = "2.5.0"
