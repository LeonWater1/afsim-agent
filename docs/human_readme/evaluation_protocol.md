# Evaluation Protocol v1

## 1. 目标

本文档定义 Task-009 的统一评测协议，用于在同一批 `benchmark` 任务上比较：

- Direct Prompt
- RAG
- IR-only
- Ablation 版本
- 完整 Agent

v1 的重点不是一次性覆盖全部未来能力，而是先把当前已经存在的 `benchmark`、Direct baseline、RAG baseline、AFSIM-IR 和 Static Verification 接到同一套口径下。

## 2. 适用范围

当前主评测集：

- `benchmarks/benchmark/tasks.jsonl`

当前任务类型：

- 以 Type A 为主，即自然语言需求 -> AFSIM 脚本

协议保留对以下中间阶段指标的扩展位：

- IR Validity
- IR Accuracy
- Grounding Accuracy
- Repair Success Rate

也就是说，Task-009 先把评测协议搭起来，不要求今天就拥有所有中间阶段结果。

## 3. 核心指标

统一统计以下 8 个指标：

1. `IR Validity`
   含义：生成的 IR 是否通过 `afsim_ir_schema_v1` 校验。
   对当前 Direct/RAG baseline：不适用，记为 `null`。

2. `IR Accuracy`
   含义：IR 是否正确表达 benchmark 任务要求的核心语义。
   对当前 Direct/RAG baseline：不适用，记为 `null`。

3. `Grounding Accuracy`
   含义：用户概念是否被映射到正确的 AFSIM 实体或模板。
   对当前 Direct/RAG baseline：不适用，记为 `null`。

4. `Script Correctness`
   含义：脚本是否通过语法/结构层面的正确性检查。
   在 v1 中，等价于 `syntax_correct_rate`。

5. `Static Pass Rate`
   含义：脚本是否通过统一静态检查器的阻断错误检查。
   在 v1 中，等价于 `static_pass_rate`。

6. `Semantic Match Rate`
   含义：脚本虽然可能可执行，但是否满足 benchmark 任务的核心语义。

7. `Repair Success Rate`
   含义：进入 Repair 的样本中，修复后是否达到目标状态。
   对当前 Direct/RAG baseline：不适用，记为 `null`。

8. `mission.exe Success Rate`
   含义：脚本是否能被 `mission.exe` 成功执行。

## 4. 统一口径

评测时使用以下统一规则：

- `Script Correctness` 和 `Static Pass Rate` 优先由当前版本 `static_checker_v1` 重算。
- 不直接信任旧 `summary.json` 里的静态指标，因为静态规则可能已升级。
- `mission.exe Success Rate` 以 `results.jsonl` 或 `summary.json` 中的 `mission_status` / `mission_success_rate` 为准。
- `Semantic Match Rate` 以方法运行时记录的 `semantic_match` 为准。
- 对没有产生 IR、Grounding、Repair 中间产物的方法，相关指标统一记为 `null`，而不是记为 `0`。

这样可以避免“方法没有这个阶段”被误解为“这个阶段完全失败”。

## 5. 结果文件约定

每个方法运行目录建议至少包含：

- `summary.json`
- `results.jsonl`
- `generated_scripts/`

`results.jsonl` 的最小必需字段：

- `id`
- `generated_script`
- `mission_status`

推荐字段：

- `syntax_correct`
- `static_pass`
- `semantic_match`
- `primary_error`
- `secondary_errors`

为未来方法保留的字段：

- `ir_valid`
- `ir_accurate`
- `grounding_correct`
- `repair_success`

## 6. 聚合规则

布尔型指标统一按：

```text
rate = True 样本数 / 适用样本数
```

其中：

- `syntax_correct` -> `Script Correctness`
- `static_pass` -> `Static Pass Rate`
- `semantic_match` -> `Semantic Match Rate`
- `ir_valid` -> `IR Validity`
- `ir_accurate` -> `IR Accuracy`
- `grounding_correct` -> `Grounding Accuracy`
- `repair_success` -> `Repair Success Rate`

`mission.exe Success Rate` 按：

```text
mission_status == PASS 的样本数 / 总样本数
```

## 7. 当前实现

对应实现文件：

- `docs/machine/evaluation_protocol.json`
- `scripts/evaluate_protocol.py`

统一评测脚本职责：

- 读取方法目录下的 `summary.json` 和 `results.jsonl`
- 若存在 `generated_scripts/`，则调用当前 `static_checker_v1` 重算静态指标
- 生成统一 scoreboard
- 为不适用指标返回 `null`

## 8. 排名规则

v1 排序优先级：

1. `mission.exe Success Rate`
2. `Semantic Match Rate`
3. `Static Pass Rate`
4. `Script Correctness`

原因很直接：

- 最终研究目标是提升可执行率
- 可执行但语义不对也不能算成功
- 静态通过比纯语法正确更接近最终目标

## 9. 已知限制

- `benchmark` 主要覆盖 Type A，因此 IR / Grounding / Repair 指标在当前只能部分留空。
- `Semantic Match Rate` 仍依赖现有 benchmark 的启发式判定，不是完整语义执行评测。
- Static checker 更新后，旧 baseline 的静态指标会发生变化，因此统一协议默认重算静态结果。

## 10. 与后续任务关系

- Task-010 产出 Grounding 结果后，可正式启用 `Grounding Accuracy`
- Task-011 / Task-013 产出 IR 后，可正式启用 `IR Validity` 和 `IR Accuracy`
- Task-012 / Task-014 产出 Repair 结果后，可正式启用 `Repair Success Rate`
- Task-016 / Task-017 可直接复用本协议比较 IR-only 和各类消融版本
