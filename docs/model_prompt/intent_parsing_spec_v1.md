# Intent Parsing Spec v1

## 1. 目标

本文档定义从自然语言需求到 `AFSIM-IR v1` 的转换规则。

Intent Parsing 的职责不是生成 AFSIM 脚本，而是把用户需求整理成结构化场景意图，供后续 Grounding、分层生成、静态检查和修复模块使用。

输入：

```text
自然语言场景需求
```

输出：

```text
符合 afsim_ir_schema_v1 的 AFSIM-IR
```

关联 schema：

- [afsim_ir_schema_v1.json](/C:/Users/28912/Desktop/afsim-script-generator-main/docs/machine/afsim_ir_schema_v1.json:1)
- [afsim_ir_schema_v1.md](/C:/Users/28912/Desktop/afsim-script-generator-main/docs/model_prompt/afsim_ir_schema_v1.md:1)

## 2. 基本原则

1. 先抽取意图，再考虑脚本语法。
2. 明确字段优先于自由文本描述。
3. 不确定的 AFSIM 类型不得臆造，放入 `platform_type_hint`、`type_hint` 或 `grounding_hints`。
4. 数量、阵营、任务和位置必须尽量显式化。
5. 用户没有给出的信息可以使用保守默认值，但必须能被后续模块识别和覆盖。

## 3. 抽取字段

### 3.1 场景名称

来源：

- 用户显式给出的场景名
- demo 名称
- 任务类型 + 组件类型自动生成

映射：

- `scenario.name`
- `scenario.description`

规则：

- `scenario.name` 使用稳定英文标识，例如 `air_to_air_1v1`。
- 中文原始描述可放入 `scenario.description`。
- 如果输入来自 benchmark，可保留 demo 名称作为名称依据。

### 3.2 平台

来源：

- 飞机、舰船、雷达站、导弹、车辆、卫星、通信节点等实体名
- “蓝方两架战斗机”“红方防空阵地”等复合表达

映射：

- `entities[].id`
- `entities[].role`
- `entities[].domain`
- `entities[].platform_type_hint`
- `platform_templates[]`
- `grounding_hints[]`

规则：

- 每类平台至少生成一个 `entity`。
- 具体平台型号未知时，不直接写 AFSIM 类型，先写 `platform_type_hint`。
- 一个自然语言平台组可以对应一个 `entity`，数量由 `quantity` 表达。

示例：

```json
{
  "id": "blue_fighters",
  "role": "fighter",
  "side": "blue",
  "quantity": 2,
  "domain": "air",
  "platform_type_hint": "fighter_aircraft"
}
```

### 3.3 数量

来源：

- “一架”“两艘”“3 个雷达站”
- “编队”“小队”“群组”等模糊数量词

映射：

- `entities[].quantity`

规则：

- 明确数字直接转换为整数。
- “一对一”映射为双方各 `quantity=1`。
- “二对二”映射为双方各 `quantity=2`。
- 模糊数量词默认不臆造具体数量，除非任务上下文已有约定；可保守设为 `1` 并在 `constraints.required_fields` 或 `grounding_hints.notes` 中标注需要确认。

### 3.4 阵营

来源：

- 蓝方、红方、中立方
- 我方、敌方、友方、目标方

映射：

- `sides[]`
- `entities[].side`

规则：

- 默认使用 `blue` 和 `red`。
- “我方”“友方”通常映射为 `blue`。
- “敌方”“目标方”通常映射为 `red`。
- 所有 `entities[].side` 必须能在 `sides[]` 中找到。

### 3.5 区域与位置

来源：

- 经纬度
- 命名地点
- 巡逻区、拦截区、防御区、目标区
- 起点、终点、航线点、轨道锚点

映射：

- `locations[]`
- `routes[]`
- `entities[].initial_location_ref`
- `tasks[].location_refs`

规则：

