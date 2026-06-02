# AFSIM Dataset v1

## 目标

本目录把 benchmark_v1 扩展为多任务数据集雏形，覆盖调研建议中的 Type A-F，并补充首版泛化切分。

## 文件

- `type_a_instruction_to_script.jsonl`: 指令 -> 脚本
- `type_b_script_to_instruction.jsonl`: 脚本 -> 指令
- `type_c_instruction_to_ir.jsonl`: 指令 -> IR
- `type_d_ir_to_script.jsonl`: IR -> 脚本
- `type_e_error_repair.jsonl`: 错误脚本 + 报错 -> 修复脚本
- `type_f_log_to_aar.jsonl`: log -> AAR
- `splits_v1.json`: 首版泛化切分标签

## 关系

- Type A 同时由 `benchmarks/benchmark_v1/tasks.jsonl` 提供全量 27 条，由本目录提供 5 条 starter set。
- Type C/D 的 IR 当前为 draft，将由 Task-006 固化。
- Type E 使用 `baseline_rag_v1` 的失败脚本和 mission logs，修复目标为对应 oracle demo。
- Type F 使用官方 demo 的 `mission.exe` 验证日志生成简短 AAR。

## 状态

当前 Type A-F 每类各 5 条 starter set，均由已验证通过的官方 demo 改写或作为目标脚本。后续可扩展到全部 27 条任务，并增加内部模板、历史脚本和人工修订描述。
