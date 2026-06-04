# Hierarchical Generation Spec v1

## 1. 目标

Task-011 的目标不是让模型一次性输出完整 AFSIM 场景脚本，而是把：

```text
AFSIM-IR
-> Grounded IR
-> Layered Generation Plan
-> AFSIM Script Fragments
-> Final Scenario
```

拆成可检查、可回退、可修复的多层流程。

这一步直接承接：

- Task-006 `AFSIM-IR v1`
- Task-010 `Grounding Library v1`

并为后续任务提供输入：

- Task-012 `Self Repair Workflow`
- Task-013 `Minimal Agent Loop`

## 2. 核心原则

1. 禁止直接从自然语言或原始 IR 一步生成完整场景。
2. 每一层都必须有明确输入、明确输出、明确检查点。
3. Grounding 结果不能只看一个扁平 `WSF_*`，要同时参考：
   - `grounding_target`
   - 原始 `type_hint`
   - 原始 `role`
4. 如果某一层信息不足，应在该层停下并记录 `manual_review_required`，而不是继续臆造。
5. 优先支持 `benchmark_v1` 高频结构，再扩展复杂场景。

## 3. 输入契约

Task-011 的最小输入不是自然语言，而是：

- 合法 `AFSIM-IR v1`
- 已完成 first-pass grounding 的 IR

其中至少应包含：

- `scenario`
- `sides`
- `entities`
- `tasks`
- `components`
- 可选 `locations`
- 可选 `routes`

## 4. 分层顺序

### 4.0 Scenario Scaffold

先抽出全局骨架信息：

- 场景名
- 时长
- side 集合
- locations
- outputs
- constraints

这一层不生成主要作战实体，只负责场景外壳和全局元信息。

### 4.1 Platform Layer

这一层生成平台相关骨架：

- `platform_type` / `platform_template` 选择
- `platform` 实例
- `side`
- `quantity`
- `initial_location_ref`
- `route_ref`

主要依据：

- `entities[].role`
- `entities[].platform_type_hint`
- `resolve_platform(...)`

这一层不负责完整行为逻辑，只负责“谁在场、属于谁、站在哪、属于哪类平台”。

### 4.2 Sensor Layer

这一层生成与感知相关的组件：

- `sensor`
- sensor 参数轮廓
- sensor 与 platform / processor 的 `internal_link`

主要依据：

- `components.sensors`
- `entities[].component_refs`
- `resolve_component("sensor", ...)`

检查重点：

- sensor 是否都被实体引用
- sensor grounding 是否成功
- sensor profile 是否缺少后续必须的 link / receiver / antenna 信息

### 4.3 Weapon Layer

这一层生成武器相关结构：

- `weapon`
- spawned platform type
- fuse / seeker / guidance 等附属子结构
- 数量和武器效果

主要依据：

- `components.weapons`
- `entities[].component_refs`
- `resolve_component("weapon", ...)`

注意：

`weapon_profile` 不能被压缩成单纯一个 `WSF_*`。  
例如 `sam_weapon`、`agm` 都要求保留 spawned platform 和内部 processor / sensor 结构提示。

### 4.4 Mission Layer

这一层处理行为与协同逻辑，而不是静态载荷：

- `tasks`
- `routes`
- `processor`
- `comm`
- task-to-platform 绑定
- `report_to` / `group_join` / command-chain / assignment 逻辑

这里之所以把 `processor` 和 `comm` 放到 Mission Layer，而不是单独拆成更早的层，是因为它们在当前项目里主要承担：

- 行为控制
- 任务调度
- 协同通信
- 编队关系

它们本质上更像“任务实现结构”，不是单纯静态组件清单。

主要依据：

- `components.processors`
- `components.comms`
- `tasks`
- `routes`
- `resolve_component("processor", ...)`
- `resolve_component("comm", ...)`
- `resolve_task(...)`

### 4.5 Scenario Assembly

最后做脚本拼装与收尾：

- include / reusable block 排序
- `platform_type` 与 `platform` 排序
- outputs
- observers
- `end_time`
- 事件输出

这一层不再发明新语义，只负责按顺序拼装前面各层的结果。

## 5. 每层输出格式

每层建议都输出结构化 plan，而不是直接输出最终脚本文本。

推荐最小字段：

- `layer_name`
- `source_refs`
- `generated_blocks`
- `dependencies`
- `unresolved_items`
- `ready`

这样后续可以：

- 单层重试
- 单层修复
- 单层人工接管

## 6. 每层检查点

### Platform Layer

- side 是否标准化成功
- platform grounding 是否成功
- quantity 是否合法
- location / route 引用是否存在

### Sensor Layer

- sensor grounding 是否成功
- sensor 是否确实被实体引用
- 必要 link 信息是否齐全

### Weapon Layer

- weapon grounding 是否成功
- 对 `weapon_profile` 是否保留完整子结构要求
- 数量 / weapon_effects / launched platform 是否齐全

### Mission Layer

- task grounding 是否成功
- assignee / target 引用是否存在
- processor / comm 是否支持对应任务语义
- `group_comm` 与 `datalink` 是否保持拓扑区分

### Scenario Assembly

- 块顺序是否合法
- `end_time` 是否能由 `scenario.duration` 落地
- outputs 是否与场景需求一致

## 7. 回退策略

如果某层无法可靠生成：

1. 保留原始 `*_hint`
2. 在该层输出 `manual_review_required`
3. 把失败原因写入 `unresolved_items`
4. 禁止靠后续层“自动脑补”

## 8. 与 Grounding 的边界

Task-010 负责：

- 把抽象 hint 映射成 canonical target

Task-011 负责：

- 根据 canonical target 决定脚本分层生成顺序
- 根据 `processor_profile` / `comm_profile` / `weapon_profile` 展开实际结构

一句话说：

- Task-010 决定“它是什么”
- Task-011 决定“应该分几步把它写出来”

## 9. benchmark_v1 优先覆盖

v1 先优先覆盖以下高频结构：

1. 单平台 / 双平台 air combat
2. escort / intercept
3. radar + SAM 的 IADS 基本链路
4. group communication
5. acoustic detection

## 10. 最小算法

推荐最小流程：

```text
load IR
-> validate IR references
-> resolve side/platform/task/component grounding
-> build scenario scaffold
-> build platform layer plan
-> build sensor layer plan
-> build weapon layer plan
-> build mission layer plan
-> assemble scenario plan
-> emit unresolved items
```

## 11. 最小接口

Task-011 对应的最小可执行接口建议为：

```text
scripts/hierarchical_generation_planner_v1.py
```

它的职责不是直接写最终脚本，而是输出：

- 分层生成计划
- 每层依赖关系
- 每层 unresolved 项
- 是否 ready_for_generation

## 12. 完成标准

Task-011 完成后，至少应满足：

- 能从 `ir_examples_v1` 生成分层计划
- 能区分 platform / sensor / weapon / mission / assembly 五层
- 能把 processor / comm 正确纳入 Mission Layer
- 能把 `weapon_profile` / `comm_profile` / `processor_profile` 展开为生成约束
- 能为后续 Task-013 提供结构化输入
