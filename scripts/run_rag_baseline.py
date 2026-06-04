#!/usr/bin/env python3
"""
Run a RAG-prompting baseline for AFSIM benchmark tasks.

Retrieves relevant documentation (SKILL.md, references/) and demo snippets
from the benchmark demo_sources, injects them into the prompt, then evaluates
using the same static checks, mission execution, and metrics as the direct baseline.
"""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

from run_direct_baseline import (
    DEEPSEEK_API_URL,
    infer_primary_error,
    load_tasks,
    mission_error_to_taxonomy,
    semantic_match,
    strip_code_fences,
)
from run_mission import load_config
from static_checker_v1 import analyze_script_text

# ── Reference files included in the corpus ──────────────────────────────────

REFERENCE_FILES = [
    "references/script_syntax_critical.md",
    "references/common_mistakes.md",
    "references/file_structure.md",
    "references/commands_reference.md",
    "references/mover_reference.md",
    "references/sensor_types_reference.md",
    "references/script_api_reference.md",
    "references/examples.md",
    "SKILL.md",
]

# Directories / path segments to skip when scanning demo sources
SKIP_DEMO_SEGMENTS = {"output", "doc", "docs", "__pycache__", "prdata", "rules"}

# ── Critical syntax primer ──────────────────────────────────────────────────
# Always injected into every prompt so the model has correct AFSIM patterns.

CRITICAL_SYNTAX = """\
================================================================================
AFSIM 2.9.0 CRITICAL SYNTAX RULES — follow these exactly:
================================================================================

1. FILE EXTENSION: .txt (NOT .wsf)

2. UNITS REQUIRED for ALL numeric values:
   speed 200 m/sec    altitude 10000 ft msl    update_interval 1.0 sec
   maximum_range 50 nm    end_time 600 sec    heading 90 deg

3. EVERY block MUST have a matching end_xxx tag:
   platform_type ... end_platform_type
   platform ... end_platform
   mover WSF_AIR_MOVER ... end_mover
   route ... end_route
   sensor ... end_sensor
   weapon ... end_weapon
   processor ... end_processor

4. COORDINATE FORMATS (either is valid):
   Decimal:   position 35.5n 120.3w altitude 10000 ft msl
   Colon:     position 38:44:52.3n 90:21:36.4w altitude 10000 ft msl

5. Use print() NOT cout.  on_initialize / on_update code directly (no script/end_script wrapper).

6. antenna_pattern MUST wrap params in constant_pattern sub-block:
   antenna_pattern MY_PAT
      constant_pattern
         peak_gain 35 db
         azimuth_beamwidth 60 deg
         elevation_beamwidth 60 deg
      end_constant_pattern
   end_antenna_pattern

7. pulse_width uses scientific notation: pulse_width 1.0e-6 sec  (NOT "microsec")

8. WSF_AIR_MOVER supported params: maximum_speed, minimum_speed, default_radial_acceleration
   Do NOT use default_climb_rate or default_descent_rate on WSF_AIR_MOVER.

9. NO ternary (? :), NO fmod(), NO int() cast, NO modulo (%).

10. KNOWN WSF TYPES (do NOT invent types outside this list):
    WSF_PLATFORM  WSF_AIR_MOVER  WSF_KINEMATIC_MOVER  WSF_RADAR_SENSOR
    WSF_SCRIPT_PROCESSOR  WSF_AIR_TO_AIR_MISSILE
    Also valid in demos: WSF_SURFACE_MOVER  WSF_SUBSURFACE_MOVER  WSF_GROUND_MOVER
    WSF_ORBITAL_MOVER  WSF_BALLISTIC_MOVER  WSF_STATIONARY_MOVER  WSF_HELO_MOVER
    WSF_GUIDED_MOVER  WSF_SCRIPTED_MOVER  WSF_ESM_SENSOR  WSF_EOIR_SENSOR
    WSF_EXPLICIT_WEAPON  WSF_BALLISTIC_WEAPON

================================================================================
CORRECT MINIMAL EXAMPLE:
================================================================================

platform_type my_aircraft WSF_PLATFORM
   icon aircraft
   mover WSF_AIR_MOVER
      maximum_speed 500 m/sec
      minimum_speed 100 m/sec
      default_radial_acceleration 5.0 g
   end_mover
end_platform_type

platform plane_1 my_aircraft
   side blue
   position 35.5n 120.3w altitude 10000 ft msl
   route
      position 35.5n 120.3w altitude 10000 ft msl speed 200 m/sec
      position 36.0n 121.0w altitude 10000 ft msl speed 200 m/sec
   end_route
end_platform

end_time 600 sec
================================================================================
"""

