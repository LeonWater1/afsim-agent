# TASK.md

# AFSIM Agent Development Tasks

## 项目状态

当前阶段：

Phase 1 - 领域调研与问题定义

总体进度：

18%

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

TODO

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

TODO

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

TODO

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

构建完整评测集。

## 内容

至少包含：

- 简单场景
- 中等复杂场景
- 多平台协同场景

## 输出

benchmark_v2

## 状态

BLOCKED

依赖：

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
