# TASK.md

# AFSIM Agent Development Tasks

## 项目状态

当前阶段：

Phase 1 - 领域调研与问题定义

总体进度：

30%

---

# Task-001 分析 AFSIM 组件体系

## 目标

梳理 AFSIM 核心组件及依赖关系。

分析对象：

- Platform
- Sensor
- Weapon
- Mover
- Processor
- Route
- Task

## 输出

形成：

《AFSIM组件关系分析文档》

内容包括：

- 组件职责
- 组件依赖
- 场景组装流程

## 状态

DONE

## 已产出

- `docs/AFSIM组件关系分析文档.md`

---

# Task-002 收集标准场景案例

## 目标

建立 Benchmark 初版数据集。

## 要求

收集：

20~50 个标准场景。

来源：

- 官方案例
- Demo工程
- 项目已有场景

## 输出

benchmark_v1

格式：

输入：

自然语言描述

输出：

对应场景脚本

## 状态

DONE

## 已产出

- `benchmarks/benchmark_v1/README.md`
- `benchmarks/benchmark_v1/tasks.jsonl`
- `benchmarks/benchmark_v1/demo_sources/`
- `benchmarks/benchmark_v1/validation_results.json`
- `benchmarks/benchmark_v1/validation_logs/`
- `scripts/validate_benchmark.py`

## 验证结果

- 27 个 benchmark oracle 均来自真实 AFSIM demos
- 27 个 benchmark oracle 脚本已全部通过 `mission.exe`
- 最近一次结果：27 PASS / 0 FAIL / 0 TIMEOUT

---

# Task-003 建立错误分类体系

## 目标

整理 AFSIM 场景生成中的典型错误。

## 分类

至少包含：

- 缺少单位
- 缺少 end_xxx
- 引用不存在对象
- 坐标格式错误
- 幻觉实体
- 必填项缺失

## 输出

error_taxonomy_v1

## 状态

DONE

## 已产出

- `docs/AFSIM错误分类体系_v1.md`
- `docs/error_taxonomy_v1.json`

## 验证结果

- 已覆盖任务要求中的 6 类错误：缺少单位、缺少 `end_xxx`、引用不存在对象、坐标格式错误、幻觉实体、必填项缺失
- 已扩展到 10 类错误，补充组件语法错配、脚本 API/语言错误、文件与执行环境错误、任务语义偏差
- 已给出 baseline 统计口径和最小标注格式

---

# Task-004 建立 Direct Prompt Baseline

## 目标

评估当前 Skill 的直接生成能力。

## 流程

自然语言

↓

AFSIM脚本

## 统计指标

- 语法正确率
- 可执行率
- 错误率

## 输出

baseline_direct_v1

## 状态

DONE

## 已产出

- `scripts/run_direct_baseline.py`
- `baseline_direct_v1/README.md`
- `baseline_direct_v1/prompt_template.md`
- `baseline_direct_v1/generated_scripts/`
- `baseline_direct_v1/mission_logs/`
- `baseline_direct_v1/results.jsonl`
- `baseline_direct_v1/summary.json`
- `baseline_direct_v1/error_stats.json`

## 验证结果

- benchmark 总数：27
- 生成器：DeepSeek API，模型 `deepseek-v4-pro`
- 语法正确率：0 / 27 = 0.00%
- 静态通过率：0 / 27 = 0.00%
- `mission.exe` 可执行率：0 / 27 = 0.00%
- 语义匹配率：0 / 27 = 0.00%
- 主错误分布：`E001=16`、`E002=23`、`E003=2`、`E004=12`、`E006=3`、`E007=26`

## 结论

- DeepSeek direct prompt 能产生 AFSIM 风格文本，但在没有 RAG、IR、grounding 和 demo 约束时，倾向生成 mission.exe 不接受的伪 DSL
- 典型失败包括缺少/错配 `end_xxx`、单位格式错误、坐标格式错误和组件语法错配
- 该结果为后续 RAG、IR、self-repair 提供了明确对照基线

---

# Task-005 建立 RAG Baseline

## 目标

评估知识增强后的生成能力。

## 流程

自然语言

↓

知识检索

↓

AFSIM脚本

## 检索来源

- 示例场景
- API文档
- Skill文档

## 输出

baseline_rag_v1

## 状态

DONE

## 已产出

