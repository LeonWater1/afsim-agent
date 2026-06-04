# AFSIM Agent v2

LLM-only evaluation pipeline - no deterministic scaffold, demo copy, or IR postprocess fallback.

## Workflow

- Natural Language
- LLM Intent Parsing
- AFSIM-IR Schema Validation
- Grounding
- Hierarchical Generation Plan
- LLM Script Generation
- Static Verification
- LLM Static Repair
- mission.exe
- LLM Execution Repair

## Results

- model: `deepseek-v4-pro`

- `BV1-012`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=True
- `BV1-022`: initial_static_pass=False, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
- `BV1-017`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=layered_executor_v1, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
