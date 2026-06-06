# AFSIM IR Schema v1

## 1. 目标

本文定义自然语言意图解析与 AFSIM 脚本生成之间使用的第一版 AFSIM 中间表示。

这个 schema 的用途包括：

- 从用户需求中提取意图
- 将意图映射到 AFSIM 平台与组件类型
- 支持分层脚本生成
- 支持静态检查
- 支持基于 benchmark 期望的语义评估

机器可读的 schema 文件位于 [afsim_ir_schema_v1.json](/C:/Users/28912/Desktop/afsim-script-generator-main/docs/machine/afsim_ir_schema.json:1)。

## 2. 设计原则

1. IR 表达的是场景意图，而不是最终脚本语法。
2. 即使最终 AFSIM 脚本会通过 route、processor、sensor 或 weapon 来实现，任务语义也必须在 `tasks` 中显式表达。
3. 平台数量、阵营、任务和位置必须是 IR 的一等字段。
4. Grounding 可以通过 `*_hint` 字段和 `grounding_hints` 暂时保持不完整。
5. 这个 schema 要足够严格，便于验证，同时又要足够简单，方便在早期实验阶段人工编写。

## 3. 必需核心字段

`schema_version`

- 固定值：`afsim_ir_v1`

`scenario`

- 场景元信息。
- 必须包含 `name` 和 `duration`。

`sides`

- 定义有效阵营，例如 `blue`、`red`、`neutral`。

`entities`

- 场景中的主要平台实例或平台组。
- 平台角色、数量、阵营和位置绑定都在这里表达。

`tasks`

- 任务意图。
- 一个任务后续可以映射为 route 逻辑、processor 行为、command chain 结构、sensor 配置或 weapon 使用逻辑。

## 4. 主要对象

`scenario`

- `name`：稳定的场景标识。
- `description`：可选的人类可读摘要。
- `duration`：包含 `value` 和 `unit` 的持续时间对象。
- `domains`：可选领域标签，例如 `air`、`surface`、`space`。
- `outputs`：期望输出，例如 `mission_log`、`heatmap`、`event_output`。

`locations`

- 可复用的点位或区域。
- 当场景包含起飞点、巡逻锚点、被保护目标或轨道锚点时使用。

`routes`

- 抽象运动计划。
- 每条 route 至少包含一个或多个 waypoint。

`platform_templates`

- 高层实体与 AFSIM 具体类型之间的可选模板层。
- 当多个实体共享同一套组件时尤其有用。

`components`

- 按 `movers`、`sensors`、`weapons`、`processors`、`comms` 分类的抽象组件目录。
- 每个组件都可以通过 `type_hint` 保持部分 grounding 状态。

`entities`

- IR 中最重要的作战单元。
- 必需字段：
  - `id`
  - `role`
  - `side`
  - `quantity`
- 常见可选字段：
  - `domain`
  - `template_ref`
  - `platform_type_hint`
  - `component_refs`
  - `initial_location_ref`
  - `route_ref`

`tasks`

- 显式任务表示。
- 必需字段：
  - `id`
  - `type`
  - `assignee_refs`
- 可选字段：
  - `target_refs`
  - `location_refs`
  - `parameters`

`constraints`

- 编码后续静态检查应遵守的归一化规则。
- 当前关键字段：
  - `unit_system`
  - `coordinate_format`
  - `required_fields`

`expected_events`

- 用于评测或修复的事件级成功标准。

`grounding_hints`

- 自然语言与 grounded AFSIM 实体之间的临时桥梁。
- 随着 grounding 库逐步完善，这些字段应逐渐减少。

## 5. 对 Task-006 的最小覆盖

这个 v1 schema 已明确覆盖任务 006 所要求的最小字段：

- Platform：`entities`、`platform_templates`
- Quantity：`entities[].quantity`
- Side：`entities[].side`、`sides`
- Mission：`tasks`
- Location：`locations`、`routes`、`entities[].initial_location_ref`

## 6. 映射建议

自然语言到 IR：

- 用户提到的平台实体 -> `entities.role`、`platform_type_hint`、`grounding_hints`
- 用户提到的数量 -> `entities.quantity`
- 用户提到的阵营 -> `entities.side`
- 用户提到的区域、站点、起点、巡逻锚点 -> `locations`
- 用户提到的运动路径或巡逻计划 -> `routes`
- 用户提到的行为或作战意图 -> `tasks`

IR 到 AFSIM 脚本：

- `platform_templates` 和 `components` -> 可复用 AFSIM 块
- `entities` -> `platform_type` 与 `platform` 结构
- `routes` -> `route` 块或 mover 参数
- `tasks` -> processor 逻辑、route 选择、weapon 配置、comm 绑定和验证条件

## 7. 验证规则

在 IR 校验阶段：

- 每个 `entity.side` 都必须存在于 `sides`
- 每个 `component_ref`、`template_ref`、`location_ref`、`route_ref` 和任务引用都必须可解析
- `quantity` 必须大于等于 1
- `duration`、速度、高度等数值必须保留单位
- 任务意图不能只隐藏在自由文本里，必须出现在 `tasks` 中

## 8. v1 非目标

- 不是要完整覆盖所有 AFSIM 命令。
- 不是要完整覆盖所有 AFSIM 内置类型的 grounding 目录。
- 不是要保证脚本文本和 IR 之间无损双向还原。

## 9. 与后续任务的关系

- Task-007 将定义如何把自然语言解析到这份 schema。
- Task-008 将以这份 schema 作为静态检查与修复的语义参照。
- Task-010 将把很多 `*_hint` 字段替换成真正的 grounding 映射。
- Task-011 将以这份 schema 作为分层脚本生成的输入。