# ── Tokenization ────────────────────────────────────────────────────────────


def tokenize(text: str) -> set:
    text = text.lower()
    tokens = set(re.findall(r"[a-z0-9_+-]{2,}", text))
    cjk = re.findall(r"[一-鿿]", text)
    tokens.update(cjk)
    tokens.update(a + b for a, b in zip(cjk, cjk[1:]))
    return tokens


# ── Corpus building ─────────────────────────────────────────────────────────


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _chunk_md_by_sections(text: str, source: str, max_section_chars: int = 4000):
    """Split markdown by ## headings; split oversized sections further by ### ."""
    chunks = []
    sections = re.split(r"\n(?=## )", text)
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if len(sec) <= max_section_chars:
            chunks.append({"source": source, "kind": "reference", "text": sec})
        else:
            subs = re.split(r"\n(?=### )", sec)
            for sub in subs:
                sub = sub.strip()
                if not sub:
                    continue
                if len(sub) <= max_section_chars:
                    chunks.append({"source": source, "kind": "reference", "text": sub})
                else:
                    # last resort: fixed-size split
                    for i in range(0, len(sub), max_section_chars):
                        piece = sub[i : i + max_section_chars].strip()
                        if piece:
                            chunks.append({"source": source, "kind": "reference", "text": piece})
    return chunks


def _chunk_demo_file(text: str, source: str, max_chars: int = 8000):
    """Keep demo files intact when small; split large files at top-level block starts."""
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= max_chars:
        return [{"source": source, "kind": "demo", "text": text}]

    # For large files, split at top-level block boundaries
    # Match lines that start a top-level AFSIM block (not indented)
    top_level_re = re.compile(
        r"^(platform_type |platform |sensor |weapon |route\n|processor |"
        r"antenna_pattern |acoustic_signature |comm |script_interface |"
        r"event_pipe |event_output |dis_interface |script_variables |"
        r"execute |mover |transmitter |receiver |constant_pattern )",
        re.MULTILINE,
    )
    splits = list(top_level_re.finditer(text))
    if not splits:
        return [{"source": source, "kind": "demo", "text": text}]

    chunks = []
    for i, m in enumerate(splits):
        start = m.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        block = text[start:end].strip()
        if len(block) > max_chars * 2:
            # Oversized block — split at blank lines
            for sub in re.split(r"\n\s*\n", block):
                sub = sub.strip()
                if not sub:
                    continue
                if len(sub) > 50:
                    chunks.append({"source": source, "kind": "demo", "text": sub})
        elif len(block) > 50:
            chunks.append({"source": source, "kind": "demo", "text": block})

    # Include preamble (anything before first top-level block)
    if splits and splits[0].start() > 0:
        pre = text[: splits[0].start()].strip()
        if pre and len(pre) > 100:
            chunks.insert(0, {"source": source, "kind": "demo", "text": pre})

    return chunks if chunks else [{"source": source, "kind": "demo", "text": text}]


def _detect_demo_components(text: str) -> set:
    """Return the set of component types present in a demo chunk."""
    components = set()
    lower = text.lower()
    if "platform_type " in lower or "platform " in lower:
        components.add("Platform")
    if "mover " in lower:
        components.add("Mover")
    if "sensor " in lower:
        components.add("Sensor")
    if "weapon " in lower:
        components.add("Weapon")
    if "processor " in lower:
        components.add("Processor")
    if "route" in lower:
        components.add("Route")
    if "comm " in lower:
        components.add("Comm")
    if "antenna_pattern " in lower:
        components.add("AntennaPattern")
    if "acoustic" in lower:
        components.add("Acoustic")
    if "transmitter " in lower:
        components.add("Transmitter")
    if "behavior_tree" in lower or "btree" in lower:
        components.add("BehaviorTree")
    return components


