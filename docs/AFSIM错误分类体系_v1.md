# AFSIM 错误分类体系 v1

## 1. 文档目标

本文档定义 AFSIM 场景自动生成任务中的错误分类体系，用于后续 Direct Prompt Baseline、RAG Baseline、静态检查器、self-repair 和执行反馈统计。

本分类体系面向如下生成链路：

```text
自然语言需求
-> AFSIM-IR
-> Grounding
-> 分层脚本生成
-> 静态验证
-> mission.exe 执行验证
-> 自动修复
```

错误分类的核心原则是：同一个失败样例可以有多个错误标签，但必须区分“表层语法错误”和“导致场景无法成立的根因错误”。例如，`PLATFORM.Sensor("AESA")` 找不到传感器时，根因通常是引用绑定错误，而不是脚本 API 错误。

## 2. 分类粒度

每个错误记录建议包含：

- `error_id`: 稳定编号，例如 `E001`
- `name`: 错误名称
- `level`: `static`、`execution` 或 `semantic`
- `severity`: `blocking`、`major`、`minor`
- `component`: 关联组件
- `detection`: 可检测信号
- `repair_hint`: 推荐修复策略

严重度定义：

| 严重度 | 含义 |
|---|---|
| `blocking` | 通常会导致 `mission.exe` 无法成功执行，或脚本解析失败 |
| `major` | 脚本可运行但场景行为明显偏离需求 |
| `minor` | 不一定影响执行，但会降低可解释性、可复现性或评测稳定性 |

检测阶段定义：

| 阶段 | 含义 |
|---|---|
| `static` | 不运行 `mission.exe` 即可检测 |
| `execution` | 需要结合 `mission.exe` stdout、stderr、日志或返回码检测 |
| `semantic` | 需要对照自然语言需求、IR 或 benchmark oracle 判断 |

## 3. 顶层分类

| 编号 | 类别 | 典型问题 | 优先检测阶段 |
|---|---|---|---|
| `E001` | 缺少单位 | `maximum_speed 250`、`end_time 3600` | static |
| `E002` | 缺少结束标记 | 缺少 `end_platform`、`end_sensor`、`end_route` | static |
| `E003` | 引用不存在对象 | 引用未定义 platform type、sensor、weapon、processor | static / execution |
| `E004` | 坐标格式错误 | 经纬度方向缺失、DMS 格式错误、高度表达不完整 | static |
| `E005` | 幻觉实体 | 使用不存在或未 grounding 的平台、武器、传感器、mover 类型 | static / semantic |
| `E006` | 必填项缺失 | 平台无位置、mover 无速度约束、传感器缺关键块 | static / execution |
| `E007` | 组件语法错配 | 将某组件参数写入不支持的块或类型 | static / execution |
| `E008` | 脚本 API/语言错误 | 使用 `cout`、`fmod`、三元运算符、错误事件块 | static / execution |
| `E009` | 文件与执行环境错误 | 输出目录不可写、`file_path` 错误、依赖文件缺失 | execution |
| `E010` | 任务语义偏差 | 数量、阵营、任务、空间域与需求不一致 | semantic |

## 4. 详细错误定义

### E001 缺少单位

定义：AFSIM 中需要物理量单位的数值参数未携带单位，或单位不被当前命令支持。

常见位置：

- 速度：`maximum_speed`、`minimum_speed`、`speed`
- 时间：`end_time`、`update_interval`、`frame_time`
- 长度/距离：`altitude`、`maximum_range`、`one_m2_detect_range`
- 角度：`heading`、`azimuth_beamwidth`
- 功率/频率：`power`、`frequency`、`bandwidth`

错误示例：

```text
maximum_speed 250
end_time 3600
altitude 10000
```

正确示例：

```text
maximum_speed 250 m/sec
end_time 3600 sec
altitude 10000 ft msl
```

检测信号：

- 单位型命令后出现裸数字并直接换行。
- 使用不推荐或不支持单位，例如 `microsec`。

修复策略：

- 从 IR 的 `unit` 字段补齐单位。
- 若 IR 缺失，按组件默认单位表补齐，但标记为 `repair_assumed_unit`。

### E002 缺少结束标记

定义：块结构未闭合，或结束标记与起始块不匹配。

常见块：

- `platform_type ... end_platform_type`
- `platform ... end_platform`
- `mover ... end_mover`
- `route ... end_route`
- `sensor ... end_sensor`
- `weapon ... end_weapon`
- `processor ... end_processor`
- `script_variables ... end_script_variables`
- `on_initialize ... end_on_initialize`
- `on_update ... end_on_update`

错误示例：

```text
platform_type fighter WSF_PLATFORM
   mover WSF_AIR_MOVER
      maximum_speed 250 m/sec
   end_mover
```

修复策略：

