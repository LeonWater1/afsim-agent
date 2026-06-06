# Repair Workflow v1

## 目标

把静态检查结果转成可执行的修复闭环：

脚本

↓

错误分析

↓

修复动作排序

↓

安全修复或分层重生成

↓

重新验证

## 输入

- `generated_script`
- `static_checker_v1` 的 `findings`
- 可选 `AFSIM-IR`
- 可选 `hierarchical_generation_plan_v1`

## 修复优先级

先修会级联污染后续判断的错误：

1. `E002 missing_or_mismatched_end_tag`
2. `E001 missing_or_invalid_unit`
3. `E006 missing_required_field`
4. `E003 undefined_reference`
5. `E004 invalid_coordinate_format`
6. `E007 component_syntax_mismatch`
7. `E005 hallucinated_entity_or_type`
8. `E008 script_api_or_language_error`

## 修复模式

### 1. Safe Direct Edit

只处理低风险、确定性强的修复：

- 给常见数值命令补默认单位
- 用 IR / generation plan 补 `end_time`
- 给文件尾部补缺失的 `end_xxx`

如果修复动作会改变组件语义或嵌套关系，则不要直接补丁。

### 2. Regenerate From IR

用于：

- 坐标格式错误
- 缺失位置、航路、时长等必填字段
- 需要用 IR 回填参数的场景

这类问题应回到结构化表示，而不是纯文本猜修。

### 3. Refresh Grounding

用于：

- 幻觉出来的 `WSF_*` 类型
- 概念没有落到已验证实体

这类问题必须重新 grounding，不能在脚本层硬补。

### 4. Regenerate Layer

用于：

- 组件块放错父块
- radar 缺 `transmitter`
- `antenna_pattern` 缺 `constant_pattern`
- pseudo keyword 被当成独立命令

这类问题应回到 Task-011 的 layer 级生成，而不是做脆弱文本移动。

### 5. Regenerate Script Logic

用于：

- 不支持的脚本 API
- 不支持的脚本语言写法

这类问题只重写 processor / script 逻辑，不动其他层。

## 错误到动作映射

| Error | 默认动作 | 是否允许安全自动修复 |
| --- | --- | --- |
| `E001` | 补默认单位，补不上则回 IR | 部分允许 |
| `E002` | 补缺失 `end_xxx`；错配嵌套转人工或重生 | 部分允许 |
| `E003` | 查已定义符号并重命名，或回 grounded IR | 不建议直接自动修 |
| `E004` | 用 IR location / route 重写 `position` | 不允许 |
| `E005` | 重新 grounding | 不允许 |
| `E006` | 从 IR 补必填字段 | 部分允许 |
| `E007` | 从组件模板或 layer 计划重生 | 不允许 |
| `E008` | 重写脚本逻辑 | 不允许 |

## 输出结构

`repair_workflow_v1` 至少包含：

- `static_analysis`
- `repair_summary`
- `repair_steps`
- `safe_repair_attempt`
- `revalidation_plan`

其中 `repair_steps` 需要明确：

- `error_id`
- `line`
- `layer_scope`
- `repair_mode`
- `auto_repairable`
- `suggested_action`

## 与后续任务的关系

- Task-013 使用它把失败脚本接入最小 Agent Loop
- Task-014 在此基础上再接 `mission.exe` 执行反馈
- 未来 Type E 数据集可直接复用这里的结构作为标注格式