def build_corpus(root: Path, benchmark_dir: Path) -> list:
    """Build retrieval corpus from SKILL.md, references/*.md, and demo_sources/**/*.txt ."""
    corpus = []

    # SKILL.md
    skill_path = root / "SKILL.md"
    if skill_path.exists():
        for chunk in _chunk_md_by_sections(_read_text(skill_path), "SKILL.md", max_section_chars=2500):
            chunk["kind"] = "skill"
            corpus.append(chunk)

    # references/*.md
    for rel in REFERENCE_FILES:
        if rel == "SKILL.md":
            continue
        path = root / rel
        if not path.exists():
            continue
        for chunk in _chunk_md_by_sections(_read_text(path), rel, max_section_chars=2500):
            corpus.append(chunk)

    # demo_sources/**/*.txt
    demo_root = benchmark_dir / "demo_sources"
    for txt_path in sorted(demo_root.glob("**/*.txt")):
        if not txt_path.is_file():
            continue
        parts = set(p.lower() for p in txt_path.relative_to(demo_root).parts)
        if parts & SKIP_DEMO_SEGMENTS:
            continue
        if txt_path.stat().st_size > 160_000:
            continue
        rel = txt_path.relative_to(root).as_posix()
        for chunk in _chunk_demo_file(_read_text(txt_path), rel):
            corpus.append(chunk)

    # Pre-compute tokens and components for every chunk
    for item in corpus:
        item["tokens"] = tokenize(item["source"] + "\n" + item["text"])
        item["components"] = _detect_demo_components(item["text"])

    return corpus


# ── Retrieval ───────────────────────────────────────────────────────────────


def _resolve_source_tree(task: dict, root: Path):
    """Return the directory tree root for the task's source_hint demo, or None."""
    hint = task.get("source_hint", "")
    if not hint:
        return None
    path = Path(hint)
    if not path.is_absolute():
        path = root / hint
    path = path.resolve()
    if path.exists():
        return path.parent.resolve()
    return None


def _make_query(task: dict) -> str:
    fields = [
        task.get("id", ""),
        task.get("input", ""),
        " ".join(task.get("covered_components", [])),
        " ".join(task.get("evaluation_focus", [])),
    ]
    return " ".join(fields)


def retrieve(task: dict, corpus: list, root: Path, max_chars: int = 12000) -> list:
    """Retrieve relevant chunks for a task.

    Strategy:
      1. Source-tree priority: chunks from the same demo directory tree as source_hint
         get a large bonus. Excludes the oracle file itself.
      2. Component bonus: chunks whose detected components overlap with task
         covered_components get a bonus.
      3. Reference diversity: always reserve ~25% of the budget for top-scoring
         reference/skill documentation chunks, so the model sees syntax rules
         and not just demo snippets.
      4. Global keyword scoring fills remaining budget.
    """
    query_tokens = tokenize(_make_query(task))
    task_components = set(task.get("covered_components", []))
    oracle_path = _resolve_source_tree(task, root)
    oracle_file = None

    # Resolve exact oracle file path for exclusion
    hint = task.get("source_hint", "")
    if hint:
        p = Path(hint)
        if not p.is_absolute():
            p = root / hint
        oracle_file = p.resolve()

    source_tree = None
    if oracle_path is not None:
        source_tree = oracle_path.resolve()

    source_tree_parent = source_tree.parent.resolve() if source_tree else None

    scored_all = []
    scored_refs = []   # reference + skill chunks only
    scored_demos = []  # demo chunks only

    for item in corpus:
        # Exclude oracle file
        if oracle_file is not None:
            src_path = item["source"].split("#chunk-")[0] if "#chunk-" in item["source"] else item["source"]
            candidate = (root / src_path).resolve()
            if candidate == oracle_file:
                continue

        # Keyword overlap score
        overlap = len(query_tokens & item["tokens"])

        # Source-tree bonus: chunks from the same demo directory tree
        source_tree_bonus = 0
        src_path = item["source"].split("#chunk-")[0] if "#chunk-" in item["source"] else item["source"]
        candidate = (root / src_path).resolve()
        try:
            candidate_parent = candidate.parent.resolve()
        except (OSError, ValueError):
            candidate_parent = None

        if item["kind"] == "demo" and source_tree is not None and candidate_parent is not None:
            if str(source_tree) in str(candidate):
                source_tree_bonus = 150   # file within the source demo project
            elif (source_tree_parent is not None and candidate_parent.parent is not None):
                try:
                    if candidate_parent.parent.resolve() == source_tree_parent:
                        source_tree_bonus = 80  # sibling demo dir
                except (OSError, ValueError):
                    pass

        # Component match bonus
        comp_bonus = 0
        chunk_comps = item.get("components", set())
        if chunk_comps and task_components:
            comp_bonus = len(chunk_comps & task_components) * 5

        # Kind bonus: docs get a baseline boost to stay competitive
        kind_bonus = 0
        if item["kind"] == "demo":
            kind_bonus = 5
        elif item["kind"] in ("reference", "skill"):
            kind_bonus = 10  # slight boost for documentation

        # Path keyword bonus
        path_bonus = 0
        src_lower = src_path.lower().replace("\\", "/")
        for token in query_tokens:
            if len(token) >= 3 and token in src_lower:
                path_bonus += 2

        total_score = overlap + source_tree_bonus + comp_bonus + kind_bonus + path_bonus
        if total_score > 0 or item["kind"] in ("reference", "skill"):
            entry = (total_score, item)
            scored_all.append(entry)
            if item["kind"] in ("reference", "skill"):
                scored_refs.append(entry)
            else:
                scored_demos.append(entry)

    scored_all.sort(key=lambda p: p[0], reverse=True)
    scored_refs.sort(key=lambda p: p[0], reverse=True)
    scored_demos.sort(key=lambda p: p[0], reverse=True)

    ref_budget = max_chars // 5   # reserve ~20% for reference docs
    demo_budget = max_chars - ref_budget

    selected = []
    total_chars = 0

    # Pick top reference/skill chunks first (up to ref_budget)
    ref_chars = 0
    for _, item in scored_refs:
        text_len = len(item["text"])
        if ref_chars + text_len > ref_budget:
            if ref_chars < ref_budget * 0.5 and ref_budget - ref_chars > 400:
                truncated = dict(item)
                truncated["text"] = item["text"][: ref_budget - ref_chars] + "\n[...truncated]"
                selected.append(truncated)
                ref_chars = ref_budget
            break
        selected.append(item)
        ref_chars += text_len
    total_chars = ref_chars

    # Fill remaining budget with demo chunks
    for _, item in scored_demos:
        text_len = len(item["text"])
        if total_chars + text_len > max_chars:
            if total_chars < max_chars * 0.7 and max_chars - total_chars > 400:
                truncated = dict(item)
                truncated["text"] = item["text"][: max_chars - total_chars] + "\n[...truncated]"
                selected.append(truncated)
            break
        # Deduplicate: skip if same source file already selected
        if any(s.get("source") == item["source"] for s in selected):
            continue
        selected.append(item)
        total_chars += text_len

    return selected