- 用栈式块匹配检查器定位未闭合块。
- 按最近未闭合块补齐对应 `end_xxx`。
- 对嵌套错位块，优先保留上层 `platform_type` / `platform` 结构，再修复子块。

### E003 引用不存在对象

定义：脚本引用了未定义或作用域不可见的对象。

常见引用：

- `platform <name> <platform_type>` 引用未定义平台类型。
- `sensor <name>` 实例覆盖未在平台类型中定义。
- `processor <processor-name>` 引用未定义 processor。
- `antenna_pattern <pattern-name>` 引用未定义天线方向图。
- `weapon_effects <name>`、`launched_platform_type <name>` 引用不存在。
- 脚本中 `PLATFORM.Sensor("...")`、`PLATFORM.Weapon("...")` 名称不匹配。

检测信号：

- 静态符号表无法解析引用。
- `mission.exe` 输出 unknown object、undefined、not found、recipient no longer exists 等信息。

修复策略：

- 构建定义表和引用表。
- 优先将引用名改为已定义对象名。
- 如果对象确实缺失，则从 grounding 库补充组件定义。
- 对脚本 API 字符串引用，必须与平台内部组件名逐字一致。

### E004 坐标格式错误

定义：平台、路线、地理点或任务区域中的坐标表达不符合 AFSIM 语法或空间域要求。

合法示例：

```text
position 30.67n 104.07e altitude 1000 m msl
position 38:44:52.3n 90:21:36.4w altitude 10000 ft msl
position 0.0 0.0 1000.0
```

常见错误：

- 经纬度缺少 `n/s/e/w` 方向。
- DMS 坐标写成 `38.44.52.3n`。
- `altitude` 缺少单位或 `msl/agl`。
- 空间场景使用普通地面坐标但未声明合适 mover / coordinate frame。

修复策略：

- 在 IR 中将位置统一表示为结构化字段：`lat`、`lon`、`altitude`、`altitude_ref`。
- 生成脚本时统一格式化坐标。
- 无法确定坐标参考系时标记为语义错误，不静默猜测。

### E005 幻觉实体

定义：生成了 AFSIM 中不存在、当前项目知识库中不存在，或未经 grounding 的实体名称/类型。

典型表现：

- `platform_type J20 WSF_STEALTH_FIGHTER`
- `sensor magic_radar WSF_QUANTUM_RADAR`
- `weapon hypersonic_missile WSF_HYPERSONIC_WEAPON`
- `mover WSF_SUPERSONIC_MOVER`

判断标准：

- AFSIM 原生命令/类型参考中不存在。
- benchmark demo、reference、grounding 表中不存在。
- 自然语言中出现的真实装备未映射到可用模板。

修复策略：

- 将用户概念映射到已有模板，例如“歼20”只能映射到已定义的 `J20_TEMPLATE` 或通用 fighter 模板。
- 若 grounding 失败，不直接造类型；返回 `grounding_missing`，交给组件库扩展。

### E006 必填项缺失

定义：组件块存在，但缺少该组件成立所需的关键字段。

常见缺失：

| 组件 | 典型必填/关键字段 |
|---|---|
| `platform` | 平台类型、位置、阵营或 route |
| `platform_type` | 基础类型、mover 或空间域相关能力 |
| `mover` | 最大速度、路径结束行为等关键运动约束 |
| `sensor` | 类型、工作模式、发射机/接收机、探测参数 |
| `weapon` | 类型、数量、射程、毁伤/发射配置 |
| `processor` | `update_interval`、事件块、脚本变量闭合 |
| `scenario` | `end_time` |

检测信号：

- 组件块只有名称，没有关键参数。
- IR 中实体存在但脚本未生成对应位置、任务或组件。
- `mission.exe` 解析期提示 required、missing、invalid 或 failed to initialize。

修复策略：

- 从同类 demo 模板补齐最小字段。
- 对 mission 级必填项，例如 `end_time`，直接补齐。
- 对语义必填项，例如任务目标，回退到 IR 层修复。

### E007 组件语法错配

定义：参数写在了错误的组件块中，或使用了当前组件类型不支持的参数。

典型例子：

- 在 `antenna_pattern` 中直接写 `azimuth_beamwidth`，未放入 `constant_pattern`。
- 给 `WSF_AIR_MOVER` 写不兼容参数。
- 将 route 命令写到不支持 route 的静态平台中。
- 将 radar 的 `transmitter` / `receiver` 写到非 radar sensor 中。

修复策略：

- 生成时按组件模板输出，不自由拼接参数。
- 静态检查器维护“组件类型 -> 允许命令”白名单。
- 对错位参数，移动到合法子块；无法移动时删除并记录。

### E008 脚本 API/语言错误

