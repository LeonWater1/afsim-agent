#!/usr/bin/env python3
"""
Task-013: Minimal Agent Loop v0

This script stitches together the existing phase outputs into a runnable
minimal loop for a small benchmark subset:

Natural Language
-> Intent Parsing
-> AFSIM-IR
-> Grounding
-> IR-to-Script
-> Static Verification
-> One-round Self Repair
-> Inspectable final script

Current v0 scope is intentionally narrow and honest:
- intent parsing is benchmark-backed for selected tasks
- script realization is demo-backed from mirrored official AFSIM sources
- one task receives a controlled repair probe to verify the repair path
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from grounding_library_v1 import (
    normalize_component_family,
    resolve_component,
    resolve_platform,
    resolve_side,
    resolve_task,
)
from hierarchical_generation_planner_v1 import build_generation_plan
from self_repair_planner_v1 import build_repair_plan
from static_checker_v1 import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark_v1" / "tasks.jsonl"
IR_EXAMPLES_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"
OUTPUT_ROOT = ROOT / "minimal_agent_v0"

DEFAULT_TASK_IDS = ["BV1-001", "BV1-003", "BV1-005"]
IR_EXAMPLE_BY_TASK = {
    "BV1-001": "IRX-001",
    "BV1-003": "IRX-002",
    "BV1-005": "IRX-003",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_benchmark_index() -> dict[str, dict]:
    return {row["id"]: row for row in load_jsonl(BENCHMARK_PATH)}


def load_ir_example_index() -> dict[str, dict]:
    rows = load_jsonl(IR_EXAMPLES_PATH)
    return {row["source_task_id"]: row for row in rows}


def intent_parse_task(task: dict, ir_example_index: dict[str, dict]) -> dict:
    source_task_id = task["id"]
    if source_task_id not in ir_example_index:
        raise KeyError(f"No IR example available for task {source_task_id}")

    example = deepcopy(ir_example_index[source_task_id])
    return {
        "version": "intent_parsing_v0",
        "task_id": source_task_id,
        "parser_mode": "benchmark_example_alignment",
        "matched_ir_example_id": example["id"],
        "supported": True,
        "input": task["input"],
        "ir": example["ir"],
        "notes": [
            "v0 uses curated benchmark-to-IR alignment instead of open-ended LLM parsing",
            "this is a minimal integration loop, not the final generalized intent parser",
        ],
    }


def build_grounded_ir(ir: dict) -> dict:
    grounded = {
        "version": "grounded_ir_v0",
        "schema_version": ir.get("schema_version"),
        "scenario": deepcopy(ir.get("scenario", {})),
        "sides": [],
        "locations": deepcopy(ir.get("locations", [])),
        "routes": deepcopy(ir.get("routes", [])),
        "components": {},
        "entities": [],
        "tasks": [],
        "all_grounded": True,
        "unresolved_items": [],
    }

    for side in ir.get("sides", []):
        side_grounding = resolve_side(side.get("id", ""))
        row = deepcopy(side)
        row["grounding"] = side_grounding
        grounded["sides"].append(row)
        if not side_grounding["matched"]:
            grounded["all_grounded"] = False
            grounded["unresolved_items"].append({"kind": "side", "side_id": side.get("id")})

    for family_name, entries in ir.get("components", {}).items():
        family = normalize_component_family(family_name)
        grounded_rows = []
        for entry in entries:
            component_grounding = resolve_component(
                family,
                label=entry.get("role", ""),
                type_hint=entry.get("type_hint", ""),
            )
            row = deepcopy(entry)
            row["grounding"] = component_grounding
            grounded_rows.append(row)
            if not component_grounding["matched"]:
                grounded["all_grounded"] = False
                grounded["unresolved_items"].append(
                    {"kind": "component", "family": family, "component_id": entry.get("id")}
                )
        grounded["components"][family] = grounded_rows

    for entity in ir.get("entities", []):
        side_grounding = resolve_side(entity.get("side", ""))
        platform_grounding = resolve_platform(
            label=entity.get("role", ""),
            platform_type_hint=entity.get("platform_type_hint", ""),
        )
        row = deepcopy(entity)
        row["side_grounding"] = side_grounding
        row["grounding"] = platform_grounding
        grounded["entities"].append(row)
        if not side_grounding["matched"]:
            grounded["all_grounded"] = False
            grounded["unresolved_items"].append(
                {"kind": "entity_side", "entity_id": entity.get("id"), "side": entity.get("side")}
            )
        if not platform_grounding["matched"]:
            grounded["all_grounded"] = False
            grounded["unresolved_items"].append({"kind": "entity", "entity_id": entity.get("id")})

    for task in ir.get("tasks", []):
        task_grounding = resolve_task(task.get("type", ""))
        row = deepcopy(task)
        row["grounding"] = task_grounding
        grounded["tasks"].append(row)
        if not task_grounding["matched"]:
            grounded["all_grounded"] = False
            grounded["unresolved_items"].append({"kind": "task", "task_id": task.get("id")})

    return grounded


def remove_first_end_time(script_text: str) -> tuple[str, dict]:
    lines = script_text.splitlines()
    removed = None
    kept = []
    for line in lines:
        if removed is None and line.strip().startswith("end_time "):
            removed = line
            continue
        kept.append(line)
    if removed is None:
        return script_text, {"mutation_applied": False}
    return "\n".join(kept) + "\n", {
        "mutation_applied": True,
        "mutation_kind": "remove_end_time",
        "removed_line": removed,
    }


def realize_script(task: dict, run_dir: Path, exercise_repair: bool) -> dict:
    source_path = ROOT / Path(task["source_hint"])
    oracle_text = source_path.read_text(encoding="utf-8-sig")
    initial_text = oracle_text
    mutation = {"mutation_applied": False}

    if exercise_repair:
        initial_text, mutation = remove_first_end_time(oracle_text)

    oracle_copy_path = run_dir / "oracle_reference.txt"
    initial_script_path = run_dir / "initial_script.txt"
    oracle_copy_path.write_text(oracle_text, encoding="utf-8")
    initial_script_path.write_text(initial_text, encoding="utf-8")

    return {
        "version": "ir_to_script_v0",
        "realizer_mode": "demo_backed_template_realization",
        "source_hint": task["source_hint"],
        "source_type": task.get("source_type"),
        "oracle_copy": str(oracle_copy_path.relative_to(ROOT)),
        "initial_script": str(initial_script_path.relative_to(ROOT)),
        "exercise_repair_probe": exercise_repair,
        "repair_probe": mutation,
        "notes": [
            "v0 realizes scripts from mirrored official demos for a minimal closed-loop integration check",
            "full generative IR-to-Script remains a later task",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_task_loop(task: dict, ir_example_index: dict[str, dict], exercise_repair: bool) -> dict:
    run_dir = OUTPUT_ROOT / task["id"]
    run_dir.mkdir(parents=True, exist_ok=True)

    intent_result = intent_parse_task(task, ir_example_index)
    ir = intent_result["ir"]
    grounded_ir = build_grounded_ir(ir)
    generation_plan = build_generation_plan(
        {
            "source_type": "minimal_agent_v0",
            "source_id": task["id"],
            "source_task_id": task["id"],
            "ir": ir,
        }
    )
    realization = realize_script(task, run_dir, exercise_repair=exercise_repair)

    initial_script_path = ROOT / realization["initial_script"]
    initial_text = initial_script_path.read_text(encoding="utf-8-sig")
    static_analysis = analyze_script_text(initial_text, script_label=str(initial_script_path))

    repair_triggered = not static_analysis["static_pass"]
    repair_plan = None
    final_script_path = initial_script_path
    final_analysis = static_analysis

    if repair_triggered:
        repair_plan = build_repair_plan(
            initial_script_path,
            initial_text,
            ir_context={"ir": ir},
            plan_context=generation_plan,
        )
        repair_plan_path = run_dir / "repair_plan.json"
        write_json(repair_plan_path, repair_plan)

        repaired_preview_path = run_dir / "repaired_preview.txt"
        repaired_preview_path.write_text(repair_plan["repaired_text_preview"], encoding="utf-8")
        realization["repaired_preview"] = str(repaired_preview_path.relative_to(ROOT))

        post = repair_plan["safe_repair_attempt"]["post_repair_analysis"]
        if post["static_pass"]:
            final_script_path = repaired_preview_path
            final_analysis = post
        else:
            final_analysis = post

    write_json(run_dir / "intent_result.json", intent_result)
    write_json(run_dir / "ir.json", ir)
    write_json(run_dir / "grounded_ir.json", grounded_ir)
    write_json(run_dir / "generation_plan.json", generation_plan)
    write_json(run_dir / "script_realization.json", realization)
    write_json(run_dir / "static_analysis.json", static_analysis)
    write_json(run_dir / "final_analysis.json", final_analysis)

    summary = {
        "task_id": task["id"],
        "input": task["input"],
        "matched_ir_example_id": intent_result["matched_ir_example_id"],
        "grounding_ok": grounded_ir["all_grounded"],
        "generation_ready": generation_plan["ready_for_generation"],
        "initial_script": realization["initial_script"],
        "initial_static_pass": static_analysis["static_pass"],
        "repair_triggered": repair_triggered,
        "repair_success": bool(repair_plan and repair_plan["safe_repair_attempt"]["post_repair_analysis"]["static_pass"]),
        "final_script": str(final_script_path.relative_to(ROOT)),
        "final_static_pass": final_analysis["static_pass"],
        "final_primary_error": final_analysis["primary_error"],
        "final_error_ids": final_analysis["static_error_ids"],
    }
    write_json(run_dir / "task_summary.json", summary)
    return summary


def write_readme(task_summaries: list[dict]) -> None:
    lines = [
        "# minimal_agent_v0",
        "",
        "最小 Agent 闭环集成产物。",
        "",
        "## 范围",
        "",
        "- Intent Parsing: benchmark-backed",
        "- AFSIM-IR: 使用现有 `ir_examples_v1`",
        "- Grounding: `grounding_library_v1`",
        "- Hierarchical Generation Plan: `hierarchical_generation_planner_v1`",
        "- IR-to-Script: demo-backed template realization",
        "- Static Verification: `static_checker_v1`",
        "- Self Repair: `self_repair_planner_v1` 一轮",
        "",
        "## 任务汇总",
        "",
    ]
    for row in task_summaries:
        lines.append(
            f"- `{row['task_id']}`: initial_static_pass={row['initial_static_pass']}, "
            f"repair_triggered={row['repair_triggered']}, final_static_pass={row['final_static_pass']}"
        )
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- 这是 Task-013 的最小可运行闭环，不是最终泛化版 Agent。")
    lines.append("- 为了验证 Self Repair 路径，`BV1-001` 在初始脚本阶段刻意移除了 `end_time`。")
    lines.append("- 最终脚本以静态可检查为目标；运行时依赖与全文生成会在后续任务继续完善。")
    lines.append("")
    (OUTPUT_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run minimal Agent loop v0 on a small benchmark subset.")
    parser.add_argument("--task-ids", nargs="*", default=DEFAULT_TASK_IDS, help="Benchmark task ids to run.")
    parser.add_argument("--repair-probe-task", default="BV1-001", help="Task id that should exercise one repair round.")
    args = parser.parse_args()

    benchmark_index = load_benchmark_index()
    ir_example_index = load_ir_example_index()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    task_summaries = []
    for task_id in args.task_ids:
        if task_id not in benchmark_index:
            raise SystemExit(f"Unknown benchmark task id: {task_id}")
        task = benchmark_index[task_id]
        summary = run_task_loop(task, ir_example_index, exercise_repair=(task_id == args.repair_probe_task))
        task_summaries.append(summary)

    overall = {
        "version": "minimal_agent_v0",
        "task_ids": args.task_ids,
        "repair_probe_task": args.repair_probe_task,
        "counts": {
            "total": len(task_summaries),
            "grounding_ok": sum(1 for row in task_summaries if row["grounding_ok"]),
            "generation_ready": sum(1 for row in task_summaries if row["generation_ready"]),
            "initial_static_pass": sum(1 for row in task_summaries if row["initial_static_pass"]),
            "repair_triggered": sum(1 for row in task_summaries if row["repair_triggered"]),
            "repair_success": sum(1 for row in task_summaries if row["repair_success"]),
            "final_static_pass": sum(1 for row in task_summaries if row["final_static_pass"]),
        },
        "tasks": task_summaries,
    }
    write_json(OUTPUT_ROOT / "summary.json", overall)
    write_readme(task_summaries)
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
