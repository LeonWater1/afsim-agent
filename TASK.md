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

## 验收标准

- `docs/human_readme/AFSIM组件关系分析文档.md` 存在
- 文档覆盖 Platform、Sensor、Weapon、Mover、Processor、Route、Task 的职责和依赖
- 文档给出 AFSIM 场景从组件到脚本的组装流程
- 至少引用官方 demo 或现有示例中的真实组件关系作为依据

## 状态

DONE

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

## 验收标准

- `benchmarks/benchmark_v1/tasks.jsonl` 可按 JSONL 逐行解析
- benchmark 任务数量在 20~50 条之间
- 每条任务包含自然语言输入、source hint、覆盖组件和 oracle 脚本来源
- 每条 oracle 脚本均能在真实 `mission.exe` 环境中执行通过或有验证日志
- `benchmarks/benchmark_v1/README.md` 说明数据来源、字段格式和验证方式

## 状态

DONE

## 已产出

- `benchmarks/benchmark_v1/README.md`
- `benchmarks/benchmark_v1/tasks.jsonl`
- `benchmarks/benchmark_v1/demo_sources/`
- `benchmarks/benchmark_v1/validation_logs/`

## 验证结果

- 当前 `benchmark_v1` 共 27 个任务
- 所有任务均绑定真实 `demo_sources` 来源文件
- oracle 场景已完成 `mission.exe` 验证，当前结论为 27 PASS / 0 FAIL / 0 TIMEOUT

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

## 验收标准

- `docs/machine/error_taxonomy_v1.json` 可解析为合法 JSON
- taxonomy 至少覆盖缺少单位、缺少 `end_xxx`、引用不存在、坐标格式错误、幻觉实体、必填项缺失
- 每个错误类型包含稳定 error id、名称、说明和是否影响静态通过的判定字段
- 人类说明文档解释错误类型、典型触发条件和后续评测统计口径

## 状态

DONE

## 已产出

- `docs/human_readme/AFSIM错误分类体系_v1.md`
- `docs/machine/error_taxonomy_v1.json`

## 验证结果

- 已覆盖任务要求中的 6 类核心错误：缺少单位、缺少 `end_xxx`、引用不存在对象、坐标格式错误、幻觉实体、必填项缺失
- 当前 taxonomy 已扩展为 `E001 ~ E010`
- 后续 Task-008 与 Task-014 已直接复用该分类体系

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

## 验收标准

- `scripts/run_direct_baseline.py` 可运行并要求 `DEEPSEEK_API_KEY`
- Direct Prompt 不使用 RAG、IR、Grounding、oracle、demo 示例或 repair 反馈
- 对 `benchmark_v1` 每条任务生成脚本、mission log 和结果记录
- 输出 `results.jsonl`、`summary.json`、`error_stats.json` 和 `README.md`
- 统计 Syntax Correct、Static Pass、mission.exe Success、Semantic Match 和错误类型分布

## 状态

DONE

## 已产出

- `scripts/run_direct_baseline.py`
- `baseline_direct_v1/prompt_template.md`
- `baseline_direct_v1/README.md`
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
- 主错误分布：`E001=16`、`E002=23`、`E004=12`、`E006=3`、`E007=27`

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

## 验收标准

- `scripts/run_rag_baseline.py` 可运行并要求 `DEEPSEEK_API_KEY`
- RAG corpus 来源、检索策略和每条任务 retrieved context 均被记录
- 评测时不直接检索当前任务自己的 oracle 脚本作为答案
- 对 `benchmark_v1` 每条任务生成脚本、mission log 和结果记录
- 输出 `results.jsonl`、`summary.json`、`error_stats.json`、`retrieved_contexts.jsonl` 和 `README.md`
- 统计口径与 Direct Prompt baseline 保持一致

## 状态

DONE

## 已产出

