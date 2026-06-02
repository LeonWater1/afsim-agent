# AFSIM Dataset Design v1

## 1. 目标

本文档把调研方案中的数据建议正式落到项目数据结构中。当前版本不是大规模训练集，而是用于论文实验、baseline 对比和后续自动扩展的首版数据集骨架。Type A-F 每类各 5 条 starter samples，均围绕已通过 `mission.exe` 的官方 demo 改写构造。

对应目录：

- `datasets/dataset_v1/`

## 2. 数据来源覆盖

当前已覆盖：

| 调研建议来源 | 当前体现 |
|---|---|
| 官方 demo / 示例场景 | `benchmarks/benchmark_v1/demo_sources/` |
| 命令参考文档 | `references/commands_reference.md` 等 |
| 平台/传感器/武器配置样例 | demo sources 中的 component files |
| 仿真日志与报错记录 | `validation_logs/`、`baseline_direct_v1/mission_logs/`、`baseline_rag_v1/mission_logs/` |
| Skill 文档 | `SKILL.md` |

当前未覆盖：

- 内部模板库
- 历史场景脚本
- 培训材料
- text + sketch 图文输入

## 3. 样本类型

### Type A: 指令 -> 脚本

文件：`datasets/dataset_v1/type_a_instruction_to_script.jsonl`

用途：训练或评估自然语言需求到 AFSIM 脚本的基础生成能力。每条样本均由官方 demo 改写，输出为已验证通过的 oracle 脚本路径。

完整 Type A benchmark 仍由 `benchmarks/benchmark_v1/tasks.jsonl` 提供。

### Type B: 脚本 -> 指令

文件：`datasets/dataset_v1/type_b_script_to_instruction.jsonl`

用途：从已有脚本反向生成需求描述，缓解人工标注不足。

当前 v1 采用人工整理的脚本摘要，后续可由 LLM 批量生成，再人工抽样修订。

### Type C: 指令 -> IR

文件：`datasets/dataset_v1/type_c_instruction_to_ir.jsonl`

用途：训练或评估 Intent Parsing 与 AFSIM-IR 生成。

当前 IR 是 draft schema，Task-006 会进一步规范为 `afsim_ir_schema_v1`。

### Type D: IR -> 脚本

文件：`datasets/dataset_v1/type_d_ir_to_script.jsonl`

用途：训练或评估领域落地模块。输入是结构化 IR，输出是 oracle 脚本路径。

### Type E: 错误脚本 + 报错 -> 修复脚本

文件：`datasets/dataset_v1/type_e_error_repair.jsonl`

用途：训练 self-repair。当前使用 RAG baseline 失败脚本和 mission.exe 报错日志作为输入，以对应官方 demo oracle 作为可执行修复目标。

注意：v1 的 repair target 是“可执行参考修复脚本”，不是逐行最小 patch。

### Type F: log -> AAR

文件：`datasets/dataset_v1/type_f_log_to_aar.jsonl`

用途：训练仿真结果解释与报告生成。当前用 mission.exe 日志生成简短 AAR 摘要。

## 4. 泛化切分

文件：`datasets/dataset_v1/splits_v1.json`

当前定义以下切分维度：

- Seen templates / Unseen compositions
- Single-platform / Multi-platform
- Static deployment / Dynamic mission
- Text-only / Text+Sketch
- Known alias / Novel alias

v1 只提供基于 27 条 benchmark 的首版标签，后续 benchmark_v2 扩展到 50+ 样例时应补齐 train/dev/test。

## 5. 当前限制

- Type A-F 目前各 5 条 starter set，不是全量闭环训练集。
- IR schema 仍是 draft，需在 Task-006 中正式化。
- Type E 当前使用 oracle demo 作为修复目标，后续应补充最小编辑 diff。
- Type F 当前是人工摘要风格，后续应从更多 `.evt`、`.aer`、mission log 中抽取结构化指标。
