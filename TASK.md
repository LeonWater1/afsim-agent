# TASK.md

# AFSIM Agent Development Tasks

## 项目状态

当前阶段：

Phase 1 - 领域调研、Baseline 与最小闭环构建

总体进度：

进行中

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

TODO

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

---

# Task-004 建立 Direct Prompt Baseline

## 目标

评估当前大模型在不使用 RAG、IR、Grounding、Repair 的情况下，直接生成 AFSIM 脚本的能力。

## 流程

自然语言

↓

LLM Direct Prompt

↓

AFSIM脚本

## 要求

Direct Prompt Baseline 不允许使用：

- 检索
- 示例脚本
- oracle 脚本
- IR
- Grounding
- Repair
- 规则模板生成

## 统计指标

- Syntax Correct Rate
- Static Pass Rate
- mission.exe Success Rate
- Semantic Match Rate
- 错误类型分布

## 输出

baseline_direct_v1

## 状态

DONE

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

# Task-006 设计 AFSIM-IR v1

## 目标

建立统一中间表示。

AFSIM-IR 用于连接：

自然语言需求

↓

结构化场景表示

↓

AFSIM脚本

## 最低要求

支持：

- Scenario
- Side
- Platform
- Quantity
- Location
- Route
- Mission
- Sensor
- Weapon
- Constraint

## 输出

afsim_ir_schema_v1

以及：

ir_examples_v1

## 状态

DONE

---

# Task-007 建立 Intent Parsing 规范

## 目标

定义：

自然语言

↓

AFSIM-IR

的转换规则。

## 提取字段

- 场景名称
- 平台
- 数量
- 阵营
- 区域
- 位置
- 任务
- 武器
- 传感器
- 约束条件

## 输出

intent_parsing_spec_v1

## 状态

DONE

## 已产出

- `docs/model_prompt/intent_parsing_spec_v1.md`

## 验证结果

- 已定义自然语言到 `AFSIM-IR v1` 的标准解析流程
- 已覆盖场景名称、平台、数量、阵营、区域、位置、任务、武器、传感器和约束条件
- 已明确不确定实体进入 `grounding_hints` / `*_hint`，不直接臆造未经验证的 AFSIM 类型
- 已给出最小 IR 示例和质量检查清单

---

# Task-008 建立 Static Verification 规范

## 目标

建立统一静态检查规则。

该任务需要提前完成，因为它同时服务于：

- Direct Prompt 结果分析
- RAG 结果分析
- IR-to-Script 生成
- Self Repair
- Execution Repair

## 检查内容

- 单位
- end_xxx
- 坐标格式
- 引用完整性
- 必填字段
- 非法组件类型
- 幻觉对象
- 脚本结构一致性

## 输出

verification_rules_v1

以及：

static_checker_v1

## 状态

DONE

## 已产出

- `docs/model_prompt/verification_rules_v1.md`
- `scripts/static_checker_v1.py`
- `docs/machine/error_taxonomy_v1.json`

## 验证结果

- 已覆盖单位、`end_xxx`、坐标格式、引用完整性、必填字段、非法组件类型、幻觉对象、脚本结构一致性
- `static_checker_v1` 可检查单文件或目录，并输出 JSON 格式结果
- Direct Prompt / RAG baseline 已改为统一调用 `static_checker_v1.analyze_script_text()`，不再维护独立静态检查规则
- `syntax_correct` / `static_pass` 现由 `docs/machine/error_taxonomy_v1.json` 中的分类字段驱动
- 统计口径与 Direct Prompt / RAG baseline 保持一致：`syntax_correct`、`static_pass`、`primary_error`、`static_error_ids`
- `docs/machine/error_taxonomy_v1.json` 已修正为可解析 JSON

## 依赖

- Task-003

---

# Task-009 建立评测体系

## 目标

建立统一评测协议，用于比较 Direct Prompt、RAG、IR-only、Ablation 和完整 Agent 方法。

## 说明

该任务不应完全依赖 Benchmark v2。

可以先基于 benchmark_v1 建立 evaluation_protocol_v1，后续再扩展到 benchmark_v2。

## 指标

统计：

- IR Validity
- IR Accuracy
- Grounding Accuracy
- Script Correctness
- Static Pass Rate
- Semantic Match Rate
- Repair Success Rate
- mission.exe Success Rate

## 输出

evaluation_protocol_v1

## 状态

DONE

## 已产出

- `docs/human_readme/evaluation_protocol_v1.md`
- `docs/machine/evaluation_protocol_v1.json`
- `scripts/evaluate_protocol_v1.py`
- `evaluation/evaluation_protocol_v1_baselines.json`