- `scripts/run_rag_baseline.py`
- `baseline_rag_v1/prompt_template.md`
- `baseline_rag_v1/README.md`
- `baseline_rag_v1/retrieved_contexts.jsonl`
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
- 语法正确率：5 / 27 = 18.52%
- 静态通过率：4 / 27 = 14.81%
- `mission.exe` 可执行率：4 / 27 = 14.81%
- 语义匹配率：3 / 27 = 11.11%
- 主错误分布：`E001=7`、`E002=13`、`E003=7`、`E004=5`、`E005=5`、`E006=1`、`E007=18`

## 结论

- RAG 检索显著提升生成质量：可执行率从 direct baseline 的 0% 提升到 14.81%
- 检索策略的 source-tree priority 有效确保了同目录相关文件优先被选中
- E005 共 5 个，经逐类型核查均为真实幻觉（WSF_ACTIVE_RADAR、WSF_COMMAND_CHAIN、WSF_WEAPON_TASK、WSF_MESSAGE、WSF_BATTLE_MANAGER），不在任何 demo、reference 或 SKILL.md 中出现
- WSF_STATIONARY_MOVER 经 SKILL.md 确认合法，已加入白名单
- 主要失败原因仍是块未闭合（E002=13）和组件语法错配（E007=18）
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

## 验收标准

- `docs/machine/afsim_ir_schema_v1.json` 可解析为合法 JSON schema
- schema 覆盖 scenario、sides、locations、routes、components、entities、tasks、constraints
- `docs/model_prompt/afsim_ir_schema_v1.md` 用中文解释 IR 字段语义和使用边界
- `docs/machine/ir_examples_v1.jsonl` 至少包含 5 条样例
- 所有 IR 样例均能通过 schema 校验或明确标注为草案样例

## 状态

DONE

## 已产出

- `docs/machine/afsim_ir_schema_v1.json`
- `docs/model_prompt/afsim_ir_schema_v1.md`
- `docs/machine/ir_examples_v1.jsonl`

## 验证结果

- `AFSIM-IR v1` 已覆盖 `scenario`、`sides`、`locations`、`routes`、`components`、`entities`、`tasks`、`constraints`
- 当前 `ir_examples_v1` 已提供 5 个跨场景示例，覆盖 acoustic、air-to-air、escort、group communication、basic IADS C2
- 后续 Task-010、Task-011、Task-013、Task-015 已直接复用该 schema 与示例

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

## 验收标准

- `docs/model_prompt/intent_parsing_spec_v1.md` 存在
- 规范覆盖场景名称、平台、数量、阵营、区域、位置、任务、武器、传感器、约束条件
- 规范说明不确定实体如何进入 `grounding_hints` 或 `*_hint`
- 规范给出自然语言到 AFSIM-IR 的最小示例
- 规范明确禁止直接臆造未经 grounding 验证的 AFSIM 类型

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

## 验收标准

- `scripts/static_checker_v1.py` 是静态检查唯一实现来源
- 检查器可检查单文件和目录，并输出 JSON 摘要
- 检查规则至少覆盖单位、块闭合、引用、坐标、必填字段、非法组件类型、脚本结构
- `syntax_correct` 和 `static_pass` 由 `docs/machine/error_taxonomy_v1.json` 驱动
- Direct Prompt 和 RAG baseline 均调用同一检查器
- 至少包含通过样例和失败样例的回归验证记录

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

## 验收标准

- `docs/machine/evaluation_protocol_v1.json` 可解析并定义统一指标
- `docs/human_readme/evaluation_protocol_v1.md` 解释各指标定义和适用范围
- `scripts/evaluate_protocol_v1.py` 可读取方法目录并生成统一 scoreboard
- 对 Direct/RAG 不适用的 IR、Grounding、Repair 指标使用 `null`
- 评估脚本使用当前 `static_checker_v1` 重算静态指标
- 已生成 baseline 对比结果文件

## 状态

DONE

## 已产出

- `docs/human_readme/evaluation_protocol_v1.md`
- `docs/machine/evaluation_protocol_v1.json`
- `scripts/evaluate_protocol_v1.py`
- `scripts/refresh_baseline_eval_v1.py`
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

## 验收标准

