# AFSIM Agent Workflow v1

## 目标

形成完整主系统流程：

自然语言

↓

Intent Parsing

↓

AFSIM-IR

↓

Grounding

↓

Hierarchical Generation

↓

Static Verification

↓

Self Repair

↓

Execution Repair

↓

Executable Scenario

## 当前 v1 实现范围

当前版本先把主系统链路跑通，不把所有子问题一次做满：

- `Intent Parsing`: benchmark-backed
- `IR-to-Script`: mirrored demo workspace
- `Self Repair`: 一轮
- `Execution Repair`: mission log 归因与修复路由

这让系统已经具备完整 workflow，但仍保留后续接入大模型的明确位置。

## 模块职责

### Intent Parsing

输入自然语言任务，输出结构化 IR。

当前 v1 使用 curated benchmark-to-IR 对齐。

### Grounding

把 IR 中的：

- side
- platform
- component
- task

映射为已验证的 AFSIM 实体或行为 profile。

### Hierarchical Generation

先构建 layer 计划，而不是直接自由生成整份脚本。

### Static Verification

发现：

- 单位
- 闭合
- 引用
- 坐标
- 组件嵌套
- 脚本语言错误

### Self Repair

优先做低风险修复；否则把问题路由回：

- IR
- grounding
- layer regeneration
- script logic repair

### Execution Repair

利用 `mission.exe` 日志把失败归因为：

- 环境 / 依赖
- 脚本编译 / API
- 组件初始化
- 静态问题漏检

## 当前 v1 对外承诺

对于受支持 benchmark 任务，系统应输出：

- `intent_result`
- `ir`
- `grounded_ir`
- `generation_plan`
- `script_realization`
- `static_before`
- `static_after`
- `execution_repair`
- `task_summary`

## 下一阶段接入大模型的位置

真正需要大模型的两个关键入口：

1. 开放自然语言 `Intent Parsing`
2. 非安全类 `Self Repair / Layer Regeneration`

也就是说，当前 v1 已经有完整 workflow 骨架，后续可以把 LLM 插入到明确位置，而不是重写整条系统。