## 验证结果

- 已定义 8 个统一指标：`IR Validity`、`IR Accuracy`、`Grounding Accuracy`、`Script Correctness`、`Static Pass Rate`、`Semantic Match Rate`、`Repair Success Rate`、`mission.exe Success Rate`
- 已明确 `benchmark_v1` 阶段对 Direct / RAG 的不适用指标使用 `null`，不将缺失阶段误记为 `0`
- `evaluate_protocol_v1.py` 可读取方法目录并生成统一 scoreboard
- 协议默认使用当前 `static_checker_v1` 重算静态指标，避免旧 `summary.json` 口径滞后
- 已对 `baseline_direct_v1` 与 `baseline_rag_v1` 生成对齐后的评测结果：RAG 当前排名第 1，Direct 当前排名第 2

## 依赖

- Task-002
- Task-003
- Task-004
- Task-005
- Task-006
- Task-008

---

# Task-010 建立最小 Grounding 库 v1

## 目标

建立：

用户实体

↓

AFSIM实体

映射关系。

## 原则

第一版 Grounding 库不追求覆盖全部 AFSIM 组件。

优先覆盖 benchmark_v1 和主实验所需的最小集合。

## 最小覆盖范围

### 平台类

- aircraft
- fighter
- radar_site
- ship
- missile_site

### 任务类

- CAP
- patrol
- intercept
- strike
- escort
- detect
- engage

### 组件类

- radar
- missile
- mover
- processor
- sensor
- weapon

### 阵营类

- blue
- red
- neutral

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

AESA雷达

↓

AESA_RADAR_SENSOR

## 输出

entity_mapping_v1

## 状态

DONE

## 产出

- `docs/machine/entity_mapping_v1.json`
- `docs/model_prompt/entity_mapping_v1.md`
- `scripts/grounding_library_v1.py`

## 验证

- `python -m py_compile scripts/grounding_library_v1.py`
- `python scripts/grounding_library_v1.py --validate`
- `python scripts/grounding_library_v1.py --side 蓝方`
- `python scripts/grounding_library_v1.py --platform-hint fighter_aircraft`
- `python scripts/grounding_library_v1.py --task escort`
- `python scripts/grounding_library_v1.py --component-family sensor --component-hint radar_sensor`

验证结果：

- 结构检查通过
- `docs/machine/ir_examples_v1.jsonl` 中当前出现的 platform / task / component hint 已全部覆盖
- 组件 grounding 仅映射到 demo-backed target 或项目 canonical target，不新增幻觉 `WSF_*`

## 依赖

- Task-006

---

# Task-011 设计分层生成流程

## 目标

禁止直接一次性生成完整场景。

采用：

AFSIM-IR

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

## 要求

每一层应尽量可单独检查。

优先支持 benchmark_v1 中出现频率较高的场景结构。

## 输出

hierarchical_generation_spec_v1

## 状态

DONE

## 产出

- `docs/model_prompt/hierarchical_generation_spec_v1.md`
- `scripts/hierarchical_generation_planner_v1.py`

## 验证

- `python -m py_compile scripts/hierarchical_generation_planner_v1.py`
- `python scripts/hierarchical_generation_planner_v1.py --example-id IRX-001`
- `python scripts/hierarchical_generation_planner_v1.py --example-id IRX-003`
- `python scripts/hierarchical_generation_planner_v1.py --example-id IRX-005`

验证结果：

- 已将生成流程稳定拆分为 `scenario_scaffold`、`platform_layer`、`sensor_layer`、`weapon_layer`、`mission_layer`、`scenario_assembly`
- 已明确 processor / comm 属于 Mission Layer，而不是被错误并入静态平台层
- 已支持读取 Task-006 的 `ir_examples_v1` 并结合 Task-010 grounding 输出分层计划
- `IRX-001`、`IRX-003`、`IRX-005` 均可生成 `ready_for_generation = true` 的 plan
- `weapon_profile`、`comm_profile`、`processor_profile` 已作为生成期结构约束进入 plan，而不是被压成单一 `WSF_*`

## 依赖

- Task-006
- Task-010

---

# Task-012 设计 Self Repair Workflow

## 目标

实现：

脚本

↓

错误分析

↓

修复

↓

重新验证

## 修复范围

优先支持：

- 缺少单位
- 缺少 end_xxx
- 坐标格式错误
- 引用不存在对象
- 必填字段缺失
- 组件结构不完整

## 输出

repair_workflow_v1

## 状态

DONE

## 依赖

- Task-008

---

# Task-013 建立 Minimal Agent Loop

## 目标

