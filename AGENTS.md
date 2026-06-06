## 项目概述

构建 AFSIM 2.9.0 场景生成的专用 LLM Agent。流水线：`自然语言 → Intent Parsing → AFSIM-IR → Grounding → Grounded IR → Hierarchical Generation → Static Verification → mission.exe → Execution Repair → Executable Scenario`。

Self Repair（LLM 全脚本修复）已移除 — 不可靠，引入错误多于修复。自愈性通过 Static Checker → mission.exe → Execution Repair 闭环实现。确定性后处理（`postprocess_script`）在 Generation 输出阶段执行。

禁止绕过 IR + Grounding 直接生成脚本。

## 关键文件

| 文件        | 职责                                                         |
| ----------- | ------------------------------------------------------------ |
| `TASK.md`   | 任务定义、依赖关系、任务状态。完成任务时只更新 `Status` 字段 |
| `STATUS.md` | 当前阶段、实验数据、风险、下一步计划、协作备注               |
| `AGENTS.md` | 项目原则、规则、约定、修复原则                               |
| `CLAUDE.md` | 本文件，给 Claude Code 的代码库指南                          |

**每次开启新会话必须先读取 `STATUS.md` 对齐状态。每次修改后必须更新 `STATUS.md`。**

## 真值来源

```
AFSIM 官方文档 > 官方 Demo > Grounding 库 > 历史实验 > 模型推断
```

- 官方文档路径：`C:/Program Files/afsim-2.9.0-win64/documentation/html/docs/main_page.html`
- 中文参考：`references/` 目录
- 优先参考官方 Command Index（`wsf-commandindex.html`）、Class Index、Model Index
- 禁止凭空创造未在官方文档或 Demo 中出现过的实体、类型、命令
- 所有静态检查规则、safe_repair 逻辑、prompt 约束应能追溯到官方文档页面或 Demo 文件
- `mission.exe` 是最终裁判。`mission.exe ≠ Static Checker` 时，以 `mission.exe` 为准

## 验证优先级

```
mission.exe > 官方文档 > Static Checker > 模型推断
```

## 主入口与命令

```bash
# 在指定 benchmark 任务上运行完整 Agent 流水线
python scripts/core/agent.py --task-ids BV1-001 BV1-003 BV1-017 --model deepseek-v4-pro

# 需要 DEEPSEEK_API_KEY 环境变量
```

### 独立脚本命令

```bash
# 对生成的脚本运行 mission.exe
python scripts/core/run_mission.py <script_file.txt> [-es|-rt|-fs] [-fio]

# 对单个脚本或目录进行静态检查
python scripts/core/static_checker.py --script <file.txt>
python scripts/core/static_checker.py --dir <directory>

# Grounding 库验证
python scripts/core/grounding.py --validate

# Execution Repair 规划器验证
python scripts/core/repair_planner.py --validate

# 评测协议 — 生成统一评分表
python scripts/evaluate_protocol.py

# 分层生成规划器（用 IR 示例测试）
python scripts/core/generation_planner.py --example-id IRX-001

# Benchmark v2 验证
python benchmarks/benchmark_extended/validate_benchmark.py
```

## 架构：核心流水线模块

### 1. LLM 客户端（`scripts/core/llm_client.py`）

共享的 DeepSeek 兼容 chat completion 客户端。`LLMClient` 类包含 `api_key`、`model`、超时/重试配置。同时导出 `extract_json_object()` 用于从代码围栏中解析 LLM JSON 响应。

### 2. Intent Parsing（`scripts/core/intent_parser.py`）

`parse_intent_with_llm(client, task_input)` — 自然语言 → AFSIM-IR。使用 few-shot 提示词。包含 `check_slot_coverage()` 用于解析后诊断。IR 输出必须通过 `afsim_ir_schema_v1` 或 `v2` 校验。

### 3. IR Schema 校验器（`scripts/core/ir_validator.py`）

版本感知的校验器，同时支持 v1 和 v2 schema。从 IR JSON 自动检测 schema 版本。

### 4. Grounding（`scripts/core/grounding.py`）

`build_grounded_ir(ir)` — 将用户实体映射到 AFSIM 标准类型，包含匹配置信度（full/partial/unresolved）、实现约束、伴随规则和外部资源依赖。映射数据位于 `docs/machine/entity_mapping_extended.json`。

### 5. 分层生成

- **规划器**（`scripts/core/generation_planner.py`）：`build_generation_plan(grounded_ir)` → 分层生成计划（scenario_scaffold → platform → sensor → weapon → mission → assembly）
- **执行器**（`scripts/core/generation_executor.py`）：`execute_layered_generation(plan, client, output_dir)` — 通过 LLM 实际逐层生成。使用 `ThreadPoolExecutor` 并行生成平台/任务层。只负责生成+合并，不在内部做静态检查/修复。