- 明确点位放入 `locations`，`kind=point`。
- 区域放入 `locations`，`kind=area`，可使用 `radius`。
- 航线或巡逻路线放入 `routes`。
- 如果位置缺失但任务需要位置，在 `constraints.required_fields` 中加入对应字段。

### 3.6 任务

来源：

- 探测、跟踪、巡逻、拦截、护航、打击、防空、通信、干扰、修复、生成报告等动词或任务名

映射：

- `tasks[]`
- `expected_events[]`

规则：

- 每条需求至少生成一个 `task`。
- 任务执行者放入 `tasks[].assignee_refs`。
- 任务对象放入 `tasks[].target_refs`。
- 任务地点放入 `tasks[].location_refs`。
- 任务的成功条件可放入 `expected_events`。

常用任务类型建议：

- `detect`
- `track`
- `patrol`
- `transit`
- `air_engage`
- `intercept`
- `escort`
- `strike`
- `area_air_defense`
- `communication`
- `jamming`
- `apply_script_effect`
- `generate_output`

### 3.7 武器

来源：

- 导弹、舰炮、近防炮、地空导弹、空空导弹、炸弹、箔条、干扰器

映射：

- `components.weapons[]`
- `entities[].component_refs`
- `grounding_hints[]`

规则：

- 用户提到武器能力时，建立抽象 weapon 组件。
- 不确定具体 AFSIM weapon 类型时使用 `type_hint`。
- 反制品如箔条可作为 `weapon` 或 `countermeasure` 风格的 weapon 组件处理，后续由 Grounding 决定落地方式。

### 3.8 传感器

来源：

- 雷达、声学传感器、ESM、EO/IR、激光指示器、仅方位传感器

映射：

- `components.sensors[]`
- `entities[].component_refs`
- `grounding_hints[]`

规则：

- 用户提到探测、跟踪、识别，通常需要 sensor 组件。
- 如果任务是 `detect` 或 `track` 但未出现传感器，应在 `constraints.required_fields` 中记录缺失项。
- 不确定具体 AFSIM sensor 类型时使用 `type_hint`，不要造 `WSF_*` 类型。

### 3.9 约束条件

来源：

- 时间、速度、高度、距离、频率、输出要求、必须可执行、必须使用官方 demo 风格等约束

映射：

- `constraints`
- `scenario.duration`
- `scenario.outputs`
- component `parameters`
- route waypoint `speed`
- position `altitude`

规则：

- 所有数值约束必须保留单位。
- 输出要求如 log、event、heatmap 放入 `scenario.outputs`。
- “必须可执行”“通过 mission.exe”属于评测约束，可记录到 `constraints.required_fields` 或后续 evaluation protocol。

## 4. 标准解析流程

1. 识别场景类型和主任务。
2. 抽取平台实体、数量和阵营。
3. 抽取位置、区域和路线。
4. 抽取传感器、武器、processor、comm 等组件需求。
5. 构造 `tasks`，明确执行者、目标和地点。
6. 构造 `expected_events`，表达最小成功条件。
7. 填充 `constraints`，记录单位、坐标格式和缺失字段。
8. 生成 `grounding_hints`，把未 grounded 的用户概念交给 Task-010。
9. 执行 IR schema 校验。

## 5. 歧义处理

平台歧义：

- 用户说“战机”但未给型号，使用 `platform_type_hint=fighter_aircraft`。
- 不直接映射为未经验证的 AFSIM 类型。

数量歧义：

- 用户说“若干”“多个”，先设定为 `1` 或保留待确认，具体策略由 benchmark 标注决定。

位置歧义：

- 用户没有给出坐标时，可以创建命名 location，例如 `patrol_area`，但不要编造精确经纬度。

任务歧义：

- 用户说“执行空战任务”，至少解析为 `air_engage`。
- 如果同时包含护航、防御、拦截，应拆成多个 task。

组件歧义：

- 用户说“探测目标”但没有指定 sensor，可生成抽象 sensor hint。
- 用户说“攻击目标”但没有指定 weapon，可生成抽象 weapon hint。