在正式主系统集成前，先跑通一个最小可行闭环。

## 范围

选择 3~5 个简单 benchmark_v1 任务。

优先选择：

- 单平台任务
- 静态部署任务
- 简单动态任务

## 流程

自然语言

↓

Intent Parsing

↓

AFSIM-IR

↓

Grounding

↓

IR-to-Script

↓

Static Verification

↓

一轮 Self Repair

↓

输出可检查脚本

## 验收标准

至少完成：

- 3 个任务完整跑通流程
- 每个任务输出 IR
- 每个任务输出 Grounded IR
- 每个任务输出 AFSIM 脚本
- 每个任务输出静态检查结果
- 至少 1 个任务进入 Self Repair 流程

## 输出

minimal_agent_v0

## 状态

DONE

## 依赖

- Task-006
- Task-007
- Task-008
- Task-010
- Task-011
- Task-012

---

# Task-014 设计 Execution Repair Workflow

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

DONE

## 依赖

- Task-012
- Task-013

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

DONE

## 依赖

- Task-009
- Task-013
- Task-014

---

# Task-016 Full Agent Evaluation

## 目标

对完整 AFSIM Agent v1 进行正式评测。

## 流程

benchmark_v1

↓

AFSIM Agent v1

↓

evaluation_protocol_v1

↓

结果统计

## 指标

- IR Validity
- IR Accuracy
- Grounding Accuracy
- Script Correctness
- Static Pass Rate
- Semantic Match Rate
- Repair Success Rate
- mission.exe Success Rate

## 输出

- full_agent_v1_results
- full_agent_v1_summary
- full_agent_v1_error_analysis

## 状态

BLOCKED

## 依赖

- Task-009
- Task-015

---

# Task-017 建立 IR-only Baseline

## 目标

评估单独引入 AFSIM-IR 是否能提升生成效果。

## 流程

自然语言

↓

AFSIM-IR

↓

AFSIM脚本

## 限制

不使用：

- Grounding
- Static Repair
- Execution Repair

## 作用

用于回答：

单独引入 IR 是否有效？

## 输出

baseline_ir_only_v1

## 状态

BLOCKED

## 依赖

- Task-006
- Task-009
- Task-011

---

# Task-018 建立消融实验协议

## 目标

验证各模块对最终性能提升的贡献。

## 原则

消融实验不应等所有模块完成后才开始。

每完成一个模块，都应在小规模任务集上记录一次结果。

## 消融版本

至少包含：

- Direct Prompt
- RAG
- IR-only
- IR + Grounding
- IR + Grounding + Static Verification
- IR + Grounding + Static Verification + Self Repair
- Full Agent

## 对比目标

回答以下问题：

- RAG 是否有效？
- IR 是否有效？
- Grounding 是否降低幻觉？
- Static Verification 是否能发现错误？
- Self Repair 是否提升通过率？
- Execution Repair 是否提升最终可执行率？

## 输出

ablation_protocol_v1

## 状态

BLOCKED

## 依赖

- Task-009
- Task-016
- Task-017

---

# Task-019 建立 Benchmark v2

## 目标

构建一个更完整的 AFSIM 多任务 benchmark，用于后续全面评估场景生成能力，而不只评测端到端 Type A。

## 执行原则

Benchmark v2 不应阻塞最小 Agent 闭环。

优先构造服务主方法的 Type C、Type D、Type E。

Type A、Type B 和完整泛化切分可以在 Minimal Agent Loop 跑通后继续扩展。

## 数据范围

benchmark_v2 至少包含以下五类数据对：

- Type A：指令 -> 脚本
- Type B：脚本 -> 指令
- Type C：指令 -> IR
- Type D：IR -> 脚本
- Type E：错误脚本 + 报错 -> 修复脚本

## 说明

- Type A 用于端到端场景生成主评测。
- Type B 用于从现有脚本反向生成自然语言描述，并可通过人工抽样修订缓解标注不足。
- Type C 用于训练和评测意图理解与中间表示生成。
- Type D 用于训练和评测领域落地模块。
- Type E 用于训练和评测 self-repair 与错误修复闭环。
- benchmark_v2 的目标不是只做单一 benchmark，而是形成覆盖 A-E 的统一评测集。

## 状态

BLOCKED

## 依赖

- Task-002
- Task-006
- Task-008
- Task-012

---

## Task-019.1 构造 Type C：指令 -> IR

### 目标

构造自然语言需求到 AFSIM-IR 的数据对。

### 用途

训练和评测 Intent Parsing 与 AFSIM-IR 生成能力。

### 要求

每条 IR 必须通过：

afsim_ir_schema_v1