- `scripts/run_rag_baseline.py`
- `baseline_rag_v1/README.md`
- `baseline_rag_v1/generated_scripts/`
- `baseline_rag_v1/mission_logs/`
- `baseline_rag_v1/results.jsonl`
- `baseline_rag_v1/summary.json`
- `baseline_rag_v1/error_stats.json`

## 验证结果

- benchmark 总数：27
- 生成器：DeepSeek API，模型 `deepseek-v4-pro`
- 检索策略：source-tree priority + component-aware + keyword overlap
- corpus chunks: 2090，max_context_chars: 12000
- 语法正确率：6 / 27 = 22.22%
- 静态通过率：5 / 27 = 18.52%
- `mission.exe` 可执行率：4 / 27 = 14.81%
- 语义匹配率：3 / 27 = 11.11%
- 主错误分布：`E001=8`、`E002=13`、`E003=2`、`E004=5`、`E005=5`、`E006=1`、`E007=10`

## 结论

- RAG 检索显著提升生成质量：可执行率从 direct baseline 的 0% 提升到 14.81%
- 检索策略的 source-tree priority 有效确保了同目录相关文件优先被选中
- E005 共 5 个，经逐类型核查均为真实幻觉（WSF_ACTIVE_RADAR、WSF_COMMAND_CHAIN、WSF_WEAPON_TASK、WSF_MESSAGE、WSF_BATTLE_MANAGER），不在任何 demo、reference 或 SKILL.md 中出现
- WSF_STATIONARY_MOVER 经 SKILL.md 确认合法，已加入白名单
- 主要失败原因仍是块未闭合（E002=13）和组件语法错配（E007=10）
- 4 个通过样例证明了 RAG 路线的有效性

---

# Task-005A 构建 Dataset v1 多任务样本

## 目标

将调研建议中的数据集设计正式落到项目文件中，覆盖：

- Type A：指令 -> 脚本
- Type B：脚本 -> 指令
- Type C：指令 -> IR
- Type D：IR -> 脚本
- Type E：错误脚本 + 报错 -> 修复脚本
- Type F：log -> AAR
- 泛化切分：Seen/Unseen、Single/Multi、Static/Dynamic 等

## 输出

dataset_v1

## 状态

DONE

## 已产出

- `docs/dataset_design_v1.md`
- `datasets/dataset_v1/README.md`
- `datasets/dataset_v1/type_a_instruction_to_script.jsonl`
- `datasets/dataset_v1/type_b_script_to_instruction.jsonl`
- `datasets/dataset_v1/type_c_instruction_to_ir.jsonl`
- `datasets/dataset_v1/type_d_ir_to_script.jsonl`
- `datasets/dataset_v1/type_e_error_repair.jsonl`
- `datasets/dataset_v1/type_f_log_to_aar.jsonl`
- `datasets/dataset_v1/splits_v1.json`

## 验证结果

- Type A/B/C/D/E/F 均已建立 starter set，且每类 5 条
- 所有 JSONL 文件均已通过 `ConvertFrom-Json` 解析检查
- `splits_v1.json` 已通过 JSON 解析检查

## 说明

- Type A 同时由 `benchmarks/benchmark_v1/tasks.jsonl` 提供全量 27 条，由 `datasets/dataset_v1/type_a_instruction_to_script.jsonl` 提供 5 条 starter set
- Type C/D 当前使用 draft IR，后续 Task-006 会正式固化 schema
- Type E 当前以 RAG baseline 错误脚本和 oracle demo 构造修复目标，后续可补充最小编辑 diff
- Type F 当前为官方 demo mission log 到简短 AAR 的 5 条 starter set，后续可扩展到 `.evt` / `.aer` 事件级解释

---

# Task-006 设计 AFSIM-IR v1

## 目标

建立统一中间表示。

## 最低要求

支持：

- Platform
- Quantity
- Side
- Mission
- Location

## 输出

afsim_ir_schema_v1

以及：

ir_examples_v1

## 状态

DONE

## 已产出

- `docs/afsim_ir_schema_v1.json`
- `docs/afsim_ir_schema_v1.md`
- `docs/ir_examples_v1.jsonl`

## 验证结果

- `afsim_ir_schema_v1` 已固定最小必需字段：Platform、Quantity、Side、Mission、Location
- schema 同时覆盖 `scenario`、`sides`、`locations`、`routes`、`components`、`entities`、`tasks`、`constraints`、`expected_events`、`grounding_hints`
- `ir_examples_v1` 已提供 5 个跨场景示例：acoustic、air-to-air、escort、group comm、basic IADS C2
- 本任务未修改 `dataset_v1`，后续 `benchmark_v2` 可直接复用本 schema 与示例结构