### 6. 脚本生成（`scripts/core/script_generator.py`）

`generate_script_with_llm(ir, grounded_ir, generation_plan, client)` — 纯 LLM 生成；无确定性脚手架回退。

### 7. 静态检查器（`scripts/core/static_checker.py`）

`analyze_script_text(text, script_label)` → 输出 findings JSON。检查内容：单位、end_xxx 块闭合、坐标格式、引用完整性、必填字段、非法组件类型、幻觉对象、脚本结构一致性。由 `docs/machine/error_taxonomy.json` 中的错误分类体系驱动。同时使用：

- `scripts/core/context_rules.py` — WSF 类型和命令上下文规则
- `scripts/core/reference_rules.py` — 禁止正则模式、后处理规则

### 8. 后处理（`scripts/core/reference_rules.py`）

`postprocess_script(text)` — 对每个脚本输出应用的确定性修复（覆盖约 80+ 已知错误模式）。作为统一的写入前门禁执行。

### 9. Execution Repair（`scripts/core/repair_planner.py`）

`build_execution_repair_plan(static_result, mission_result)` — 将 mission 失败分类为 17 种错误模式 → 5 个生成层。退出码分类（0/1/-1/None）。支持 `target_layers` 参数用于限定范围的 LLM 修复。

### 10. LLM 修复执行器（`scripts/core/repair_executor.py`）

`llm_execution_repair()` — LLM 引导的修复，限定到特定层（基于 mission.exe 诊断）。重试循环：最多 2 次尝试，error family 未改善时回退。`llm_static_repair()` 已废弃 — Self Repair 已从流水线移除。

### 11. Mission 日志解析器（`scripts/core/mission_log_parser.py`）

`parse(mission_log_text)` — 从 mission.exe 输出中提取结构化诊断（退出码、错误类别、缺失事件、实体状态）。

## IR Schema 版本

- **v1**：`docs/machine/afsim_ir_schema.json` — Scenario、Side、Platform、Mission、Components、Constraints
- **v2**：`docs/machine/afsim_ir_schema_extended.json` — 新增 Logic 层（behavior_rules、state_machines、engagement/trigger logic）和 Evaluation 层（mission_phases、success_criteria、observation_metrics）
- v1 → v2 向后兼容（仅需升级 `schema_version`）

## Benchmark 数据

- **benchmark**：`benchmarks/benchmark/tasks.jsonl` — 27 个任务，oracle 脚本已通过 `mission.exe` 验证（27 PASS）
- **benchmark_extended**：`benchmarks/benchmark_extended/` — 5 种类型（A：指令→脚本、B：脚本→指令、C：指令→IR、D：IR→脚本、E：错误→修复），共 38 条样本

## 修复原则（来自 AGENTS.md）

### 泛化性

禁止 `if task_id == ...`、针对单个 benchmark 特判、从失败脚本直提正则硬匹配。每条新增规则必须能回答：来源（官方文档哪页/Demo 哪个文件）、覆盖范围（哪些场景类型）、假阳性风险（合法 Demo 是否误报）、未观测数据预期（扩展到 100 任务是否仍生效）。

### 均等性

所有 benchmark 任务使用相同 Prompt 模板、Pipeline 路径、代码路径。

### 确定性层 vs LLM 依赖层

- **确定性层**（未知数据保证生效）：官方命令白名单、WSF 类型上下文约束、块交叉关闭纠正、引用完整性检查、命令位置检查、外部资源检查 — 持续从官方文档扩充
- **LLM 依赖层**（未知数据可能退化）：Intent Parsing、Script Generation、Execution Repair — 通过扩充 few-shot 和 grounding 覆盖改进，而非微调 prompt

## API Key

需要 `DEEPSEEK_API_KEY` 环境变量。默认 API 端点：`https://api.deepseek.com/chat/completions`。模型：`deepseek-v4-pro` 或 `deepseek-v4-flash`。

## AFSIM 脚本规范（来自 SKILL.md）

- 脚本文件必须使用 `.txt` 扩展名（不能使用 `.wsf`）
- 所有数值参数必须包含单位（`m/sec`、`ft`、`nm`、`sec`、`g`）
- 坐标使用冒号 `:` 分隔：`38:44:52.3n 90:21:36.4w`
- 使用 `print()` 而非 `cout` 输出
- `on_initialize` 中的代码不能包裹在 `script` 块中
- 天线方向图使用 `constant_pattern` 子块，不能直接定义参数
- 脉冲宽度使用科学计数法：`1.0e-6 sec`，不能使用 `microsec`