定义：`WSF_SCRIPT_PROCESSOR` 内部脚本使用了 AFSIM 脚本语言不支持的语法、函数或事件结构。

典型错误：

- 使用 C++ 输出：`cout << ... << endl`
- 在 `on_initialize` / `on_update` 内再包一层 `script ... end_script`
- 使用 `fmod()`、`%`、三元运算符、C++ 风格强制类型转换
- 调用不存在的方法，例如 `PLATFORM.Position().Geodetic()`

修复策略：

- 输出统一替换为 `print(...)`。
- 事件块直接写代码，不包 `script`。
- 定时逻辑用时间差比较替代取模。
- API 调用必须来自 `script_api_reference.md` 或 demo 实例。

### E009 文件与执行环境错误

定义：脚本本身可能基本正确，但运行环境、路径或输出配置导致 `mission.exe` 失败。

典型问题：

- 在 `C:\Program Files\...` 下直接运行，输出目录不可写。
- `output/` 不存在，事件或日志文件无法创建。
- `file_path` 未包含依赖文件目录。
- `terrain`、签名、武器、平台 include 文件路径缺失。
- `mission.exe` 路径未配置或版本不匹配。

修复策略：

- benchmark oracle 运行前镜像到可写工作目录。
- 执行前创建 `output/`。
- `run_mission.py` 以脚本所在目录为 cwd。
- 将环境错误与脚本生成错误分开统计。

### E010 任务语义偏差

定义：脚本语法和执行均通过，但与自然语言需求或 IR 不一致。

典型问题：

- 用户要求 2v2，脚本只生成 1v1。
- 用户要求红方防空，脚本将防空平台放到 blue。
- 用户要求巡逻，脚本只放置静态平台。
- 用户要求雷达探测，脚本只定义平台但没有 sensor。
- 用户要求 self-repair 后可执行，系统只做静态修补未执行验证。

检测策略：

- 将自然语言解析为 IR，再比较 IR 与脚本抽取结果。
- 对 benchmark 样例记录 `expected_ir_focus` 和 `evaluation_focus`。
- 统计时与语法错误分开：语义失败不能被“可执行”掩盖。

## 5. 与生成阶段的对应关系

| 生成阶段 | 最容易产生的错误 | 主要防护 |
|---|---|---|
| Intent Parsing | `E010` | 明确平台、数量、阵营、任务、位置 |
| AFSIM-IR | `E001`、`E004`、`E006`、`E010` | IR 字段结构化，单位和坐标独立存储 |
| Grounding | `E003`、`E005` | 禁止未 grounding 实体直接进入脚本 |
| 分层生成 | `E002`、`E007`、`E008` | 使用组件模板和块栈生成 |
| 静态验证 | `E001` - `E008` | 单位、块、符号表、组件白名单 |
| 执行验证 | `E003`、`E006`、`E009` | mission 日志解析和 cwd/output 管理 |
| Self Repair | 全部 | 修复后重新静态验证并执行验证 |

## 6. 统计口径

后续 baseline 评估建议统计：

- `syntax_pass_rate`: 未触发 `E001`、`E002`、`E004`、`E007`、`E008` 的比例。
- `static_pass_rate`: 未触发任何 static blocking 错误的比例。
- `mission_success_rate`: `mission.exe` 返回码成功的比例。
- `semantic_match_rate`: 与 benchmark 的 `expected_ir_focus` 和 `evaluation_focus` 匹配的比例。
- `repair_success_rate`: 修复后由失败转为通过的比例。
- `hallucination_rate`: 触发 `E005` 的比例。

多标签统计建议：

1. 每个失败样例可以打多个标签。
2. `primary_error` 记录最早阻断生成链路的根因。
3. `secondary_errors` 记录伴随问题。
4. `E009` 环境错误不计入模型生成错误，但应单独报告。

## 7. 最小标注格式

```json
{
  "sample_id": "BV1-003",
  "stage": "direct_prompt",
  "mission_status": "FAIL",
  "primary_error": "E003",
  "secondary_errors": ["E001", "E006"],
  "evidence": "PLATFORM.Sensor(\"AESA\") references missing sensor",
  "repair_action": "rename sensor reference to RADAR or add grounded sensor definition",
  "repair_status": "pending"
}
```

## 8. 对 Task-004 的直接用途

Direct Prompt Baseline 的输出不应只记录“成功/失败”，而应按本 taxonomy 标注失败原因。推荐结果字段：

- `sample_id`
- `generated_script`
- `static_errors`
- `mission_return_code`
- `mission_errors`
- `primary_error`
- `secondary_errors`
- `is_executable`
- `is_semantically_matched`

这样可以区分：

- 模型是否知道 AFSIM 语法。
- 模型是否能正确 grounding。
- 模型是否能生成可执行脚本。
- 模型是否满足自然语言任务。

