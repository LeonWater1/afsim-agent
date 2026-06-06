# Benchmark v2

## 概述

Benchmark v2 是 AFSIM 场景生成能力的**大规模多任务统一评测集**，覆盖从自然语言到最终可执行脚本的完整链路。与 Benchmark v1（仅端到端 Type A）不同，v2 覆盖 **Type A-E 五类数据对**，每类 **50 条**，共 **250 条唯一样本**，支持分阶段评测 Intent Parsing、IR Generation、Script Generation 和 Self Repair 四个独立模块。

## 与 Benchmark v1 的区别

| 维度 | Benchmark v1 | Benchmark v2 |
|------|:-----------:|:-----------:|
| 任务数量 | 27 | **250** (Type A-E 各 50) |
| 数据类别 | 仅 Type A（指令→脚本） | Type A/B/C/D/E 五类 |
| 来源覆盖 | 21 官方 demo 目录 | **50/66** 官方 demo 目录 |
| IR 覆盖 | 无独立 IR 数据对 | Type C（指令→IR）、Type D（IR→脚本） |
| Repair 覆盖 | 无 | Type E（错误→修复），覆盖 E001~E010 |
| 组件覆盖 | ~10 种 | **16 种**（含 Space/Cyber/Ballistic/Swarm/IADS/Guidance） |
| 泛化切分 | 无 | 10 维正交切分 |
| Schema 版本 | afsim_ir_v1 | afsim_ir_v1 + afsim_ir_v2 |
| 验证方式 | 手动 | `validate_benchmark.py` 自动化 |

## 五类数据对

### Type A：指令 → 脚本（50 条）
端到端场景生成主评测。50 条样本覆盖 50 个官方 demo 目录，每条的 `instruction` 来自对应 demo 目录 README.md 的自然语言描述及文件级上下文。每条绑定真实 oracle 脚本路径，脚本已复制至 `demo_sources/`。

### Type B：脚本 → 指令（50 条）
反向评测——从已有脚本生成自然语言描述。50 条样本对应 Type A 的全部脚本，标注为 `auto_generated`（待人工抽样修订）。`human_review_status` 字段追踪修订状态。

### Type C：指令 → IR（50 条）
意图理解与中间表示生成评测。50 条样本使用 Type A 的自然语言指令，目标输出为 `afsim_ir_v2` 格式。`ir` 字段当前为 `null`，`ir_status = pending_generation`，等待 Intent Parser 生成后回填并通过 schema 校验。

### Type D：IR → 脚本（50 条）
领域落地模块评测。50 条样本来源：
- 5 条源自 `ir_examples_v2.jsonl`（afsim_ir_v2）
- 9 条源自 `ir_examples_v1.jsonl`（afsim_ir_v1）
- 27 条源自 benchmark 的 oracle 脚本对
- 9 条源自新选 demo，标注 `IR pending`

每条样本包含 IR 来源、脚本路径、静态检查结果 (`static_check_result`) 和 mission.exe 执行结果 (`mission_result`) 占位。

### Type E：错误脚本 + 报错 → 修复脚本（50 条）
Self-repair 评测。50 条样本覆盖 **全部 10 个错误类型**（E001~E010），每种 5 条：

| 错误 ID | 说明 | 条数 |
|---------|------|:--:|
| E001 | 缺少单位声明 | 5 |
| E002 | 块未闭合（缺少 end_xxx） | 5 |
| E003 | 引用不存在对象 | 5 |
| E004 | 坐标格式错误 | 5 |
| E005 | 幻觉实体（不存在于官方文档的 WSF_*） | 5 |
| E006 | 必填字段缺失 | 5 |
| E007 | 组件上下文错误 | 5 |
| E008 | 脚本 API 错误 | 5 |
| E009 | 外部资源缺失 | 5 |
| E010 | 结构不一致 | 5 |

错误来源：`baseline_direct_v1` 和 `baseline_rag_v1` 的真实失败案例。

