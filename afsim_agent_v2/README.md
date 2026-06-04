# AFSIM Agent v2

当前版本是 LLM-only 主方法评估管道：不使用 deterministic scaffold、demo 复制或 IR 后处理兜底。

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

- `BV1-001`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-002`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-004`: initial_static_pass=False, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-005`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-003`: initial_static_pass=False, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-008`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-010`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-006`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-007`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=True
- `BV1-009`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=False, llm_execution_repair=True
- `BV1-011`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-012`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-013`: initial_static_pass=False, final_static_pass=False, mission_status=PASS, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-016`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=True
- `BV1-015`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=False, llm_execution_repair=True
- `BV1-014`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
- `BV1-019`: initial_static_pass=False, final_static_pass=False, mission_status=PASS, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-018`: initial_static_pass=False, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-020`: initial_static_pass=True, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=True
- `BV1-017`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
- `BV1-023`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-025`: initial_static_pass=True, final_static_pass=True, mission_status=PASS, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=False
- `BV1-021`: initial_static_pass=False, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
- `BV1-022`: initial_static_pass=False, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=False
- `BV1-026`: initial_static_pass=True, final_static_pass=True, mission_status=FAIL, generation_mode=llm_only_static_pass, llm_static_repair=False, layer_regeneration=False, llm_execution_repair=True
- `BV1-027`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
- `BV1-024`: initial_static_pass=False, final_static_pass=False, mission_status=FAIL, generation_mode=llm_only_static_fail, llm_static_repair=True, layer_regeneration=True, llm_execution_repair=True