- `docs/machine/entity_mapping_v1.json` 可解析并通过 `grounding_library_v1.py --validate`
- mapping 至少覆盖 benchmark_v1 / IR examples 中出现的 side、platform、task、component hints
- 每条 platform/task/component mapping 都包含 `canonical_id` 和 `grounding_target`
- `scripts/grounding_library_v1.py` 提供 side、platform、task、component 查询入口
- 粗粒度相同的 AFSIM 类型保留 profile / role 区分，避免生成阶段丢失语义

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

## 验收标准

- `docs/model_prompt/hierarchical_generation_spec_v1.md` 存在并定义分层生成顺序
- `scripts/hierarchical_generation_planner_v1.py` 可从 IR 样例生成 generation plan
- generation plan 至少包含 scenario scaffold、platform、sensor、weapon、mission、assembly 层
- planner 能标记 unresolved items 和 `ready_for_generation`
- 至少 3 个 IR 样例生成 `ready_for_generation = true` 的 plan

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

## 验收标准

- `docs/model_prompt/repair_workflow_v1.md` 存在并定义修复输入、输出和路由
- `scripts/self_repair_planner_v1.py` 可读取静态检查结果并生成结构化 repair plan
- 对低风险错误支持确定性安全修复并重新运行静态检查
- 对不可安全修复的问题能路由到 IR、Grounding、Layer Regeneration 或 Script Logic Repair
- 至少包含一个安全修复成功样例和一个结构性错误路由样例

## 状态

DONE

## 已产出

- `docs/model_prompt/repair_workflow_v1.md`
- `scripts/self_repair_planner_v1.py`
- `evaluation/self_repair_v1/BV1-002_repair_plan.json`
- `evaluation/self_repair_v1/BV1-002_repaired_preview.txt`
- `evaluation/self_repair_v1/BV1-003_repair_plan.json`

## 验证结果

- 已支持从 `static_checker_v1` 结果生成结构化 repair plan
- 已支持安全修复：补缺失 `end_xxx`、补 `end_time`、补部分缺失单位
- `BV1-002` 安全修复后 findings 从 4 条降到 2 条
- `BV1-003` 被正确路由为结构性问题，建议回 layer regeneration 而不是做危险文本补丁
- Task-012 负责 repair plan 与路由定义；实际 LLM 局部重生执行器已在 Task-016 的 `llm_repair_executor_v1.py` 中接入并验证

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

## 已产出

- `scripts/minimal_agent_loop_v0.py`
- `minimal_agent_v0/README.md`
- `minimal_agent_v0/summary.json`
- `minimal_agent_v0/BV1-001/`
- `minimal_agent_v0/BV1-003/`
- `minimal_agent_v0/BV1-005/`

## 验证结果

- 已在 3 个任务上跑通最小闭环：`BV1-001`、`BV1-003`、`BV1-005`
- `grounding_ok = 3/3`
- `generation_ready = 3/3`
- `initial_static_pass = 2/3`
- `repair_triggered = 1/3`
- `repair_success = 1/1`
- `final_static_pass = 3/3`

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

## 验收标准

- `docs/model_prompt/execution_repair_spec_v1.md` 存在并定义执行错误分类和修复路由
- `scripts/execution_repair_planner_v1.py` 可分析 mission log、return code 和静态检查结果
- 分类器至少覆盖 `E009` 环境/依赖错误、`E008` 脚本编译/API 错误和静态错误回退
- `rerun_plan.preconditions` 随不同 route 变化
- `--validate` 内建验证样例全部通过

## 状态

DONE

## 已产出

- `docs/model_prompt/execution_repair_spec_v1.md`
- `scripts/execution_repair_planner_v1.py`
- `evaluation/execution_repair_v1/pass_simple_demo.json`
- `evaluation/execution_repair_v1/fail_missing_dependency.json`
- `evaluation/execution_repair_v1/fail_script_compile.json`

## 验证结果

- 已支持 `E009` 环境 / 依赖错误分类
- 已支持 `E008` 脚本编译 / API 错误分类
- 已支持基于运行日志与静态错误的回退路由
- 已支持 `--validate` 模式，当前内建验证样例为 6 / 6 全通过

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

