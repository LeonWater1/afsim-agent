# AFSIM Benchmark v1

## 目标

本目录用于承载 Phase 1 的最小可运行 benchmark。v1 的首要目标不是追求大规模，而是让后续 Direct Prompt、RAG Prompt、IR 生成、Grounding、静态检查和 self-repair 能在同一批任务上比较。

## 当前版本

当前版本为 `v1.0-demo`，包含 27 条自然语言场景生成任务。所有 oracle 均来自 `C:\Program Files\afsim-2.9.0-win64\demos` 的真实 AFSIM demo，并已镜像到本目录下的 `demo_sources/` 以便在可写目录中稳定运行。每条任务记录：

- `id`: 样例编号
- `difficulty`: 难度层级
- `input`: 自然语言需求
- `covered_components`: 需要覆盖的 AFSIM 组件
- `expected_ir_focus`: 设计 AFSIM-IR 时必须显式表达的字段
- `evaluation_focus`: 后续评测重点
- `oracle_status`: 对应参考脚本状态
- `mission_status`: `mission.exe` 执行验证结果
- `source_type`: 当前均为 `afsim_demo`
- `source_hint`: oracle 脚本路径
- `demo_id`: 候选筛选阶段的原始编号

## 数据文件

- `tasks.jsonl`: 27 条 demo-derived benchmark 任务
- `demo_sources/`: 从 AFSIM 官方 demos 镜像出的 oracle 源文件和依赖文件
- `validation_results.json`: 最近一次批量验证汇总
- `validation_logs/`: 每个脚本的 `mission.exe` 执行日志

## 状态说明

`oracle_status` 当前取值：

- `source_available`: 已有真实 demo 脚本作为 oracle。

当前 `tasks.jsonl` 中 27 条任务均为 `source_available`，且 `mission_status` 均为 `PASS`。最近一次批量验证结果为 27 PASS / 0 FAIL / 0 TIMEOUT。

## 下一步

1. 建立静态检查规则，至少检查单位、块闭合、引用完整性和坐标格式。
2. 将本 benchmark 接入 Direct Prompt 与 RAG Prompt baseline。
3. 后续扩展到 50 条样例时，继续使用 `scripts/validate_benchmark.py` 做批量验证。
