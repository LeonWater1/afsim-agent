#!/usr/bin/env python3
"""Fair Direct Prompt and RAG baselines for benchmark.

The baselines intentionally stop at one-shot script generation. They do not use
AFSIM-IR, grounding, static/mission feedback, execution repair, or deterministic
postprocessing before evaluation.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from core.llm_client import LLMClient, strip_code_fences
from core.mission_log_parser import parse as parse_mission_log
from core.run_mission import load_config
from core.static_checker import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark" / "tasks.jsonl"

GENERIC_AFSIM_CONSTRAINTS = """AFSIM 2.9.0 script constraints:
- Return a complete .txt-style AFSIM scenario script as plain text only.
- Do not return markdown fences, JSON, comments about your answer, or explanations.
- Use documented AFSIM/WSF-style blocks such as platform_type, platform, mover,
  sensor, weapon, processor, route, event_output, and end_time.
- Close every opened block with the matching end_xxx tag.
- Use units for physical values, for example m/sec, ft, nm, sec, deg, g.
- Coordinates must be valid AFSIM coordinates such as 35.5n 120.3w or
  38:44:52.3n 90:21:36.4w.
- Use print() rather than cout in script code.
- Do not wrap on_initialize or on_update code in script/end_script blocks.
- Use conservative, simple executable structure when details are absent.
"""

DIRECT_SYSTEM_PROMPT = f"""You generate AFSIM 2.9.0 mission scripts.

This is a zero-structure Direct Prompt baseline. Use only the user's natural
language task, the generic AFSIM constraints below, and the requested output
format. Do not use retrieval, demos, oracle scripts, AFSIM-IR, grounding tables,
static checker feedback, mission.exe feedback, repair feedback, or benchmark
task-specific special cases.

{GENERIC_AFSIM_CONSTRAINTS}
"""

RAG_SYSTEM_PROMPT = f"""You generate AFSIM 2.9.0 mission scripts.

This is a RAG baseline. Use the user's task, the fixed retrieved context, the
generic AFSIM constraints below, and the requested output format. Do not use
AFSIM-IR, grounding tables, static checker feedback, mission.exe feedback,
repair feedback, oracle scripts for the current task, or benchmark task-specific
special cases.