# ── Prompt building ─────────────────────────────────────────────────────────


def format_context(chunks: list) -> str:
    """Format retrieved chunks into a labelled context block."""
    parts = []
    for idx, item in enumerate(chunks, start=1):
        label = f"[{idx}] {item['kind'].upper()} — {item['source']}"
        parts.append(f"{label}\n{item['text'].strip()}")
    return "\n\n---\n\n".join(parts)


def build_rag_messages(task: dict, retrieved_context: str):
    """Build system + user messages with critical rules and retrieved context."""
    system_prompt = f"""You generate AFSIM 2.9.0 mission scripts.

This is a RAG-prompting baseline. You receive reference documentation and demo
snippets as context. Use them to produce a syntactically correct AFSIM script.
Do not assume access to IR, grounding tables, or repair feedback.

{CRITICAL_SYNTAX}

Return exactly one complete AFSIM script as plain text.
Do not include markdown fences, explanation, JSON, or commentary."""

    user_prompt = f"""Task ID: {task['id']}
Natural-language request:
{task['input']}

Expected components: {", ".join(task.get("covered_components", []))}

────────────────────────────────────────────────────────────────────────────────
RETRIEVED REFERENCE & DEMO CONTEXT (study these patterns before generating):
────────────────────────────────────────────────────────────────────────────────
{retrieved_context}
────────────────────────────────────────────────────────────────────────────────

Generate the complete AFSIM script now. Output ONLY the script, no other text."""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ── API call ────────────────────────────────────────────────────────────────


