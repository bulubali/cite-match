# CiteMatch v2.5.x — Developer Manual

> **Status: Maintenance Mode**
>
> 这是 CiteMatch 唯一的开发维护规范。所有开发、测试、发布活动必须遵守本文档。
>
> Current Version: **v2.5.x**
>
> 当前阶段: **Maintenance** — 不是 Development，不是 Refactor，不是 Rewrite。

---

# 1. Production Validation

Production Validation 是 CiteMatch 的**真实论文验证机制**。

## 1.1 触发条件

当用户明确表示以下任一意图时，自动进入 **Production Validation Mode**：

- 真实测试
- Production Validation
- Acceptance Test
- Regression Test
- 文献补充 / 文献匹配 / citation matching（全流程执行）

## 1.2 职责

Production Validation Mode 下，必须遵守以下规则：

1. **完整执行 skills.md 全部 Phase**
   - Phase 00 → Phase 0 → Phase 1 → ... → Phase 7
   - 不跳过任何 Phase
   - 不省略任何交互询问（包括 Table IF Gate、CSL 样式选择、全作者确认）

2. **全程 Production Review**
   - 每个 Phase 完成后自动验证输出
   - 对比 Expected vs Actual
   - 任何偏差都记录到 Validation Report

3. **不自动修复代码**
   - 发现 Bug → 创建 Issue → 继续 Workflow
   - 不得在 Validation 过程中修改 Engine 代码
   - 修复必须等待用户批准

4. **Expected ≠ Actual 判断 Bug**
   - Bug 的唯一标准：Expected ≠ Actual
   - 程序是否报错不是判断标准
   - 没有报错也可能存在 Bug

5. **Workflow 不因 Bug 中断**
   - Bug 不影响后续 Phase 继续执行
   - 所有 Bug 汇总到最终 Report
   - 一次运行生成完整 Production Report

6. **最终生成完整 Production Report**
   - `Production_Validation_Report.md`
   - `validation_statistics.json`
   - `comparison_report.md`

---

# 2. Bug Definition

## 2.1 统一标准

**Bug 的唯一判断标准：**

```
Expected ≠ Actual
```

## 2.2 重要说明

- 程序报错**不是**唯一 Bug
- 没有报错**也可能**存在 Bug
- **任何结果与 skills.md 不一致，都属于 Production Bug**

## 2.3 示例

| 场景 | 报错？ | Expected | Actual | Bug？ |
|------|--------|----------|--------|-------|
| 引用映射 59→48（重复 key） | ❌ 无报错 | 59 唯一 key | 48 唯一 key | ✅ Bug |
| Pandoc 编译失败 | ✅ 报错 | DOCX 生成 | 无输出 | ✅ Bug |
| Table IF Gate 未询问 | ❌ 无报错 | 交互询问 | 静默跳过 | ✅ Bug |
| 参考文献列表未删除 | ❌ 无报错 | 仅 `# References` | 残留静态文本 | ✅ Bug |
| 语义映射全进 preamble | ❌ 无报错 | 分章节分布 | 全部 (preamble) | ✅ Bug |

## 2.4 Bug 优先级

### P0 — 生产级 Bug
影响最终输出正确性：
- 引文识别错误 / 丢失引用 / 重复引用
- IF Gate 未询问 / Table IF Gate 未询问
- 表格注入错误 / Figure 注入错误
- Pandoc 编译失败 / CSL 错误
- Mapping Report 错误 / Missing CiteKey
- 参考文献列表残留 / ^ 字符残留

### P1 — 影响结果正确性
- 连续引用格式错误 / Citation Merge 错误
- Crossref 被修改 / 图注注入错误
- Review paper 路由错误 / Density 溢出
- Floating ratio 过高

### P2 — 体验问题
- Prompt 文案 / 提示顺序 / 输出格式
- 禁止为了 P2 重构 Engine

---

# 3. Issue Workflow

## 3.1 自动创建 Issue

Production Validation 过程中发现 Bug 时，**自动执行**：

1. 创建 `docs/issues/ISSUE-XXX.md`（编号自增）
2. 更新 `docs/issues/README.md`（Issue Index）
3. Issue 状态设为 `Open`

## 3.2 Issue 目录结构

```
docs/
└── issues/
    ├── README.md          ← Issue Index（自动维护）
    ├── ISSUE-001.md
    ├── ISSUE-002.md
    └── ...
```

## 3.3 Issue 最少内容

每个 Issue 必须包含：

```markdown
# ISSUE-XXX

## Title
一句话描述

## Priority
P0 / P1 / P2

## Status
Open | In Progress | Regression Testing | Closed

## Version Found
v2.5.x

## Environment
OS / Python / Pandoc / etc.

## Steps to Reproduce
必须能够稳定复现。禁止模糊描述。

## Expected Behavior
应该发生什么（引用 skills.md 对应规则）

## Actual Behavior
实际发生什么

## Severity
- Root Cause (Initial) — 初步定位
- Related Phase — 影响的 Phase
- Files Involved — 涉及文件

## Minimal Fix Plan
最小修改方案。禁止重构。

## Regression Test
新增 test_issue_xxx.py

## Acceptance Result
PASS / FAIL

## Notes
```

## 3.4 README.md Index 格式

```markdown
# CiteMatch Issues

| Issue | Title | Priority | Phase | Status | Found | Fixed |
|-------|-------|----------|-------|--------|-------|-------|
| ISSUE-001 | xxx | P0 | Phase 3 | Open | v2.5.0 | — |
```

## 3.5 Issue 创建后