---

# Task-007 建立 Intent Parsing 规范

## 目标

定义：

自然语言

↓

AFSIM-IR

的转换规则。

## 提取字段

- 平台
- 数量
- 阵营
- 区域
- 任务
- 武器
- 传感器

## 输出

intent_parsing_spec_v1

## 状态

TODO

---

# Task-008 建立 Grounding 库

## 目标

建立：

用户实体

↓

AFSIM实体

映射关系。

## 示例

歼20

↓

J20_TEMPLATE

CAP

↓

CAP_BEHAVIOR

PL15

↓

PL15_WEAPON

## 输出

entity_mapping_v1

## 状态

BLOCKED

依赖：

Task-006

---

# Task-009 设计分层生成流程

## 目标

禁止直接生成完整场景。

采用：

IR

↓

Platform Layer

↓

Sensor Layer

↓

Weapon Layer

↓

Mission Layer

↓

Scenario Assembly

## 输出

hierarchical_generation_spec_v1

## 状态

BLOCKED

依赖：

Task-006

Task-008

---

# Task-010 建立 Static Verification 规范

## 目标

建立统一静态检查规则。

## 检查内容

- 单位
- end_xxx
- 坐标格式
- 引用完整性
- 必填字段

## 输出

verification_rules_v1

## 状态

BLOCKED

依赖：

Task-003

---

# Task-011 设计 Self Repair Workflow

## 目标

实现：

脚本

↓

错误分析

↓

修复

↓

重新验证

## 输出

repair_workflow_v1

## 状态

BLOCKED

依赖：

Task-010

---

# Task-012 设计 Execution Repair Workflow

## 目标

利用 mission.exe 实现执行反馈闭环。

## 流程

脚本

↓

mission.exe

↓

日志

↓

错误分析

↓

修复

↓

重新执行

## 输出

execution_repair_spec_v1

## 状态

BLOCKED

依赖：

Task-011

---

# Task-013 建立 Benchmark v2

## 目标

构建一个更完整的 AFSIM 多任务 benchmark，用于后续全面评估场景生成能力，而不只评测端到端 `Type A`。

## 数据范围

后续 `benchmark_v2` 至少包含以下五类数据对：

- Type A：指令 -> 脚本
- Type B：脚本 -> 指令
- Type C：指令 -> IR
- Type D：IR -> 脚本
- Type E：错误脚本 + 报错 -> 修复脚本

## 说明

- Type A 用于端到端场景生成主评测。
- Type B 用于从现有脚本反向生成自然语言描述，并可通过人工抽样修订缓解标注不足。
- Type C 用于训练意图理解与中间表示生成。
- Type D 用于训练领域落地模块。
- Type E 用于训练 self-repair 与错误修复闭环。
- `benchmark_v2` 的目标不是只做单一 benchmark，而是形成覆盖 A-E 的统一评测集。

## 输出

`benchmark_v2`

## 状态

BLOCKED

## 依赖

Task-002

---

# Task-014 建立评测体系

## 指标

统计：

- IR正确率
- Grounding正确率
- 脚本正确率
- Static Pass Rate
- Repair Success Rate
- mission.exe Success Rate

## 输出

evaluation_protocol_v1

## 状态

BLOCKED

依赖：

Task-013

---

# Task-015 主系统集成

## 目标

形成完整 Agent Workflow。

## 流程

Natural Language

↓

Intent Parsing

↓

AFSIM-IR

↓

Grounding

↓

Hierarchical Generation

↓

Static Verification

↓

Self Repair

↓

Execution Repair

↓

Executable Scenario

## 输出

AFSIM Agent v1

## 状态

BLOCKED

依赖：

Task-012

Task-014

---

# 可选扩展任务

## Task-101 Log → AAR

日志

↓

自动生成 AAR

状态：

FUTURE

---

## Task-102 图 → IR

态势图

↓

AFSIM-IR

状态：

FUTURE

---

# 当前优先级

P0（立即执行）

- Task-001
- Task-002
- Task-003
- Task-004
- Task-005
- Task-006

P1

- Task-007
- Task-008
- Task-009
- Task-010

P2

- Task-011
- Task-012
- Task-013
- Task-014
- Task-015