## 验收标准

- `scripts/afsim_agent_v1.py` 串接 Intent Parsing、AFSIM-IR、Grounding、Hierarchical Generation、Static Verification、Self Repair、Execution Repair
- 对至少 3 个 benchmark_v1 任务输出 intent、IR、grounded IR、generation plan、脚本、静态检查、执行修复结果
- 至少 1 个任务触发并完成 self-repair 流程
- 所有默认验证任务最终 `static_pass = true`
- 所有默认验证任务最终 `mission_status = PASS`
- `TASK.md` 和 README 明确说明 v1 的 benchmark-backed / demo-backed 范围限制

## 状态

DONE

## 当前 v1 范围说明

- 当前 `Intent Parsing` 仍为 benchmark-backed，对受支持任务使用 `benchmark_example_alignment`
- 当前 `IR-to-Script` 仍为 demo-backed，通过 `mirrored_demo_workspace` 复制并运行现有 demo 工作区
- 当前默认验证任务为 3 个已具备 curated IR example 的 benchmark 任务：`BV1-001`、`BV1-003`、`BV1-005`
- 当前 `grounded_ir` 与 `generation_plan` 已串接在同一 workflow 中，但 generation planner 仍主要消费 IR 原文；grounding 产生的细粒度 target/profile 信息尚未完全下沉到后续生成阶段

## 已产出

- `docs/model_prompt/agent_workflow_v1.md`
- `scripts/afsim_agent_v1.py`
- `afsim_agent_v1/README.md`
- `afsim_agent_v1/summary.json`
- `afsim_agent_v1/BV1-001/`
- `afsim_agent_v1/BV1-003/`
- `afsim_agent_v1/BV1-005/`

## 验证结果

- 已在 3 个任务上跑通完整 Agent Workflow：`BV1-001`、`BV1-003`、`BV1-005`
- `grounding_ok = 3/3`
- `generation_ready = 3/3`
- `final_static_pass = 3/3`
- `mission_pass = 3/3`
- `BV1-001` 已成功触发并完成一轮受控 self-repair，再通过 `mission.exe`
- `execution_repair.json` 已按当前 `build_rerun_preconditions()` 口径刷新；`no_repair_needed` 路由当前输出 `preconditions = [\"no repair required\"]`

## 依赖

- Task-009
- Task-013
- Task-014

---

# Task-016 大模型接入主系统

## 目标

将当前 workflow-complete prototype 升级为真正的大模型驱动 Agent。

## 流程

自然语言

↓

LLM Intent Parsing

↓

AFSIM-IR + Schema Validation

↓

Grounding

↓

Generation Plan + Grounded IR

↓

LLM Script Generation

↓

Static Verification

↓

LLM-guided Self Repair / Layer Regeneration

↓

Execution Repair

↓

Executable Scenario

## 具体实现

至少完成：

- 抽取共享 `llm_client`，统一 DeepSeek / 后续模型调用方式
- 将 `afsim_agent_v1.py` 中 `intent_parse_task()` 从 `benchmark_example_alignment` 改为真实 LLM 解析
- 在 LLM intent parsing 后增加 `afsim_ir_schema_v1` 校验与失败重试
- 将 `IR-to-Script` 从 `mirrored_demo_workspace` 替换为 LLM 生成脚本文本并落盘
- 将 `grounded_ir` 的 target / profile 信息显式下传到 generation 阶段
- 对非安全类修复，允许按 `repair_plan` 调用 LLM 做局部重写
- 对 execution repair 的可修复路由，允许调用 LLM 做二次修复或 layer regeneration

## 范围约束

第一版大模型接入优先支持：

- benchmark_v1 中已具备 IR example 的任务
- 单轮 intent parsing
- 单轮 script generation
- 单轮 self repair

暂不强求：

- 任意开放域自然语言
- 多轮 agent planning
- 全 benchmark 27 任务同时稳定通过

## 输出