- **继续 Workflow**，不等待修复
- **不得自动修复**
- 等待用户批准后进入 Regression Workflow

---

# 4. Regression Workflow

任何 Bug 修复完成后，必须通过以下 **4 项全部**，否则不得关闭 Issue：

## 4.1 四项门槛

```
┌──────────────────────────────────────────┐
│  1. Bug Regression                       │
│     ↓                                    │
│  2. Unit Test (new + existing)           │
│     ↓                                    │
│  3. Golden Dataset Verification          │
│     ↓                                    │
│  4. Production Validation (real paper)   │
│     ↓                                    │
│  Issue Closed                            │
└──────────────────────────────────────────┘
```

## 4.2 详细要求

### 1. Bug Regression
- 确认修复后 Expected == Actual
- 同一场景不再复现
- 相关场景无新增 Bug

### 2. Unit Test
- 新增 `tests/regression/test_issue_XXX.py`
- 全部已有 Unit Tests 通过
- 全部 Integration Tests 通过

### 3. Golden Dataset
- `python tests/golden_dataset/verify_golden_dataset.py` → PASS
- Regression output 与 expected 差异 ≤5%

### 4. Production Validation
- `python tests/production_validation/validation_runner.py` → 无新增 FAIL
- Overall Score ≥ 90%

## 4.3 关闭条件

```
All 4 gates PASS → Issue Closed
Any gate FAIL  → Issue stays Open, fix iterates
```

---

# 5. Developer Mode Rules

## 5.1 禁止事项

Maintenance Mode 下**绝对禁止**：

- ❌ 新增 Framework
- ❌ 新增 Validation 系统
- ❌ 重构 Engine
- ❌ 新增 Phase
- ❌ 新增 Feature
- ❌ 为了代码更漂亮而修改
- ❌ 因为觉得以后可能出问题而修改
- ❌ 为了提高代码覆盖率而增加功能
- ❌ 为了提高架构完整性而增加模块

## 5.2 允许事项

Maintenance Mode 下**仅允许**：

- ✅ Root Cause Analysis
- ✅ Minimal Fix（最小修改，不重写已有模块）
- ✅ Regression Test 新增
- ✅ Production Validation 执行
- ✅ Issue Tracking（创建、更新、关闭）
- ✅ 修复已通过真实论文验证发现的问题

## 5.3 Issue 修复顺序

**一次仅允许修复一个 Issue。**

除非当前 Issue 已通过以下**两项全部**，否则**禁止**进入下一 Issue：

1. **Regression Test** — 新增 `tests/regression/test_issue_XXX.py` 并全部通过
2. **Production Validation** — 使用真实论文验证 Expected == Actual

```
ISSUE-004 修复
    ↓
Regression Test PASS
    ↓
Production Validation PASS
    ↓
ISSUE-004 Closed
    ↓
    ├── 此时才允许开始 ISSUE-001
    ↓
ISSUE-001 修复
    ↓
...
```

违反此规则的后果：上下文污染、多 Issue 交叉调试、无法确定哪个修改引入了新 Bug。

## 5.4 开发铁律

```
真实论文复现
    ↓
Root Cause 定位
    ↓
最小修改（优先新增，不重写）
    ↓
Regression Test 新增
    ↓
4 项 Regression Gate 全部通过
    ↓
真实论文再次验证
    ↓
Merge
```

**禁止猜测。禁止跳过。禁止为了 P2 重构 Engine。**

---

# 6. 工作流程总览

## 6.1 完整开发流程

```
用户触发 Production Validation
    ↓
完整执行 Phase 00 → Phase 7
    ↓
全程 Production Review
    ↓
发现 Bug？
    ├── Yes → 创建 Issue → 继续 Workflow
    └── No  → 继续 Workflow
    ↓
生成 Production Report
    ↓
用户批准修复？
    ├── Yes → Root Cause → Minimal Fix → Regression Gates → Close Issue
    └── No  → Issue stays Open
```

## 6.2 每次修复后必须输出

1. Root Cause
2. Modified Files
3. Regression Test Added
4. Tests Passed（4 项 Gate 结果）
5. 是否影响已有功能
6. 是否需要更新 skills.md

---

# 7. 自动执行规则

以后每提出一个 Bug，必须严格按顺序：

1. 自动创建 `ISSUE-XXX`
2. 更新 `docs/issues/README.md`
3. Root Cause Analysis
4. Minimal Fix（用户批准后）
5. 新增 Regression Test
6. 4 项 Regression Gate 全部通过
7. Issue Closed

**不要跳过任何步骤。**

---

# 8. 附录

## 8.1 当前版本

- **Current Version:** v2.5.x
- **Phase:** Maintenance
- **目标:** 让 CiteMatch 在真实论文上稳定运行

## 8.2 关键文件索引

| 文件 | 用途 |
|------|------|
| `SKILL.md` | v1 完整规范（Phase 定义） |
| `skills.md` (if exists) | 当前 Skill 规范 |
| `engine/` | 所有 Engine 模块 |
| `tests/golden_dataset/` | 回归测试基准数据 |
| `tests/production_validation/` | 生产验证框架 |
| `docs/issues/` | Issue 跟踪 |
| `output/` | 引擎输出目录 |
| `profiles/` | 策略配置 |

## 8.3 相关文档

- [README.md](README.md) — 项目概览
- [CHANGELOG.md](CHANGELOG.md) — 版本变更
- [tests/production_validation/README.md](tests/production_validation/README.md) — 验证框架使用说明
- [tests/production_validation/production_checklist.md](tests/production_validation/production_checklist.md) — 签核清单
