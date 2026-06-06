# Static Verification Rules v1

## 1. 目标

本文档定义 AFSIM 脚本生成链路中的静态检查规则。

静态检查器不替代 `mission.exe`，而是用于在执行前尽早发现高概率阻断错误，并为 Direct Prompt、RAG、IR-to-Script、Self Repair 和 Execution Repair 提供统一错误口径。

对应实现：

- `scripts/core/static_checker.py`
- `docs/machine/error_taxonomy.json`

实现关系：

- `scripts/core/static_checker.py` 是 Static Verification v1 的唯一规则实现来源。
- `scripts/run_direct_baseline.py` 和 `scripts/run_rag_baseline.py` 统一调用 `static_checker_v1.analyze_script_text()`。
- `syntax_correct` 和 `static_pass` 的判定集合由 `docs/machine/error_taxonomy.json` 驱动，不再在 Python 中单独硬编码一套分类语义。

## 2. 输入与输出

输入：

```text
AFSIM .txt 脚本
```

输出：

```json
{
  "script": "path/to/script.txt",
  "syntax_correct": true,
  "static_pass": true,
  "primary_error": "",
  "static_error_ids": [],
  "findings": []
}
```

字段含义：

- `syntax_correct`：未触发 taxonomy 中 `affects_syntax = true` 的错误。
- `static_pass`：未触发 taxonomy 中 `blocks_static_pass = true` 的错误。
- `primary_error`：按发现顺序记录的第一个静态错误类型。

## 3. 错误覆盖范围

Static Verification v1 覆盖以下错误：

- `E001`：缺少或非法单位
- `E002`：缺少或错配 `end_xxx`
- `E003`：引用不存在对象
- `E004`：坐标格式错误
- `E005`：幻觉实体或未验证 `WSF_*` 类型
- `E006`：必填字段缺失
- `E007`：组件语法错配
- `E008`：脚本 API 或语言错误

`E009` 属于执行环境错误，由 `mission.exe` 阶段发现。

`E010` 属于任务语义偏差，需要结合 IR 或 benchmark 目标判断。

## 4. E007 当前实现范围

`E007` 在 v1 中是规则化启发式检查，不是完整语法验证器。当前已实现：

- `WSF_RADAR_SENSOR` 缺少 `transmitter` 子块。
- `antenna_pattern` 定义块缺少 `constant_pattern` 子块。
- `route` 块未嵌套在 `platform` 下。
- `constant_pattern` 块未嵌套在 `antenna_pattern` 下。
- `command_chain` 未嵌套在 `platform` 下。
- `task` 未嵌套在 `processor` 下。
- `weapon_type`、`sensor_type`、`processor_type`、`mover_type` 这类伪关键字被当作独立命令使用。
- `antenna_pattern` 引用未嵌套在 `transmitter` 或 `receiver` 下。
- `WSF_AIR_MOVER` 中出现 `default_climb_rate` 或 `default_descent_rate`。

未覆盖的更细粒度组件约束，后续由更完整的 grounding / layer-specific generation 继续补强。

## 5. 引用检查规则

`E003` 当前明确检查：

- `platform <instance> <platform_type>` 中引用了未定义的平台类型。
- `transmitter` / `receiver` 中的 `antenna_pattern <name>` 引用了未定义天线方向图。

说明：

- 顶层 `antenna_pattern <name> ... end_antenna_pattern` 会被视为定义。
- `transmitter` / `receiver` 中的 `antenna_pattern <name>` 会被视为引用。
- 这两种形式在符号表构建中严格区分，避免“所有 `antenna_pattern` 都被当作定义”的误判。

## 6. 使用方式

检查单个脚本：

```powershell
python scripts/core/static_checker.py benchmarks/benchmark/demo_sources/acoustic/simple_demo.txt
```

检查目录：

```powershell
python scripts/core/static_checker.py baseline_rag_v1/generated_scripts --recursive
```

只输出汇总：

```powershell
python scripts/core/static_checker.py baseline_rag_v1/generated_scripts --recursive --summary-only
```

发现静态错误时返回非零退出码：

```powershell
python scripts/core/static_checker.py generated.txt --fail-on-findings
```

## 7. 与后续任务关系

- Task-009 使用本口径建立评测体系。
- Task-011 在 IR-to-Script 后调用本检查器。
- Task-012 根据 `findings` 选择修复策略。
- Task-013 Minimal Agent Loop 为每个任务输出静态检查结果。
- Task-014 Execution Repair 将本检查结果与 `mission.exe` 日志结合。