- llm_client_v1
- llm_intent_parser_v1
- llm_script_generator_v1
- llm_repair_executor_v1
- afsim_agent_v2

## 验收标准

- 新增或抽取统一 `llm_client`，不再在各脚本中重复实现模型调用
- `afsim_agent_v2` 能用 LLM 从自然语言生成 AFSIM-IR，并通过 schema 校验或自动修复重试
- 脚本生成阶段使用 `IR + grounded_ir + generation_plan` 调用 LLM 生成脚本文本，不再依赖复制 demo 作为主路径
- 非安全类 self-repair 至少支持一次 LLM-guided 局部重写并重新静态检查
- execution repair 至少支持一种可修复 route 的 LLM 二次修复或 layer regeneration
- 至少 3 个受支持 benchmark 任务完成端到端运行，并产出完整任务工件

## 状态

DONE

## 已产出

- `scripts/llm_client_v1.py`
- `scripts/ir_schema_validator_v1.py`
- `scripts/llm_intent_parser_v1.py`
- `scripts/llm_script_generator_v1.py`
- `scripts/llm_repair_executor_v1.py`
- `scripts/afsim_agent_v2.py`
- `afsim_agent_v2/README.md`
- `afsim_agent_v2/summary.json`
- `afsim_agent_v2/BV1-001/`
- `afsim_agent_v2/BV1-003/`
- `afsim_agent_v2/BV1-017/`
- `afsim_agent_v2/probes/BV1-003_bad_weapon_layer_probe.txt`
- `afsim_agent_v2/probes/BV1-003_layer_regeneration_probe.json`
- `afsim_agent_v2/probes/BV1-003_layer_regenerated_script.txt`

## 验证结果

- `python -m py_compile` 已通过：`llm_client_v1.py`、`ir_schema_validator_v1.py`、`llm_intent_parser_v1.py`、`llm_script_generator_v1.py`、`llm_repair_executor_v1.py`、`afsim_agent_v2.py`
- 使用 `DEEPSEEK_API_KEY` 实跑 `python scripts/afsim_agent_v2.py --task-ids BV1-001 BV1-003 BV1-017 --model deepseek-v4-pro`
- `afsim_agent_v2/summary.json` 结果：
- `total=3`
- `final_static_pass=3`
- `mission_pass=3`
- 通过任务：
- `BV1-001` 声学探测最小示例：`mission_status=PASS`
- `BV1-003` 一对一空战：`mission_status=PASS`
- `BV1-017` 群组通信：`mission_status=PASS`
- 受控 probe：
- `BV1-001_static_repair_probe.json` 证明了 LLM-guided static repair 路径可调用并可重新静态检查
- `BV1-001_execution_repair_probe.json` 证明了 execution repair 在 `E005 / return_to_grounding` 路由上可调用 LLM 二次修复
- `BV1-003_layer_regeneration_probe.json` 证明了非安全类 self-repair 可以根据 `repair_plan.target_layers=["weapon_layer"]` 只重生目标层，而不是整脚本重写
- 局部重生 probe 的关键结果：`mode=static_repair_layer_regeneration`、`replacement_count=1`、`full_script_fallback_used=false`、重生后 `static_pass=true`
- `BV1-003_layer_regenerated_script.txt` 已通过 `static_checker_v1.py`，并通过 `mission.exe -es -fio`，返回码为 0

## LLM-only amendment

- `llm_script_generator_v1.py` no longer builds deterministic scaffold scripts or uses scaffold fallback. Final script text must come from LLM output.
- `afsim_agent_v2.py` no longer uses `normalize_ir_for_execution()` or deterministic safe-repair fallback. Static failures go to LLM static repair.
- `summary.json` `mission_pass` and `llm_only_pass` now describe the LLM path only. Demo-copy and scaffold outputs are not counted as main-method success.
- Current LLM-only 3-task trial has been repaired to `mission_pass=3/3`; `BV1-003` and `BV1-017` required execution repair, while controlled probes verify static repair and layer-local regeneration paths.
- The latest `summary.json` was generated before the new layer-regeneration summary counters were added; rerun `afsim_agent_v2.py` to refresh those counters before Task-017 reporting.
- This amendment supersedes the older scaffold-backed validation note above.