def call_deepseek_rag(task, context, api_key, model, api_timeout, max_retries):
    payload = {
        "model": model,
        "messages": build_rag_messages(task, context),
        "temperature": 0.0,
        "max_tokens": 8192,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            request = urllib.request.Request(DEEPSEEK_API_URL, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=api_timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            return strip_code_fences(data["choices"][0]["message"]["content"])
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DeepSeek RAG generation failed for {task['id']}: {last_error}")


# ── Prompt template doc ─────────────────────────────────────────────────────


def write_prompt_template(path: Path, model: str, exclude_oracle: bool):
    content = f"""# RAG Prompt Template v1

该 baseline 模拟"自然语言 → 知识检索 → AFSIM 脚本"的生成流程。

## 当前运行配置

- generator: `deepseek`
- model: `{model}`
- exclude_oracle: `{exclude_oracle}`
- retrieval_sources: `SKILL.md`, `references/`, `benchmarks/benchmark_v1/demo_sources/`

## 检索策略

1. **始终注入** AFSIM 关键语法规则（来自 SKILL.md / script_syntax_critical.md）
2. **源目录优先**：根据 source_hint 定位 demo 目录，该目录树内的 chunk 获得高分加成
3. **组件匹配**：根据任务 covered_components 匹配 chunk 类型
4. **全局关键词**：填充剩余 context 预算

默认排除当前任务的 oracle 脚本，避免把 benchmark 答案直接注入 prompt。
"""
    path.write_text(content, encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Run RAG baseline on benchmark tasks")
    parser.add_argument("--benchmark-dir", default="benchmarks/benchmark_v1")
    parser.add_argument("--output-dir", default="baseline_rag_v1")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--api-timeout", type=int, default=180)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--allow-oracle", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    benchmark_dir = (root / args.benchmark_dir).resolve()
    output_dir = (root / args.output_dir).resolve()
    scripts_dir = output_dir / "generated_scripts"
    logs_dir = output_dir / "mission_logs"

    output_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_prompt_template(output_dir / "prompt_template.md", args.model, not args.allow_oracle)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required")

    tasks = load_tasks(benchmark_dir / "tasks.jsonl")
    if args.limit:
        tasks = tasks[: args.limit]

    print(f"Building corpus...")
    corpus = build_corpus(root, benchmark_dir)
    print(f"Corpus: {len(corpus)} chunks  |  Tasks: {len(tasks)}")

    config = load_config()
    mission_exe = Path(config["mission_exe"])

    summary_rows = []
    retrieved_rows = []
    error_counter = Counter()
    mission_counter = Counter()

    for task in tasks:
        chunks = retrieve(task, corpus, root, max_chars=args.max_context_chars)
        context = format_context(chunks)

        retrieved_rows.append({
            "id": task["id"],
            "sources": [
                {"kind": item["kind"], "source": item["source"]} for item in chunks
            ],
        })

        script_text = call_deepseek_rag(
            task, context, api_key, args.model, args.api_timeout, args.max_retries
        )
        script_path = scripts_dir / f"{task['id']}.txt"
        (script_path.parent / "output").mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text, encoding="utf-8")

        static_result = analyze_script_text(script_text, script_label=str(script_path))
        findings = static_result["findings"]
        static_error_ids = static_result["static_error_ids"]

        cmd = [str(mission_exe), "-es", "-sm", str(script_path)]
        mission_status = "NOT_RUN"
        return_code = None
        log_text = ""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(script_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            return_code = result.returncode
            log_text = result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else "")
            mission_status = "PASS" if result.returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired as exc:
            log_text = (exc.stdout or "") + ("\nSTDERR:\n" + exc.stderr if exc.stderr else "")
            mission_status = "TIMEOUT"

        log_path = logs_dir / f"{task['id']}.log"
        log_path.write_text(log_text, encoding="utf-8", errors="replace")
        mission_taxonomy = mission_error_to_taxonomy(log_text)
        semantic_ok = semantic_match(task, script_text, mission_status)

        primary_error = infer_primary_error(findings, mission_status)
        secondary_errors = sorted({
            item["error_id"] for item in findings if item["error_id"] != primary_error
        })
        if mission_taxonomy and primary_error == "E009" and not findings:
            primary_error = mission_taxonomy
        elif mission_taxonomy and mission_taxonomy not in {primary_error, *secondary_errors}:
            if primary_error:
                secondary_errors.append(mission_taxonomy)
            else:
                primary_error = mission_taxonomy

        for error_id in [primary_error] + secondary_errors:
            if error_id:
                error_counter[error_id] += 1
        mission_counter[mission_status] += 1

        summary_rows.append({
            "id": task["id"],
            "input": task["input"],
            "generated_script": str(script_path.relative_to(root)).replace("\\", "/"),
            "retrieved_sources": [item["source"] for item in chunks],
            "static_errors": findings,
            "static_error_ids": static_error_ids,
            "syntax_correct": static_result["syntax_correct"],
            "static_pass": static_result["static_pass"],
            "mission_status": mission_status,
            "return_code": return_code,
            "mission_log": str(log_path.relative_to(root)).replace("\\", "/"),
            "primary_error": primary_error,
            "secondary_errors": secondary_errors,
            "semantic_match": semantic_ok,
        })
        print(
            f"{task['id']}: "
            f"retrieved={len(chunks)} "
            f"static={len(static_error_ids)} "
            f"mission={mission_status} "
            f"semantic={semantic_ok}"
        )

    total = len(summary_rows)
    syntax_correct = sum(1 for row in summary_rows if row["syntax_correct"])
    static_pass = sum(1 for row in summary_rows if row["static_pass"])
    mission_pass = sum(1 for row in summary_rows if row["mission_status"] == "PASS")
    semantic_pass = sum(1 for row in summary_rows if row["semantic_match"])
    failed = total - mission_pass

    summary = {
        "name": "baseline_rag_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generator": "deepseek",
        "model": args.model,
        "benchmark_dir": str(benchmark_dir.relative_to(root)).replace("\\", "/"),
        "retrieval": {
            "exclude_oracle": not args.allow_oracle,
            "max_context_chars": args.max_context_chars,
            "corpus_chunks": len(corpus),
            "strategy": "source_tree_priority + component_aware + keyword",
        },
        "total": total,
        "syntax_correct_rate": round(syntax_correct / total, 4) if total else 0.0,
        "static_pass_rate": round(static_pass / total, 4) if total else 0.0,
        "mission_success_rate": round(mission_pass / total, 4) if total else 0.0,
        "error_rate": round(failed / total, 4) if total else 0.0,
        "semantic_match_rate": round(semantic_pass / total, 4) if total else 0.0,
        "counts": {
            "syntax_correct": syntax_correct,
            "static_pass": static_pass,
            "mission_pass": mission_pass,
            "mission_fail": mission_counter["FAIL"],
            "mission_timeout": mission_counter["TIMEOUT"],
            "semantic_match": semantic_pass,
        },
        "error_stats": dict(sorted(error_counter.items())),
        "results": summary_rows,
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in summary_rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "retrieved_contexts.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in retrieved_rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "error_stats.json").write_text(
        json.dumps({"error_stats": dict(sorted(error_counter.items()))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = f"""# baseline_rag_v1

## 设置

- benchmark: `{summary['benchmark_dir']}`
- total: {total}
- timeout_per_case: {args.timeout} sec
- generator: `deepseek`
- model: `{summary['model']}`
- exclude_oracle: `{summary['retrieval']['exclude_oracle']}`
- corpus_chunks: {summary['retrieval']['corpus_chunks']}
- max_context_chars: {summary['retrieval']['max_context_chars']}
- retrieval_strategy: source-tree priority + component-aware + keyword overlap
- generation_policy: RAG prompting only, no IR, no grounding table, no repair feedback

## 指标

- 语法正确率: {summary['counts']['syntax_correct']}/{total} = {summary['syntax_correct_rate']:.2%}
- 静态通过率: {summary['counts']['static_pass']}/{total} = {summary['static_pass_rate']:.2%}
- 可执行率: {summary['counts']['mission_pass']}/{total} = {summary['mission_success_rate']:.2%}
- 错误率: {failed}/{total} = {summary['error_rate']:.2%}
- 语义匹配率: {summary['counts']['semantic_match']}/{total} = {summary['semantic_match_rate']:.2%}

## 主要错误分布

{chr(10).join(f"- {key}: {value}" for key, value in sorted(error_counter.items()))}

## 检索策略说明

1. **始终注入** AFSIM 关键语法规则（WST类型、单位、坐标格式、end_xxx等）+ 正确示例
2. **源目录优先**：根据任务 source_hint 定位 demo 目录，该目录树内所有 chunk 获得 +40~+80 的检索加分
3. **组件匹配**：chunk 包含的 AFSIM 组件类型与任务 covered_components 匹配时获得加分
4. **全局关键词**：token 重叠 + 路径关键词填充剩余 context 预算
5. **Oracle 排除**：默认排除 source_hint 指向的 oracle 脚本文件
"""
    (output_dir / "README.md").write_text(md, encoding="utf-8")

    print(f"\nDone. {total} tasks → mission PASS={mission_pass} ({mission_pass/total:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
