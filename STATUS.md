# STATUS.md

## 当前阶段

Pipeline 迭代优化阶段。

当前重点已经从“把流程跑通”转到“把 mission.exe 已经证明过的真实约束前移到规则层”，并持续压缩以下三类差距：

1. `static_checker` 与 `mission.exe` 的差距
2. grounding / generation 的实现约束缺口
3. repair 过程中产生的 drift 和结构性二次损坏

更新时间：2026-06-04

---

## v5 实验数据

v5 统计口径以 `afsim_agent_v2/BV1-*/task_summary.json` 为准。
旧的 `afsim_agent_v2/summary.json` 存在混入旧轮次工件的风险，不能直接作为唯一真源。

### Canonical v5 counts

| 指标 | 数值 |
|------|:--:|
| total | 27 |
| ir_valid | 27 |
| mission_pass | 13 |
| substantive_pass | 11 |
| mission_pass_but_non_substantive | 2 |
| empty_shell_pass | 0 |

### v5 substantive pass tasks

- `BV1-001`
- `BV1-004`
- `BV1-005`
- `BV1-006`
- `BV1-007`
- `BV1-008`
- `BV1-015`
- `BV1-018`
- `BV1-023`
- `BV1-025`
- `BV1-026`

### v5 mission pass but non-substantive

- `BV1-013`
- `BV1-019`

### v5 mission fail

- `BV1-002`
- `BV1-003`
- `BV1-009`
- `BV1-010`
- `BV1-011`
- `BV1-012`
- `BV1-014`
- `BV1-016`
- `BV1-017`
- `BV1-020`
- `BV1-021`
- `BV1-022`
- `BV1-024`
- `BV1-027`

### v4 -> v5 变化

- `BV1-015` 新增 substantive pass
- `BV1-026` 新增 substantive pass
- `BV1-002` 退化，暴露出 `WSF_STATIONARY_MOVER` 的 runtime/document mismatch

---

## 当前关键风险

1. **评测工件口径未完全统一**
   - `summary.json` 与各任务目录下的 `task_summary.json` 存在混写痕迹
   - 后续一律以 `task_summary.json` 为聚合输入
   - mission 日志优先读取 `mission_final.log`

2. **runtime/document mismatch 仍存在**
   - `WSF_STATIONARY_MOVER` 在历史白名单中可见，但当前 mission.exe 报 `Could not find mover`
   - 说明“文档可见”不等于“当前环境可安全生成”

3. **Static Pass 仍不等于 mission pass**
   - 目前仍有一批 `final_static_pass = true` 但 `mission_status = FAIL`
   - 代表缺口主要集中在：
     - 被动/ESM 传感器语义约束
     - ejector/chaff 宿主约束
     - Brawler family companion rules
     - script API 第二批 lint

4. **Grounding 覆盖仍不足**
   - `artillery_shell`、`designator` 等实体仍可能 unresolved
   - 复杂场景族仍受影响

5. **repair drift 仍有失败面**
   - `BV1-014 / 017 / 020 / 022 / 024 / 027`
   - 主要表现为：
     - block 结构修坏
     - full-script repair 过大
     - 新错误覆盖旧根因

---

## 当前确定性规则层

| 规则层 | 当前状态 | 备注 |
|------|:--:|------|
| 官方命令白名单 | 已接入 | 来源：官方 command index + demo 补充 |
| WSF 类型宿主约束 | 已接入 | 当前仍需继续扩类型覆盖 |
| block 交叉关闭纠正 | 已接入 | 仍需继续压 `E002` 失败簇 |
| mover 命令位置检查 | 已接入 | 已能抓一批 wrong-level 命令 |
| E003 引用完整性 | 已接入 | comm / behavior / antenna pattern |
| E008 script API linting 第一批 | 已接入 | `Vec3.Normalize(...)` / `Vec3.Scale(...)` / `.LLA()` |
| E009 外部资源检查 | 已接入 | `aero_file` token 遍历 bug 已修复 |
| command context JSON 规则 | 已接入 | 来自 `afsim_context_rules_v1.json` |
| repair drift guard | 已接入 | 已进入 pipeline，但还要继续收紧 |

---

## 当前 LLM 依赖层

| 环节 | 当前状态 | 风险 |
|------|:--:|------|
| Intent Parsing | 有 few-shot | 陌生命题仍可能降质 |
| Script Generation | 有 `source_hint` | 新任务族易出语法 / 上下文错误 |
| Grounding | `entity_mapping_v1.json` | 新实体 unresolved |
| Execution Repair | 已接入 | 对结构坏脚本和复杂组件族仍不稳 |

---

## v5 P0 修复（2026-06-04 已实施）

| # | 修复 | 状态 |
|:--:|------|:--:|
| 1 | 移除 `WSF_STATIONARY_MOVER`（BV1-002） | ✅ `VALID_WSFS` 已移除 |
| 2 | ESM/被动传感器 `frequency_band` 必填检查（BV1-010） | ✅ `check_component_syntax` |
| 3 | `ejector` 仅限 `weapon WSF_CHAFF_WEAPON` 宿主规则（BV1-003） | ✅ 双路径（block-start + content-command） |
| 4 | Brawler companion rules（BV1-012） | ✅ `has_brawler_mover` + `has_threat_processor` |
| 5 | 统一 v5 评测口径 | ✅ `summary.json` + `results.jsonl` 已从 `task_summary.json` 重建 |

Canonical v5 baseline: `mission_pass=13`, `substantive_pass=11`.

---

## 后续优先级

### P1：扩确定性规则层

- 扩 `wsf_type_host_rules`，目标 15+ 类型
- 扩 `command_context_rules`，优先：
  - `target`
  - `max_speed` / `maximum_speed`
  - `task`
  - `weapon_bay`
  - `effect`
  - `technique`
  - `on_message`
  - `guidance_computer`
  - `frequency`
- 扩 `parameter_context_rules`
  - speed
  - range
  - bandwidth
  - quantity
  - interval

### P1.5：继续压 repair drift

- repair 若引入新的 `E002/E007` 结构族错误，则拒绝接受
- block-stack-aware local repair 优先于 full-script repair
- 继续保护：
  - `primary_root_cause`
  - `final_blocker`
- 重点回归：
  - `BV1-014`
  - `BV1-017`
  - `BV1-020`
  - `BV1-022`
  - `BV1-024`
  - `BV1-027`

### P2：Script API linting 第二批

- 在第一批基础上继续前移 mission-proven API 误用：
  - `HeadingTo`
  - `Offset`
  - 其他未验证 `WsfGeoPoint / Vec3` 方法形态
- 尽量基于 `script_api_reference.md` + 官方 demo 做 shape/whitelist

### P2：补 LLM 依赖层覆盖

- 扩 `ir_examples_v1.jsonl`
  - fires
  - brawler
  - cislunar
  - chaff
- 扩 `entity_mapping_v1.json`
  - 优先 unresolved 实体
  - 如 `artillery_shell`、`designator`

---

## 协作备注

- `TASK.md` 只维护任务定义、依赖和状态
- `STATUS.md` 只维护当前阶段、实验结果、风险和下一步
- 后续大规模修改完成后，必须同步更新本文件
- 过时的过程性内容不要继续堆积在这里，历史通过 git 追溯
- `minimal_agent_v0` 旧工件文件已清理；Task-013 状态仍保持 DONE
