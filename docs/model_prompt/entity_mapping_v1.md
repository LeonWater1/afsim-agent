# Entity Mapping v1

## 1. 目标

本文档定义 Task-010 的最小 Grounding 库。

它的职责不是把所有自然语言都直接变成最终脚本文本，而是把：

```text
用户概念 / IR hint
```

映射成：

```text
项目内稳定的 canonical grounding target
```

再由后续分层生成模块把 canonical target 落到具体 AFSIM 脚本结构。

对应机读文件：

- `docs/machine/entity_mapping_v1.json`

对应最小接口：

- `scripts/grounding_library_v1.py`

## 2. 设计原则

- 不臆造未经验证的 `WSF_*` 类型。
- 优先使用 benchmark_v1 和官方 demo 中已经出现过的目标类型。
- 允许先映射到项目内 canonical template / bundle，再在 Task-011 落到具体脚本。
- 如果无法可靠 grounding，就保留 `platform_type_hint` / `type_hint`，并通过 `grounding_hints` 上抛，而不是硬猜。

## 3. 覆盖范围

### 3.1 平台类

v1 至少覆盖：

- `aircraft`
- `fighter`
- `radar_site`
- `ship`
- `missile_site`

为了覆盖 `benchmark_v1`，当前额外补充：

- `hvaa`
- `sensor_platform`
- `detector`
- `relay`
- `observer`

### 3.2 任务类

v1 至少覆盖：

- `CAP`
- `patrol`
- `intercept`
- `strike`
- `escort`
- `detect`
- `engage`

### 3.3 组件类

当前最小集合：

- mover
- sensor
- weapon
- processor
- comm

### 3.4 阵营类

- `blue`
- `red`
- `neutral`

## 4. Grounding 输出形式

每条映射都尽量产出以下信息：

- `canonical_id`
- `canonical_role`
- 可匹配别名
- 可接受的 `platform_type_hint` 或 `type_hint`
- `grounding_target`
- `provenance`

其中 `grounding_target.target_kind` 当前允许：

- `platform_template`
- `wsf_type`
- `behavior_bundle`
- `processor_profile`
- `comm_profile`
- `weapon_profile`

这些目标分别服务于：

- 平台模板层
- 组件类型层
- 任务行为层
- 处理器生成轮廓层
- 通信拓扑轮廓层
- 武器结构轮廓层

也就是说，Grounding v1 不再只返回一个扁平的 `WSF_*` 字符串；对于确实共享同一底层 `WSF_*`、但脚本结构明显不同的对象，v1 会保留：

- `backing_wsf_type`
- `script_pattern`
- `required_*` 结构约束

这样 Task-011 可以继续分层生成，而不会因为 Grounding 过粗把关键结构信息丢掉。

## 5. 为什么不用“直接映射成完整脚本”

因为 Task-010 的目的不是跳过 IR 和分层生成，而是把“语义概念”和“脚本实体”之间的桥先搭起来。

例如：

- `fighter_aircraft` -> `fighter_aircraft_basic`
- `radar_sensor` -> `WSF_RADAR_SENSOR`
- `escort` -> `escort_behavior`

后续仍需要 Task-011 把这些 target 组织成：

- `platform_type`
- `mover`
- `sensor`
- `weapon`
- `processor`
- `comm`
- `route`

其中对 `processor_profile` / `comm_profile` / `weapon_profile`，Task-011 应同时参考：

- Grounding 返回的 profile 元数据
- IR 原始 `type_hint`
- IR 原始 `role`

避免把像 `comm_system` 这样的泛化 hint 直接压成单一实现。

## 6. 当前保守策略

以下情况不强行 grounding：

- 用户给出具体型号，但项目里没有 demo-backed template
- 任务语义存在歧义，可能对应多个 processor / behavior 组合
- hint 只能说明“像某类东西”，但不能稳定落到现有 AFSIM 实体

在这些情况下：

- 保留原始 `*_hint`
- 记录 `grounding_hints`
- 后续由扩展版 Grounding 库或人工确认补全

## 7. 验证标准

Task-010 完成后，至少应满足：

- `fighter_aircraft`、`radar_platform`、`sam_platform`、`comm_system`、`radar_sensor`、`air_to_air_missile` 等常见 hint 能解析
- `acoustic_target`、`iads_command_platform`、`area_air_defense`、`group_communication` 等当前 IR 示例已出现的 hint 能解析
- `blue` / `red` / `neutral` 能统一标准化
- `escort`、`intercept`、`detect`、`strike` 等任务词能映射到稳定的 behavior target
- 对 `battle_manager_processor` / `sensor_manager_processor` / `fighter_engagement_processor` / `escort_processor` 能保留足够区分度
- 对 `datalink` / `group_comm` / `sam_weapon` 能保留生成期所需的拓扑或子结构提示
- 对 `agm` / `air_to_ground_missile` 能保留 spawned platform、制导、引信和传感器等结构提示
- 不产生新的幻觉 `WSF_*` 类型

推荐直接运行：

```bash
python scripts/grounding_library_v1.py --validate
```

该命令除结构检查外，还会顺带统计 `docs/machine/ir_examples_v1.jsonl` 的 hint 覆盖情况。

如果 `ir_examples_v1.jsonl` 中存在损坏行，验证器会跳过这些行并在 `skipped_invalid_lines` 中报告，而不是直接崩溃。

## 8. 与后续任务关系

- Task-011 使用本库把 IR 中的 `platform_type_hint` / `type_hint` 解析为可落地 target
- Task-013 Minimal Agent Loop 可直接调用本库完成 first-pass grounding
- Task-017 后续可评估 `Grounding Accuracy`