## 6. 输出格式要求

Intent Parsing 模块输出必须是一个完整 JSON object，顶层必须包含：

```json
{
  "schema_version": "afsim_ir_v1",
  "scenario": {},
  "sides": [],
  "locations": [],
  "routes": [],
  "platform_templates": [],
  "components": {},
  "entities": [],
  "tasks": [],
  "constraints": {},
  "expected_events": [],
  "grounding_hints": []
}
```

不允许输出 Markdown 包裹的 JSON，不允许混入解释文字。解释文字应由调用方另存。

## 7. 最小示例

输入：

```text
基于 air_to_air/1v1，生成一对一空战场景。
```

输出 IR 摘要：

```json
{
  "schema_version": "afsim_ir_v1",
  "scenario": {
    "name": "air_to_air_1v1",
    "description": "一对一空战场景",
    "duration": {
      "value": 300,
      "unit": "sec"
    },
    "domains": ["air"],
    "outputs": ["mission_log"]
  },
  "sides": [
    {"id": "blue", "display_name": "Blue"},
    {"id": "red", "display_name": "Red"}
  ],
  "entities": [
    {
      "id": "blue_fighter",
      "role": "fighter",
      "side": "blue",
      "quantity": 1,
      "domain": "air",
      "platform_type_hint": "fighter_aircraft",
      "component_refs": ["fighter_mover", "fighter_sensor", "fighter_weapon"]
    },
    {
      "id": "red_fighter",
      "role": "fighter",
      "side": "red",
      "quantity": 1,
      "domain": "air",
      "platform_type_hint": "fighter_aircraft",
      "component_refs": ["fighter_mover", "fighter_sensor", "fighter_weapon"]
    }
  ],
  "components": {
    "movers": [
      {"id": "fighter_mover", "role": "air_mover", "type_hint": "air_mover"}
    ],
    "sensors": [
      {"id": "fighter_sensor", "role": "air_search", "type_hint": "radar_sensor"}
    ],
    "weapons": [
      {"id": "fighter_weapon", "role": "air_to_air", "type_hint": "air_to_air_missile"}
    ]
  },
  "tasks": [
    {
      "id": "blue_engage_red",
      "type": "air_engage",
      "assignee_refs": ["blue_fighter"],
      "target_refs": ["red_fighter"]
    }
  ],
  "constraints": {
    "unit_system": "afsim_mixed",
    "coordinate_format": "lat_lon_dir",
    "required_fields": ["entities.side", "entities.quantity", "tasks"]
  },
  "expected_events": [
    {
      "id": "air_engagement_occurs",
      "type": "engagement",
      "actor_refs": ["blue_fighter", "red_fighter"],
      "success_condition": "双方进入空战交战过程"
    }
  ],
  "grounding_hints": [
    {
      "label": "fighter_aircraft",
      "target_kind": "platform",
      "candidate_types": [],
      "notes": "待 Task-010 Grounding 库映射到具体 AFSIM 平台模板"
    }
  ]
}
```

## 8. 质量检查清单

解析结果进入后续模块前，应检查：

- 是否包含 `schema_version=afsim_ir_v1`
- 是否包含 `scenario.name` 和 `scenario.duration`
- 是否至少有一个 `side`
- 是否至少有一个 `entity`
- 是否每个 `entity` 都有 `side` 和 `quantity`
- 是否至少有一个 `task`
- 是否所有引用字段都能解析，或被明确放入 `grounding_hints`
- 是否没有直接臆造未经验证的 `WSF_*` 类型
- 是否所有数值字段保留单位

## 9. 与后续任务关系

- Task-010 使用 `grounding_hints`、`platform_type_hint`、`type_hint` 建立最小 Grounding 库。
- Task-011 使用解析后的 IR 进行分层脚本生成。
- Task-018.1 使用本规范构造 `Type C：指令 -> IR` 数据。
- Task-016 使用本规范建立 IR-only baseline。