---

## 依赖

- Task-015
- Task-007
- Task-011
- Task-012
- Task-014

---

# Task-017 Full Agent Evaluation

## 目标

对完整 AFSIM Agent v2 进行正式评测。

## 流程

benchmark_v1

↓

AFSIM Agent v2

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

- full_agent_v2_results
- full_agent_v2_summary
- full_agent_v2_error_analysis

## 验收标准

- 使用 `evaluation_protocol_v1` 对 `afsim_agent_v2` 进行统一评测
- 评测范围、任务数量和是否为全量 benchmark_v1 必须在 summary 中明确记录
- 输出逐任务结果、总体 summary 和 error analysis
- 8 个协议指标均有数值或明确的 `null` 说明
- 结果至少与 Direct Prompt、RAG baseline 在同一 scoreboard 中可比较
- 记录关键 failure cases 和下一步修复建议

## 状态

BLOCKED

## 依赖

- Task-009
- Task-016

---

# Task-018 建立 IR-only Baseline

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

## 验收标准

- IR-only baseline 使用自然语言 -> IR -> 脚本路径
- 明确禁用 Grounding、Static Repair、Execution Repair
- 对选定 benchmark 任务输出生成脚本、静态检查、mission log 和评测结果
- 使用 `evaluation_protocol_v1` 生成统一指标
- 结果可与 Direct、RAG、Full Agent 对比，用于回答“单独引入 IR 是否有效”

## 状态

BLOCKED

## 依赖

- Task-006
- Task-009
- Task-011
- Task-016

---

# Task-019 建立消融实验协议

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

## 验收标准

- 消融协议列出每个实验变体的启用/禁用模块
- 至少包含 Direct、RAG、IR-only、IR+Grounding、IR+Grounding+Static Verification、IR+Grounding+Static Verification+Self Repair、Full Agent
- 所有变体使用相同任务集合和相同 evaluation protocol
- 输出实验矩阵、运行命令或配置、统一 scoreboard 和模块贡献分析
- 明确说明哪些提升来自 IR、Grounding、Verification、Self Repair、Execution Repair

## 状态

BLOCKED

## 依赖

- Task-009
- Task-017
- Task-018

---

# Task-020 建立 Benchmark v2

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

## 验收标准

- `benchmark_v2` 至少包含 Type A-E 五类数据对
- 每类至少包含 5 条 starter samples，并明确来源 demo 或构造方式
- 所有样本文件可解析，字段格式统一
- 与 `afsim_ir_schema_v1`、`static_checker_v1`、`evaluation_protocol_v1` 的接口关系明确
- 提供 split 文件和 validation report
- `README.md` 说明 Benchmark v2 与 Benchmark v1 的区别和用途

## 状态

BLOCKED

## 依赖

- Task-002
- Task-006
- Task-008
- Task-012

---

## Task-020.1 构造 Type C：指令 -> IR

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

### 验收标准

- 数据文件至少包含 5 条 `instruction -> IR` 样本
- 每条样本包含自然语言指令、AFSIM-IR、来源 demo 和样本 id
- 每条 IR 均通过 `afsim_ir_schema_v1` 校验
- 样本覆盖至少 3 种不同任务或场景类型
- README 说明样本构造方式和人工修订状态

### 状态

BLOCKED

## 依赖

- Task-006
- Task-007

---

## Task-020.2 构造 Type D：IR -> 脚本

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

### 验收标准

- 数据文件至少包含 5 条 `IR -> script` 样本
- 每条样本包含 AFSIM-IR、Grounded IR、生成或 oracle 脚本、静态检查结果和 mission.exe 执行结果
- 每条脚本路径可解析，相关依赖文件可定位
- 至少包含 3 条 `mission_status = PASS` 的样本
- README 说明 demo-backed 与 generated script 的区分

### 状态

BLOCKED

## 依赖