校验。

### 输出

instruction_to_ir_v1

### 状态

BLOCKED

## 依赖

- Task-006
- Task-007

---

## Task-019.2 构造 Type D：IR -> 脚本

### 目标

构造 AFSIM-IR 到 AFSIM 脚本的数据对。

### 用途

训练和评测从结构化中间表示到领域脚本的落地能力。

### 要求

每条样本应包含：

- AFSIM-IR
- Grounded IR
- AFSIM脚本
- 静态检查结果
- mission.exe 执行结果

### 输出

ir_to_script_v1

### 状态

BLOCKED

## 依赖

- Task-006
- Task-008
- Task-010
- Task-011

---

## Task-019.3 构造 Type E：错误脚本 + 报错 -> 修复脚本

### 目标

构造 self-repair 数据集。

### 数据来源

- Direct Prompt 失败结果
- RAG 失败结果
- 人工注入错误
- mission.exe 报错日志
- Static Checker 报错结果

### 错误类型

至少覆盖：

- 缺少单位
- 缺少 end_xxx
- 引用不存在对象
- 坐标格式错误
- 必填字段缺失
- 幻觉组件
- 任务结构错误

### 输出

repair_dataset_v1

### 状态

BLOCKED

## 依赖

- Task-003
- Task-008
- Task-012

---

## Task-019.4 构造 Type A：指令 -> 脚本

### 目标

扩展当前 benchmark_v1 中已有的端到端数据。

### 输入

自然语言任务描述。

### 输出

对应 AFSIM 脚本。

### 要求

每条脚本应尽量通过：

- 静态检查
- mission.exe 执行验证

### 状态

BLOCKED

---

## Task-019.5 构造 Type B：脚本 -> 指令

### 目标

从已有 AFSIM 脚本反向生成自然语言描述。

### 用途

缓解自然语言标注数据不足问题。

### 流程

AFSIM脚本

↓

反向生成自然语言描述

↓

人工抽样修订

### 输出

script_to_instruction_v1

### 状态

BLOCKED

---

## Task-019.6 建立 Benchmark v2 泛化切分

### 目标

建立更能体现泛化能力的数据切分。

### 切分维度

至少包含：

- Seen templates / Unseen compositions
- Single-platform / Multi-platform
- Static deployment / Dynamic mission
- Text-only / Text+Sketch
- Known alias / Novel alias

### 输出

splits_v2

### 状态

BLOCKED

---

## Task-019.7 验证 Benchmark v2 数据格式与可用性

### 目标

确保 benchmark_v2 的数据格式统一、可校验、可复现。

### 检查内容

- Type A-E 数据格式是否统一
- IR 是否通过 schema 校验
- 脚本是否通过静态检查
- oracle 脚本是否可执行
- repair 样本是否包含错误脚本、错误信息、修复脚本
- split 文件是否覆盖所有任务

### 输出

benchmark_v2_validation_report

### 状态

BLOCKED

---

# 可选扩展任务

## Task-101 Log -> AAR

## 目标

将 mission.exe 运行日志转化为 AAR 报告。

## 流程

日志

↓

事件抽取

↓

战后分析报告

## 状态

FUTURE

---

## Task-102 图 -> IR

## 目标

支持态势图或草图输入。

## 流程

态势图

↓

AFSIM-IR

↓

AFSIM场景

## 状态

FUTURE

---

# 当前优先级

## P0 立即执行

- Task-007 建立 Intent Parsing 规范
- Task-008 建立 Static Verification 规范
- Task-009 建立评测体系

## P1 最小主方法闭环

- Task-010 建立最小 Grounding 库 v1
- Task-011 设计分层生成流程
- Task-012 设计 Self Repair Workflow
- Task-013 建立 Minimal Agent Loop

## P2 执行反馈与正式系统

- Task-014 设计 Execution Repair Workflow
- Task-015 主系统集成
- Task-016 Full Agent Evaluation
- Task-017 建立 IR-only Baseline
- Task-018 建立消融实验协议

## P3 Benchmark v2 扩展

优先：

- Task-019.1 构造 Type C：指令 -> IR
- Task-019.2 构造 Type D：IR -> 脚本
- Task-019.3 构造 Type E：错误脚本 + 报错 -> 修复脚本

随后：

- Task-019.4 构造 Type A：指令 -> 脚本
- Task-019.5 构造 Type B：脚本 -> 指令
- Task-019.6 建立 Benchmark v2 泛化切分
- Task-019.7 验证 Benchmark v2 数据格式与可用性

## P4 未来扩展

- Task-101 Log -> AAR
- Task-102 图 -> IR
