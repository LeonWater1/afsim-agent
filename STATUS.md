# STATUS.md

更新时间：2026-06-06 三方法公平对比

## Pipeline（当前主方法）

```
自然语言 → Intent Parsing → AFSIM-IR → Grounding → Grounded IR
→ Hierarchical Generation → Static Verification
→ mission.exe → Execution Repair → Executable Scenario
```

## benchmark_v1 三方法公平对比

**模型**: deepseek-v4-flash | **temperature**: 0.0 | **日期**: 2026-06-06

| Method | Total | Mission PASS | Rate | Syntax | Static |
|--------|------:|-------------:|-----:|-------:|-------:|
| **Agent v2** | 27 | **9** | **33.3%** | 37.0% | 29.6% |
| Direct | 27 | 0 | 0.0% | 0.0% | 0.0% |
| RAG | 27 | 1 | 3.7% | 0.0% | 0.0% |

### 错误分布

| 错误类型 | Agent | Direct | RAG |
|----------|------:|-------:|----:|
| Unknown Command | ~8 | 22 | 16 |
| Missing Entity | ~3 | 0 | 1 |
| Parser Fatal | ~0 | 27 | 26 |
| E002 (Block) | ~6 | 18 | 10 |
| E001 (Units) | ~2 | 8 | 13 |
| API Error | 1 | 0 | 0 |

### RAG 标注

RAG 语料 = references/ + benchmark_v1/v2 demo_sources（排除 exact oracle + same top-level demo tree）。标注为 **demo-augmented RAG**。

### Phase 6 分析

1. **Direct 为什么 0%？** 无 IR/Grounding 结构化信息，LLM 对 AFSIM 语法缺乏精确理解。27/27 Parser Fatal。

2. **RAG 相比 Direct 有微弱提升**：BV1-018 通过。但 26/27 Parser Fatal——检索到的 demo 含 include_once 等外部引用，反而误导 LLM。

3. **主方法提升主要来自**：IR（结构化实体提取）+ Grounding（映射合法 WSF 类型）+ 确定性后处理（~90 规则）。

4. **当前风险**：小样本（27 任务）、LLM 非确定性（结果在 7-12 间波动）。

5. **下一步**：扩充 Grounding 覆盖、改进分层生成 Prompt、减少 API 超时。

### 输出目录

- `afsim_agent_v2_bv1_fair/` — Agent v2
- `baseline_direct_bv1_fair/` — Direct
- `baseline_rag_bv1_fair/` — RAG
