# Docs Layout

`docs/` 现在按主要使用对象分成三类：

## `docs/machine/`

机器可读、适合脚本直接加载的文件：

- `afsim_ir_schema_v1.json`
- `entity_mapping_v1.json`
- `error_taxonomy_v1.json`
- `evaluation_protocol_v1.json`
- `ir_examples_v1.jsonl`

## `docs/model_prompt/`

适合在 Agent / 大模型阶段按需提供的规则文档：

- `afsim_ir_schema_v1.md`
- `intent_parsing_spec_v1.md`
- `entity_mapping_v1.md`
- `verification_rules_v1.md`
- `hierarchical_generation_spec_v1.md`
- `repair_workflow_v1.md`
- `execution_repair_spec_v1.md`
- `agent_workflow_v1.md`

## `docs/human_readme/`

主要给人阅读、审查、写论文或复盘使用的说明文档：

- `AFSIM组件关系分析文档.md`
- `AFSIM错误分类体系_v1.md`
- `evaluation_protocol_v1.md`

## 使用原则

- 程序优先读取 `docs/machine/`
- 模型参考优先读取 `docs/model_prompt/`
- 人工审阅优先阅读 `docs/human_readme/`
