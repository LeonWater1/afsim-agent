# Execution Repair Spec v1

## 目标

把 `mission.exe` 执行反馈纳入闭环：

脚本

↓

`mission.exe`

↓

日志 / 返回码

↓

错误归因

↓

修复路由

↓

重新执行

## 输入

- `generated_script`
- `static_checker_v1` 结果
- `mission.exe` 返回码
- mission 日志文本

## 先后原则

1. 先看执行环境错误
2. 再看脚本编译错误
3. 再看组件初始化错误
4. 如果执行日志和静态错误一致，优先回到 Task-012 的静态修复链

## 执行错误分类

### E009: execution environment / dependency

典型信号：

- `mission.exe not found`
- `Cannot open file`
- `Terrain directory does not exist`
- `permission denied`
- `Add failed for NIMA DTED`

默认动作：

- 修正路径
- 保证脚本从可写、依赖完整的镜像目录运行
- 用绝对脚本路径重新执行

说明：

- `Cannot open file` 不应只假定为 `.txt`；`mission.exe -fio` 场景下，依赖文件也可能是 `.aer` 或其他扩展名

### E008: script compile / script API

典型信号：

- `Unable to compile script`
- `Method 'X' does not exist`
- `Void script cannot return a value`
- `Unknown identifier`
- `Invalid method call`

默认动作：

- 回到 mission layer / script logic repair
- 重写 processor 脚本
- 重新做静态验证后再执行

### E005 / E006 / E007: component / configuration / structure

典型信号：

- `Unknown command`
- `Could not find mover`
- `Bad value for`
- `No ... defined`
- `Platform component failed phase one initialization`

默认动作：

- 如果静态检查已经报错，优先回 Task-012
- 如果静态检查未覆盖，则依据日志信号回到：
  - grounding
  - layer regeneration
  - IR 参数修复

## 输出结构

`execution_repair_spec_v1` 至少包含：

- `static_analysis`
- `execution_analysis`
- `repair_recommendation`
- `rerun_plan`

其中 `execution_analysis` 需要明确：

- `mission_pass`
- `primary_error`
- `classifier`
- `route`
- `inferred_stage`
- `evidence_lines`

## 与 Task-012 的分工

- Task-012 负责静态闭环
- Task-014 负责执行闭环

如果脚本连静态都不过，不要直接做 execution repair；先回 Task-012。

## 与后续系统的关系

- Task-015 会把 static repair 和 execution repair 串成完整 Agent Workflow
- 未来 Type E / execution datasets 可复用这里的输出结构

## 轻量验证

分类器应支持不实际运行 `mission.exe` 的内建验证模式，用少量已知日志模式检查：

- `E009` 环境 / 文件依赖错误
- `E008` 脚本编译 / API 错误
- `E005` grounding 失败
- 静态错误回退分流
