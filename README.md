# AFSIM Agent

基于 LLM 的 AFSIM 2.9.0 场景生成 Agent。从自然语言需求自动生成可执行的 AFSIM 仿真脚本。

## 工作流

```
Natural Language → Intent Parsing → AFSIM-IR → Grounding → Grounded IR
→ Hierarchical Generation → Static Verification
→ mission.exe → Execution Repair → Executable Scenario
```

## 快速开始

```bash
# 设置 API Key
export DEEPSEEK_API_KEY="your-key"

# 运行完整流水线
python -m scripts.core.agent \
  --benchmark-jsonl benchmarks/benchmark/tasks.jsonl \
  --model deepseek-v4-flash \
  --max-workers 27
```

## 项目结构

```
├── scripts/core/           # 核心流水线模块
│   ├── agent.py            # 主入口，编排完整流水线
│   ├── intent_parser.py    # 自然语言 → AFSIM-IR 解析
│   ├── ir_validator.py     # IR Schema 校验
│   ├── grounding.py        # 实体映射到 AFSIM 标准类型
│   ├── generation_planner.py  # 分层生成计划
│   ├── generation_executor.py # 分层生成执行
│   ├── script_generator.py # 脚本生成（备用路径）
│   ├── static_checker.py   # 静态语法验证
│   ├── reference_rules.py  # 确定性后处理（~90 修复规则）
│   ├── context_rules.py    # WSF 类型上下文约束
│   ├── repair_planner.py   # 执行修复规划
│   ├── repair_executor.py  # LLM 引导执行修复
│   ├── mission_log_parser.py  # Mission.exe 日志解析
│   ├── run_mission.py      # Mission.exe 运行器
│   └── llm_client.py       # DeepSeek API 客户端
├── scripts/                # 评测与基线
│   ├── run_fair_baselines.py      # Direct / RAG 公平基线
│   ├── run_baselines_extended.py  # Benchmark 扩展基线
│   └── evaluate_protocol.py       # 统一评测协议
├── docs/                   # JSON Schema 与设计文档
├── references/             # AFSIM 中文参考文档
└── benchmarks/             # 任务数据集（本地，非跟踪）
```

## 流水线模块

### 1. Intent Parsing
将自然语言任务解析为结构化 AFSIM-IR（中间表示），包含实体、任务、约束。

### 2. Grounding
将用户实体映射到 AFSIM 标准类型（WSF_*），提供匹配置信度和实现约束。

### 3. Hierarchical Generation
分层生成：Scenario Scaffold → Platform → Sensor → Weapon → Mission → Assembly。

### 4. Static Verification
静态语法检查：块闭合、单位验证、引用完整性、WSF 类型白名单、幻觉检测。

### 5. Postprocessing
确定性后处理，覆盖 ~90 种已知 LLM 错误模式（幻觉指令移除、WSF 类型替换、块结构修复等）。

### 6. Execution Repair
基于 mission.exe 真实诊断的定向修复。17 种错误模式映射到 5 个生成层，最多 2 次重试。

## 评测结果

### benchmark_v1（27 任务）

| 方法 | Mission PASS | Rate |
|------|-------------:|-----:|
| Agent v2 (flash) | 12 | 44.4% |

### Benchmark 扩展（50 任务，消融实验）

| 方法 | PASS | Rate |
|------|-----:|-----:|
| Agent (IR + Grounding + 后处理) | 14 | 28.0% |
| Direct Prompt | 0 | 0.0% |
| RAG | 0 | 0.0% |

## 设计原则

- **Self Repair 已移除** — LLM 全脚本修复引入错误多于修复
- **确定性层优于 LLM 层** — 后处理规则覆盖已知模式，LLM 用于结构化理解
- **mission.exe 是最终裁判** — 以仿真器反馈为准

## 独立脚本命令

```bash
# 运行 mission.exe
python -m scripts.core.run_mission <script.txt> -es -fio

# 静态检查
python -m scripts.core.static_checker --script <file.txt>

# Grounding 验证
python -m scripts.core.grounding --validate

# 公平基线
python scripts/run_fair_baselines.py --mode direct --model deepseek-v4-flash
python scripts/run_fair_baselines.py --mode rag --model deepseek-v4-flash
```

## 要求

- Python 3.10+
- AFSIM 2.9.0（`C:\Program Files\afsim-2.9.0-win64`）
- `DEEPSEEK_API_KEY` 环境变量
