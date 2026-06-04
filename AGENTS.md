# AFSIM Agent

## 项目目标

构建 AFSIM 场景生成的专用 Agent。流水线：

```text
自然语言 → Intent Parsing → AFSIM-IR → Grounding → Grounded IR
→ Hierarchical Generation → Static Verification → Self Repair
→ mission.exe → Execution Repair → Executable Scenario
```

禁止绕过 IR + Grounding 直接生成脚本。

## Source of Truth

```text
AFSIM 官方文档 > 官方 Demo > Grounding 库 > 历史实验 > 模型推断
```

- 官方文档路径：`C:/Program Files/afsim-2.9.0-win64/documentation/html/docs/main_page.html`
- 优先参考官方 Command Index (`wsf-commandindex.html`)、Class Index、Model Index
- 禁止凭空创造未在官方文档或 Demo 中出现过的实体、类型、命令
- 所有静态检查规则、safe_repair 逻辑、prompt 约束应能追溯到官方文档页面或 Demo 文件
- `mission.exe` 是最终裁判。`mission.exe ≠ Static Checker` 时，以 `mission.exe` 为准

## 验证优先级

```text
mission.exe > 官方文档 > Static Checker > 模型推断
```

## 协作文档

| 文件 | 职责 |
|------|------|
| `TASK.md` | 任务定义、依赖关系、任务状态。完成任务时只更新 `Status` 字段 |
| `STATUS.md` | 当前阶段、实验数据、风险、下一步计划、协作备注 |
| `AGENTS.md` | 本文件。项目原则、规则、约定 |

禁止在 `TASK.md` 中追加进展说明或实验总结。`TASK.md` 与 `STATUS.md` 冲突时，任务状态以 `TASK.md` 为准，协作说明以 `STATUS.md` 为准。

## STATUS.md 维护规则

- **每次开启新会话或发现 STATUS.md 被修改时，必须先读取对齐状态。**
- **每完成大规模修改后必须更新 STATUS.md**，记录核心改动、实验数据、阻塞风险、下一步优先级。
- **删除已不适用的已完成内容**，保持精简。历史通过 git log 追溯。

## 修复原则

### 泛化性

禁止：`if task_id == ...`、针对单个 benchmark 特判、从失败脚本直提正则硬匹配。

每条新增规则必须能回答：来源（官方文档哪页/Demo 哪个文件）、覆盖范围（哪些场景类型）、假阳性风险（合法 Demo 是否误报）、未观测数据预期（扩展到 100 任务是否仍生效）。

### 均等性

所有 benchmark 任务使用相同 Prompt 模板、Pipeline 路径、代码路径。

### 自愈性

领域知识通过 `Static Checker → mission.exe → LLM Retry` 闭环逐步归纳。禁止堆积 Prompt 特判。

### 未知数据泛化

```text
修复的正确性提升 必须来自 规则本身的覆盖面 而非 对当前 benchmark 的适配
```

**确定性层**（未知数据保证生效）：官方命令白名单、WSF 类型上下文约束、块交叉关闭纠正、引用完整性检查、命令位置检查、外部资源检查——持续从官方文档扩充。

**LLM 依赖层**（未知数据可能退化）：Intent Parsing、Script Generation、Execution Repair——通过扩充 few-shot 和 grounding 覆盖改进，而非微调 prompt。

每轮改进后验证无退化：跑官方 Demo 探针 + 历史通过任务 + 历史误报案例。

### 可复现性

固定版本、固定 Prompt、固定 Benchmark。

## 长期方向

- Direction A: `Log → AAR`（自动生成战后分析报告）
- Direction B: `态势图 → AFSIM-IR → 场景`

## 最终目标

构建能理解需求、规划场景、生成场景、验证场景、修复场景、执行场景的 AFSIM 专用 Agent。目标不是生成代码，是生成可执行场景。