- Task-006
- Task-008
- Task-010
- Task-011

---

## Task-020.3 构造 Type E：错误脚本 + 报错 -> 修复脚本

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

### 验收标准

- 数据文件至少包含 5 条 `错误脚本 + 报错 -> 修复脚本` 样本
- 每条样本包含错误脚本、静态 findings、mission log 或错误文本、修复脚本和修复说明
- 错误类型至少覆盖 E001、E002、E003/E005、E006、E007 中的 4 类
- 修复后脚本必须重新运行静态检查，并记录修复是否成功
- README 说明错误来源是 baseline 失败、人工注入还是执行日志

### 状态

BLOCKED

## 依赖

- Task-003
- Task-008
- Task-012

---

## Task-020.4 构造 Type A：指令 -> 脚本

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

### 验收标准

- 至少新增 5 条 `instruction -> script` 样本
- 每条样本包含自然语言指令、脚本路径、来源 demo、静态检查结果和 mission.exe 结果
- 样本不与 benchmark_v1 完全重复，或明确标注为扩展/改写版本
- 通过样本和失败样本都保留结果记录，不能只保留成功案例
- README 说明与 benchmark_v1 的关系

### 状态

BLOCKED

---

## Task-020.5 构造 Type B：脚本 -> 指令

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

### 验收标准

- 至少新增 5 条 `script -> instruction` 样本
- 每条样本包含脚本路径、自动反向描述、人工修订状态和来源 demo
- 自然语言描述能覆盖平台、阵营、任务和关键组件
- 至少抽样检查 2 条，确认描述不泄漏无关实现细节
- README 说明反向生成与人工修订流程

### 状态

BLOCKED

---

## Task-020.6 建立 Benchmark v2 泛化切分

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

### 验收标准

- split 文件可解析为合法 JSON
- 每条样本至少属于一个 split
- 覆盖 Seen templates / Unseen compositions、Single-platform / Multi-platform、Static / Dynamic、Known alias / Novel alias
- split 中不存在重复样本 id 或不存在的样本 id
- README 解释每个 split 评估的泛化问题

### 状态

BLOCKED

---

## Task-020.7 验证 Benchmark v2 数据格式与可用性

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

### 验收标准

- validation report 覆盖 Type A-E 所有样本文件
- 检查 JSON/JSONL 格式、IR schema、脚本静态检查、oracle 可执行性和 split 完整性
- 报告列出通过数、失败数、失败原因和可复现命令
- validation 脚本或命令可重复运行
- 只有 validation report 通过后，Benchmark v2 才能进入正式评测使用

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

## 验收标准

- 至少支持读取 3 条 `mission.exe` 日志或事件输出
- 能抽取关键事件、时间线、参与实体和结果摘要
- 输出结构化 AAR JSON 和人类可读 AAR 文档
- 至少 2 条样例经过人工检查，确认摘要与日志一致
- README 说明 log 类型、字段和适用边界

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

## 验收标准

- 至少支持 3 条态势图或草图输入样例
- 能输出符合 `afsim_ir_schema_v1` 的 AFSIM-IR
- 能识别基本实体、阵营、位置关系和任务意图
- 输出 IR 进入现有 Grounding / Generation 流程时不破坏接口
- README 说明输入图格式、限制和失败案例

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
- Task-016 大模型接入主系统
- Task-017 Full Agent Evaluation
- Task-018 建立 IR-only Baseline
- Task-019 建立消融实验协议

## P3 Benchmark v2 扩展

优先：

- Task-020.1 构造 Type C：指令 -> IR
- Task-020.2 构造 Type D：IR -> 脚本
- Task-020.3 构造 Type E：错误脚本 + 报错 -> 修复脚本

随后：

- Task-020.4 构造 Type A：指令 -> 脚本
- Task-020.5 构造 Type B：脚本 -> 指令
- Task-020.6 建立 Benchmark v2 泛化切分
- Task-020.7 验证 Benchmark v2 数据格式与可用性

## P4 未来扩展

- Task-101 Log -> AAR
- Task-102 图 -> IR
