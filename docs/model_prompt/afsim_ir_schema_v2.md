# AFSIM-IR v2 设计说明

## 1. 升级目标

在 `AFSIM-IR v1` 基础上补齐场景逻辑（Logic）与评估（Evaluation）两层表达能力，使 IR 能描述"怎么打"和"怎么判胜负"，而不只是"有什么"。

## 2. 与 v1 的兼容性

v2 是 v1 的**纯增量**扩展：

- 所有 v1 字段保持不变，`additionalProperties` 已对新增层放开
- `schema_version` 改为 `"afsim_ir_v2"`
- 任何合法的 v1 IR 只需改 `schema_version` 即可通过 v2 schema 校验（`logic` 和 `evaluation` 均有 `default: {}`）
- Grounding / Generation 管线读取 v1 字段的逻辑不受影响；新字段仅在 v2 模式下消费

## 3. 六层信息架构

```
Scenario     — 场景名、时长、域、输出、起始时间
Side         — 阵营 id、别名、战术条令
Platform     — 平台模板、实体、组件引用
Mission      — 任务、航线、位置
Logic        — 行为规则、状态机、交战逻辑、触发逻辑    ← 新增
Evaluation   — 任务阶段、成功判据、观测指标            ← 新增
```

## 4. Logic 层

### 4.1 behavior_rules（行为规则）

描述"在什么条件下做什么"的战术行为规则。每条规则包含：

| 字段 | 说明 |
|------|------|
| `id` | 规则标识 |
| `description` | 人类可读描述 |
| `condition` | 触发条件（自然语言或伪代码） |
| `action` | 执行动作 |
| `priority` | 优先级（越高越优先） |
| `applies_to` | 适用实体/任务引用 |

示例：

```json
{
  "id": "intercept_on_detect",
  "description": "探测到目标后转向拦截",
  "condition": "sensor detects hostile track within 100 km",
  "action": "assign intercept task, enable weapon",
  "priority": 10,
  "applies_to": ["blue_fighter"]
}
```

### 4.2 state_machines（状态机）

描述 processor 的状态转换逻辑：

| 字段 | 说明 |
|------|------|
| `id` | 状态机标识 |
| `processor_ref` | 绑定到的 processor 组件 |
| `initial_state` | 初始状态名 |
| `states` | 状态列表，含 `on_entry`、`transitions` |

### 4.3 engagement_logic（交战逻辑）

描述交战决策机制：

| 字段 | 说明 |
|------|------|
| `style` | `brawler` / `scripted` / `quantum_agent` / `custom` |
| `rules` | 目标选择与武器分配规则 |
| `target_prioritization` | 目标优先级排序 |

### 4.4 trigger_logic（触发逻辑）

事件-条件-动作（ECA）规则：

| 字段 | 说明 |
|------|------|
| `trigger` | `on_detect` / `on_weapon_launch` / `on_platform_destroyed` / `on_time` / `on_enter_area` 等 |
| `source_refs` | 触发来源实体/传感器 |
| `action` | 触发后执行的动作 |
| `target_refs` | 动作影响的目标 |

## 5. Evaluation 层

### 5.1 mission_phases（任务阶段）

将任务分解为有序阶段，每个阶段有独立目标和进出条件：

```json
{
  "id": "phase_patrol",
  "name": "Patrol Phase",
  "order": 1,
  "duration": {"value": 300, "unit": "sec"},
  "objectives": [
    {"id": "obj_detect", "description": "Detect hostile aircraft in patrol zone"}
  ],
  "exit_condition": "hostile detected OR patrol duration exceeded"
}
```

### 5.2 success_criteria（成功判据）

定义任务整体成功/失败条件：

| 字段 | 说明 |
|------|------|
| `overall_condition` | 自然语言整体判据 |
| `minimum_phases_required` | 必须成功的阶段 id 列表 |
| `score_thresholds` | 数值评分阈值 |

### 5.3 observation_metrics（观测指标）

可量化的评估指标：

| 字段 | 说明 |
|------|------|
| `metric_type` | `detection_count` / `kill_count` / `survival_count` / `time_to_complete` / `coverage_percent` / `custom` |
| `target_refs` | 指标针对的实体 |
| `aggregation` | `sum` / `max` / `min` / `average` / `at_end` / `boolean` |
| `threshold` | 成功阈值 |

## 6. v1 → v2 升级路径

1. 将 `schema_version` 从 `"afsim_ir_v1"` 改为 `"afsim_ir_v2"`
2. 如需描述行为规则，添加 `logic` 对象
3. 如需定义评估标准，添加 `evaluation` 对象
4. 现有 `expected_events` 仍可用于简单场景；`evaluation.mission_phases` 用于多阶段复杂任务
5. v1 字段（entities、tasks、routes、constraints）无需修改

## 7. 与其他模块的接口

- **Grounding**：`logic.engagement_logic.style` 决定 processor 选型（brawler → WSF_BRAWLER_PROCESSOR、scripted → WSF_TASK_PROCESSOR）。`evaluation.mission_phases` 的 `task_refs` 指向已存在的 task，不引入新引用类型。
- **Generation**：`logic.*` 映射到 script processor 的 behavior_tree / state machine / execute 块。`evaluation.*` 映射到 `expected_events` + `event_output` 结构。
- **Static Checker**：`evaluation.observation_metrics` 类型枚举可被 checker 验证。

## 8. 与 v1 的关系

本文件是 `afsim_ir_schema_v1.md` 的升级说明。v1 的完整字段语义文档仍有效，v2 仅在此基础上新增 Logic 和 Evaluation 两层。