## 数据来源

### 官方 demo 目录（50 个）

Type A/B/C 的 oracle 脚本来自 `C:\Program Files\afsim-2.9.0-win64\demos` 下 50 个目录的场景 `.txt` 文件，覆盖全部 16 种组件类型：

```
acoustic, aea_iads, air_to_air, alternate_locations, alv_routing,
ballistic, ballistic_missile_shootdown, bearing_only, behavior_tree,
brawler, chaff, cislunar, ciws, comm, coverage_demos, cyber,
distributed_operations, draw, electronic_warfare, engage,
example_scripts, exchange_proc, fires, gun_engagement, heatmap,
hel, iads, iads_c2_demos, kinematic_mover, l16_j11,
laser_designator, launcher, logistics, multiresolution_demos,
new_guidance, noise_cloud, orwaca_iads, oth_radar, outer_air_battle,
p6dof, parachute, route_finder_demos, satellite_demos, script_demos,
sensor_demos, ship_ad, shooter, simple_scenario, space_operations,
swarm, tbm_demos, terrain_following, timeline, traffic_demos, wargame
```

Type D 额外引用 benchmark 已使用的 demo 脚本，对接到 `ir_examples_v1` 和 `ir_examples_v2`。

Type E 错误样本来自 `baseline_direct_v1/generated_scripts/` 和 `baseline_rag_v1/generated_scripts/` 中的真实失败生成结果。

## 泛化切分

见 `splits_v2.json`。10 个正交切分维度（同一任务可属于多个切分）：

| 切分 | 说明 |
|------|------|
| seen_templates | 已在 v1 IR examples 中出现的模板模式 |
| unseen_compositions | 新领域或新组件组合 |
| single_platform | 单平台/最少实体数 |
| multi_platform | 多平台/编队/跨阵营 |
| static_deployment | 静态配置，无动态任务逻辑 |
| dynamic_mission | 含时序任务/交战/动态行为 |
| known_alias | 已存在于 entity_mapping_v2 的别名 |
| novel_alias | 新领域特有名称 |
| text_only | 纯文本输入 |
| text_plus_sketch | 文本+草图（预留，当前为空） |

## 字段格式

所有 JSONL 文件每行为一个 JSON 对象。通用字段：
- `id`：样本唯一标识（如 `BV2-A-001`）
- `type`：A / B / C / D / E
- `source_demo`：官方 demo 来源路径

各 Type 特有字段见对应 JSONL 文件的第一个样本。

## 验证方式

```bash
python benchmarks/benchmark_extended/validate_benchmark.py
```

验证内容：
1. 5 个 JSONL 文件均可解析，每类 ≥ 5 条
2. 250 个样本 ID 无重复
3. Type A oracle 脚本文件全部存在（50/50）
4. Type E 错误来源可追溯
5. 输出 `validation_report.json`

当前验证结果：
```json
{
  "overall_status": "PASS",
  "total_unique_ids": 250,
  "total_errors": 0,
  "oracle_files": {"found": 50, "missing": 0}
}
```

## 构建方式

```bash
python benchmarks/benchmark_extended/build_full.py
```

该脚本自动扫描 `C:\Program Files\afsim-2.9.0-win64\demos` 下全部 66 个 demo 目录，读取 README.md 提取自然语言描述，选择 50 个代表性场景文件，复制到 `demo_sources/`，并生成全部五类 JSONL 数据文件。

## 与外部模块的接口

- **afsim_ir_schema_v1 / v2**：Type C/D 的 IR 数据符合对应 schema
- **static_checker_v1**：Type D/E 的静态检查结果使用统一检查器
- **evaluation_protocol_v1**：评测口径与 v1 保持一致，新增 IR 维度指标
- **grounding_library_v2**：Type C 中的 novel_alias 实体预期触发 partial/unresolved 匹配
- **llm_intent_parser_v1**：Type C 的 `pending_generation` 条目待解析器生成 IR 后回填