{GENERIC_AFSIM_CONSTRAINTS}
"""

REFERENCE_FILES = [
    ROOT / "references" / "script_syntax_critical.md",
    ROOT / "references" / "common_mistakes.md",
    ROOT / "references" / "file_structure.md",
    ROOT / "references" / "commands_reference.md",
    ROOT / "references" / "mover_reference.md",
    ROOT / "references" / "sensor_types_reference.md",
    ROOT / "references" / "script_api_reference.md",
    ROOT / "references" / "examples.md",
    ROOT / "SKILL.md",
]

SKIP_DEMO_SEGMENTS = {
    "output",
    "doc",
    "docs",
    "__pycache__",
    "validation_logs",
}


def load_tasks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def read_text_lossy(path: Path, max_chars: int = 6000) -> str:
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")[:max_chars]
    except OSError:
        return ""


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9_+-]{2,}", lowered))
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update(cjk)
    tokens.update(a + b for a, b in zip(cjk, cjk[1:]))
    return {token for token in tokens if token}


def top_level_demo_name(source_hint: str) -> str:
    normalized = source_hint.replace("\\", "/")
    marker = "demo_sources/"
    if marker not in normalized:
        return ""
    rest = normalized.split(marker, 1)[1]
    return rest.split("/", 1)[0].lower()


def build_rag_corpus(include_demos: bool = True) -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for path in REFERENCE_FILES:
        if path.exists():
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            text = read_text_lossy(path, max_chars=5000)
            corpus.append({"kind": "reference", "source": rel, "text": text, "demo_root": ""})

    if include_demos:
        for bench in ["benchmark", "benchmark_extended"]:
            demo_root = ROOT / "benchmarks" / bench / "demo_sources"
            if not demo_root.exists():
                continue
            for path in sorted(demo_root.rglob("*.txt")):
                rel_parts = [part.lower() for part in path.relative_to(demo_root).parts]
                if set(rel_parts) & SKIP_DEMO_SEGMENTS:
                    continue
                if path.stat().st_size > 160_000:
                    continue
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                corpus.append(
                    {
                        "kind": "demo",
                        "source": rel,
                        "text": read_text_lossy(path, max_chars=5000),
                        "demo_root": rel_parts[0] if rel_parts else "",
                    }
                )

    for item in corpus:
        item["tokens"] = sorted(tokenize(item["source"] + "\n" + item["text"]))
    return corpus


def retrieve_context(task: dict[str, Any], corpus: list[dict[str, Any]], top_k: int, max_context_chars: int) -> list[dict[str, str]]:
    query = " ".join(
        [
            task.get("id", ""),
            task.get("input", ""),
            " ".join(task.get("covered_components", [])),
            " ".join(task.get("evaluation_focus", [])),
        ]
    )
    query_tokens = tokenize(query)
    excluded_demo = top_level_demo_name(task.get("source_hint", ""))
    oracle_norm = task.get("source_hint", "").replace("\\", "/").lower()

    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in corpus:
        source_norm = item["source"].replace("\\", "/").lower()
        if item["kind"] == "demo":
            if source_norm == oracle_norm:
                continue
            if excluded_demo and item.get("demo_root", "").lower() == excluded_demo:
                continue
        item_tokens = set(item.get("tokens", []))
        overlap = len(query_tokens & item_tokens)
        path_bonus = sum(2 for token in query_tokens if len(token) >= 3 and token in source_norm)
        kind_bonus = 3 if item["kind"] == "reference" else 1
        score = overlap + path_bonus + kind_bonus
        if score > 0:
            scored.append((score, item["source"], item))

    scored.sort(key=lambda row: (-row[0], row[1]))
    selected: list[dict[str, str]] = []
    char_count = 0
    for _, _, item in scored:
        if len(selected) >= top_k:
            break
        remaining = max_context_chars - char_count
        if remaining <= 300:
            break
        text = item["text"][:remaining]
        selected.append({"kind": item["kind"], "source": item["source"], "text": text})
        char_count += len(text)
    return selected


def format_context(chunks: list[dict[str, str]]) -> str:
    parts = []
    for idx, item in enumerate(chunks, start=1):
        parts.append(f"[{idx}] {item['kind'].upper()} {item['source']}\n{item['text'].strip()}")
    return "\n\n---\n\n".join(parts)


def direct_messages(task: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": DIRECT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Task ID: {task['id']}\nNatural-language task:\n{task['input']}\n\nReturn only the complete AFSIM script.",
        },
    ]


def rag_messages(task: dict[str, Any], context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Task ID: {task['id']}\n"
                f"Natural-language task:\n{task['input']}\n\n"
                f"Retrieved context:\n{context}\n\n"
                "Return only the complete AFSIM script."
            ),
        },
    ]


def generate_script(task: dict[str, Any], client: LLMClient, mode: str, rag_chunks: list[dict[str, str]]) -> str:
    messages = direct_messages(task) if mode == "direct" else rag_messages(task, format_context(rag_chunks))
    response = client.chat(messages, temperature=0.0, max_tokens=8192)
    return strip_code_fences(response.content).strip() + "\n"


def semantic_match(task: dict[str, Any], script_text: str, mission_status: str) -> bool:
    if mission_status != "PASS":
        return False
    component_map = {
        "Platform": lambda s: "platform " in s.lower() and "platform_type " in s.lower(),
        "Route": lambda s: "route" in s.lower(),
        "Mover": lambda s: "mover " in s.lower(),
        "Sensor": lambda s: "sensor " in s.lower(),
        "Weapon": lambda s: "weapon " in s.lower(),
        "Processor": lambda s: "processor " in s.lower(),
        "Comm": lambda s: "comm " in s.lower(),
        "Acoustic": lambda s: "acoustic" in s.lower(),
        "BehaviorTree": lambda s: "behavior_tree" in s.lower() or "btree" in s.lower(),
        "Space": lambda s: "space_mover" in s.lower() or "orbital" in s.lower(),
        "ElectronicWarfare": lambda s: "jammer" in s.lower() or "esm" in s.lower() or "chaff" in s.lower(),
        "IADS": lambda s: "sam" in s.lower() and "radar" in s.lower(),
        "LaserDesignator": lambda s: "laser" in s.lower(),
        "Coverage": lambda s: "heatmap" in s.lower(),
        "Cyber": lambda s: "cyber" in s.lower(),
        "Fires": lambda s: "artillery" in s.lower() or "time_on_target" in s.lower(),
    }
    checks = []
    for component in task.get("covered_components", []):
        matcher = component_map.get(component)
        if matcher:
            checks.append(matcher(script_text))
    return all(checks) if checks else bool(script_text.strip())


def classify_primary_error(static_result: dict[str, Any], mission_diag: dict[str, Any], api_error: str) -> str:
    if api_error:
        return "API_ERROR"
    if static_result.get("primary_error"):
        return static_result["primary_error"]
    categories = mission_diag.get("error_categories", [])
    if categories:
        return categories[0]
    return ""


def run_mission_script(script_path: Path, timeout: int) -> tuple[str, int | None, str]:
    config = load_config()
    mission_exe = Path(config["mission_exe"])
    cmd = [str(mission_exe), "-es", "-fio", str(script_path)]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        log_text = result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else "")
        status = "PASS" if result.returncode == 0 and "FATAL:" not in log_text else "FAIL"
        return status, result.returncode, log_text
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        return "TIMEOUT", None, stdout + ("\nSTDERR:\n" + stderr if stderr else "")


def run_one(
    task: dict[str, Any],
    client: LLMClient,
    mode: str,
    output_dir: Path,
    rag_corpus: list[dict[str, Any]],
    top_k: int,
    max_context_chars: int,
    timeout: int,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    task_id = task["id"]
    run_dir = output_dir / task_id
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "generated_script.txt"
    log_path = run_dir / "mission.log"
    retrieved_record = None
    api_error = ""

    rag_chunks: list[dict[str, str]] = []
    if mode == "rag":
        rag_chunks = retrieve_context(task, rag_corpus, top_k=top_k, max_context_chars=max_context_chars)
        retrieved_record = {
            "id": task_id,
            "top_k": top_k,
            "max_context_chars": max_context_chars,
            "excluded_demo_root": top_level_demo_name(task.get("source_hint", "")),
            "sources": [{"kind": item["kind"], "source": item["source"]} for item in rag_chunks],
        }
        write_json(run_dir / "retrieved_context.json", retrieved_record)

    try:
        script_text = generate_script(task, client, mode, rag_chunks)
    except Exception as exc:
        script_text = ""
        api_error = f"{type(exc).__name__}: {exc}"

    script_path.write_text(script_text, encoding="utf-8")
    static_result = analyze_script_text(script_text, script_label=str(script_path)) if script_text else {
        "syntax_correct": False,
        "static_pass": False,
        "primary_error": "API_ERROR",
        "static_error_ids": ["API_ERROR"],
        "findings": [{"error_id": "API_ERROR", "line": 0, "message": api_error}],
    }

    if api_error:
        mission_status, return_code, log_text = "FAIL", None, api_error
        mission_diag = {"error_categories": ["api_error"], "errors": [], "repair_hints": []}
    else:
        mission_status, return_code, log_text = run_mission_script(script_path, timeout=timeout)
        mission_diag = parse_mission_log(log_text, return_code)
    log_path.write_text(log_text, encoding="utf-8", errors="replace")
    write_json(run_dir / "static.json", static_result)
    write_json(run_dir / "mission_diagnostics.json", mission_diag)

    primary_error = classify_primary_error(static_result, mission_diag, api_error)
    secondary = sorted(
        {
            *static_result.get("static_error_ids", []),
            *mission_diag.get("error_categories", []),
        }
        - {primary_error, ""}
    )
    row = {
        "id": task_id,
        "input": task.get("input", ""),
        "mode": mode,
        "generated_script": str(script_path.relative_to(ROOT)).replace("\\", "/"),
        "syntax_correct": bool(static_result["syntax_correct"]),
        "static_pass": bool(static_result["static_pass"]),
        "static_error_ids": static_result.get("static_error_ids", []),
        "static_errors": static_result.get("findings", []),
        "mission_status": mission_status,
        "return_code": return_code,
        "mission_log": str(log_path.relative_to(ROOT)).replace("\\", "/"),
        "mission_error_categories": mission_diag.get("error_categories", []),
        "primary_error": primary_error,
        "secondary_errors": secondary,
        "semantic_match": semantic_match(task, script_text, mission_status),
        "api_error": api_error,
    }
    write_json(run_dir / "result.json", row)
    return row, retrieved_record


def summarize(mode: str, model: str, benchmark_path: Path, output_dir: Path, rows: list[dict[str, Any]], rag_meta: dict[str, Any] | None) -> dict[str, Any]:
    total = len(rows)
    mission_pass = sum(1 for row in rows if row["mission_status"] == "PASS")
    mission_fail = sum(1 for row in rows if row["mission_status"] == "FAIL")
    syntax_ok = sum(1 for row in rows if row["syntax_correct"])
    static_ok = sum(1 for row in rows if row["static_pass"])
    semantic_ok = sum(1 for row in rows if row["semantic_match"])
    primary_counter = Counter(row["primary_error"] for row in rows if row.get("primary_error"))
    error_counter = Counter()
    mission_category_counter = Counter()
    for row in rows:
        for error_id in row.get("static_error_ids", []):
            error_counter[error_id] += 1
        for category in row.get("mission_error_categories", []):
            mission_category_counter[category] += 1
    summary = {
        "name": f"baseline_{mode}_benchmark_fair",
        "mode": mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "benchmark_jsonl": str(benchmark_path.relative_to(ROOT)).replace("\\", "/"),
        "total": total,
        "counts": {
            "total": total,
            "mission_pass": mission_pass,
            "mission_fail": mission_fail,
            "mission_timeout": sum(1 for row in rows if row["mission_status"] == "TIMEOUT"),
            "syntax_correct": syntax_ok,
            "static_pass": static_ok,
            "semantic_match": semantic_ok,
            "api_error": sum(1 for row in rows if row.get("api_error")),
        },
        "mission_success_rate": round(mission_pass / total, 4) if total else 0.0,
        "syntax_correct_rate": round(syntax_ok / total, 4) if total else 0.0,
        "static_pass_rate": round(static_ok / total, 4) if total else 0.0,
        "semantic_match_rate": round(semantic_ok / total, 4) if total else 0.0,
        "primary_error_distribution": dict(sorted(primary_counter.items())),
        "error_type_distribution": dict(sorted(error_counter.items())),
        "mission_error_category_distribution": dict(sorted(mission_category_counter.items())),
        "special_counts": {
            "unknown_command": mission_category_counter["unknown_command"],
            "missing_entity": mission_category_counter["missing_entity"],
            "missing_processor": mission_category_counter["missing_processor"],
            "parser_fatal": mission_category_counter["parser_fatal"],
            "api_error": sum(1 for row in rows if row.get("api_error")),
        },
        "results": rows,
    }
    if rag_meta:
        summary["retrieval"] = rag_meta
    write_json(output_dir / "summary.json", summary)
    write_jsonl(output_dir / "results.jsonl", rows)
    write_json(output_dir / "error_stats.json", {
        "primary_error_distribution": summary["primary_error_distribution"],
        "error_type_distribution": summary["error_type_distribution"],
        "mission_error_category_distribution": summary["mission_error_category_distribution"],
        "special_counts": summary["special_counts"],
    })
    return summary


def write_prompt_template(output_dir: Path, mode: str, model: str, rag_meta: dict[str, Any] | None) -> None:
    text = [
        f"# baseline_{mode}_benchmark_fair prompt",
        "",
        f"- model: `{model}`",
        "- temperature: `0.0`",
        "- no AFSIM-IR",
        "- no Grounding library",
        "- no static checker feedback in prompt",
        "- no mission.exe feedback in prompt",
        "- no repair feedback",
        "- no deterministic postprocess before evaluation",
        "",
        "## Generic Constraints",
        "",
        "```text",
        GENERIC_AFSIM_CONSTRAINTS.strip(),
        "```",
    ]
    if mode == "rag" and rag_meta:
        text.extend([
            "",
            "## Retrieval",
            "",
            f"- top_k: `{rag_meta['top_k']}`",
            f"- max_context_chars: `{rag_meta['max_context_chars']}`",
            f"- corpus_chunks: `{rag_meta['corpus_chunks']}`",
            "- self_oracle_policy: exclude exact oracle path and same top-level demo tree",
            "- label: demo-augmented RAG with same-demo-tree exclusion",
        ])
    (output_dir / "prompt_template.md").write_text("\n".join(text) + "\n", encoding="utf-8")


def write_readme(output_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# {summary['name']}",
        "",
        f"- model: `{summary['model']}`",
        f"- benchmark: `{summary['benchmark_jsonl']}`",
        f"- total: {summary['total']}",
        f"- mission PASS: {summary['counts']['mission_pass']}/{summary['total']} ({summary['mission_success_rate']:.2%})",
        f"- syntax correct: {summary['counts']['syntax_correct']}/{summary['total']} ({summary['syntax_correct_rate']:.2%})",
        f"- static pass: {summary['counts']['static_pass']}/{summary['total']} ({summary['static_pass_rate']:.2%})",
        "",
        "This run is a one-shot baseline evaluation. Generation did not receive IR, grounding, static feedback, mission feedback, repair feedback, or deterministic postprocessing.",
    ]
    if "retrieval" in summary:
        lines.append("")
        lines.append("RAG is labelled demo-augmented because the fixed corpus includes official demo snippets, with exact oracle and same top-level demo tree excluded per task.")
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fair benchmark Direct/RAG baselines.")
    parser.add_argument("--mode", choices=["direct", "rag"], required=True)
    parser.add_argument("--benchmark-jsonl", default=str(BENCHMARK_PATH.relative_to(ROOT)))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--include-demos", action="store_true", default=True)
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_jsonl)
    if not benchmark_path.is_absolute():
        benchmark_path = ROOT / benchmark_path
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / f"baseline_{args.mode}_benchmark_fair"
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = load_tasks(benchmark_path)
    if args.limit:
        tasks = tasks[: args.limit]

    client = LLMClient.from_env(model=args.model)
    rag_corpus = build_rag_corpus(include_demos=args.include_demos) if args.mode == "rag" else []
    rag_meta = None
    if args.mode == "rag":
        rag_meta = {
            "top_k": args.top_k,
            "max_context_chars": args.max_context_chars,
            "corpus_chunks": len(rag_corpus),
            "include_demos": args.include_demos,
            "self_oracle_policy": "exclude_exact_oracle_and_same_top_level_demo_tree",
            "label": "demo_augmented_rag_same_tree_excluded",
        }
    write_prompt_template(output_dir, args.mode, args.model, rag_meta)

    rows: list[dict[str, Any]] = []
    retrieved_rows: list[dict[str, Any]] = []
    def _run_task(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        return run_one(
            task,
            client,
            args.mode,
            output_dir,
            rag_corpus,
            args.top_k,
            args.max_context_chars,
            args.timeout,
        )

    if args.max_workers <= 1:
        for task in tasks:
            row, retrieved = _run_task(task)
            rows.append(row)
            if retrieved:
                retrieved_rows.append(retrieved)
            print(f"{task['id']}: mission={row['mission_status']} syntax={row['syntax_correct']} static={row['static_pass']}")
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(_run_task, task): task["id"] for task in tasks}
            for future in as_completed(futures):
                row, retrieved = future.result()
                rows.append(row)
                if retrieved:
                    retrieved_rows.append(retrieved)
                print(f"{row['id']}: mission={row['mission_status']} syntax={row['syntax_correct']} static={row['static_pass']}")

    rows.sort(key=lambda row: row["id"])
    retrieved_rows.sort(key=lambda row: row["id"])

    if retrieved_rows:
        write_jsonl(output_dir / "retrieved_contexts.jsonl", retrieved_rows)
    summary = summarize(args.mode, args.model, benchmark_path, output_dir, rows, rag_meta)
    write_readme(output_dir, summary)
    print(json.dumps({k: summary[k] for k in ["name", "total", "counts", "mission_success_rate", "syntax_correct_rate", "static_pass_rate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
