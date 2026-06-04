#!/usr/bin/env python3
"""
Task-015: AFSIM Agent v1

End-to-end orchestrator that integrates:
- benchmark-backed intent parsing
- AFSIM-IR
- grounding
- hierarchical generation planning
- demo-backed script realization
- static verification
- one-round self repair
- mission execution
- execution repair analysis

This v1 is intentionally scoped to the curated benchmark tasks that already
have IR examples and mirrored demo sources.
"""

from __future__ import annotations

import argparse
import json
import shutil
from copy import deepcopy
from pathlib import Path

from execution_repair_planner_v1 import build_execution_repair_plan
from grounding_library_v1 import (
    normalize_component_family,
    resolve_component,
    resolve_platform,
    resolve_side,
    resolve_task,
)
from hierarchical_generation_planner_v1 import build_generation_plan
from run_mission import run_mission
from self_repair_planner_v1 import build_repair_plan
from static_checker_v1 import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark_v1" / "tasks.jsonl"
IR_EXAMPLES_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"
OUTPUT_ROOT = ROOT / "afsim_agent_v1"

DEFAULT_TASK_IDS = ["BV1-001", "BV1-003", "BV1-005"]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_benchmark_index() -> dict[str, dict]:
    return {row["id"]: row for row in load_jsonl(BENCHMARK_PATH)}


def load_ir_example_index() -> dict[str, dict]:
    rows = load_jsonl(IR_EXAMPLES_PATH)
    return {row["source_task_id"]: row for row in rows}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def intent_parse_task(task: dict, ir_example_index: dict[str, dict]) -> dict:
    source_task_id = task["id"]
    if source_task_id not in ir_example_index:
        raise KeyError(f"No IR example available for task {source_task_id}")

    example = deepcopy(ir_example_index[source_task_id])
    return {
        "version": "intent_parsing_v1",
        "task_id": source_task_id,
        "parser_mode": "benchmark_example_alignment",
        "matched_ir_example_id": example["id"],
        "supported": True,
        "input": task["input"],
        "ir": example["ir"],
        "notes": [
            "v1 currently uses curated benchmark-to-IR alignment for supported tasks",
            "open-ended LLM intent parsing is the next integration step after this workflow shell",
        ],
    }


def build_grounded_ir(ir: dict) -> dict:
    grounded = {
        "version": "grounded_ir_v1",
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


def derive_demo_root(source_path: Path) -> Path:
    try:
        idx = source_path.parts.index("demo_sources")
    except ValueError as exc:
        raise ValueError(f"source path is not under demo_sources: {source_path}") from exc
    if idx + 1 >= len(source_path.parts):
        raise ValueError(f"cannot derive demo root from source path: {source_path}")
    return Path(*source_path.parts[: idx + 2])


def realize_workspace(task: dict, run_dir: Path, exercise_repair: bool) -> dict:
    source_path = ROOT / Path(task["source_hint"])
    demo_root = derive_demo_root(source_path)
    relative_script_path = source_path.relative_to(demo_root)
    workspace_dir = run_dir / "workspace"

    if workspace_dir.exists():
        shutil.rmtree(workspace_dir)
    shutil.copytree(demo_root, workspace_dir)
    (workspace_dir / "output").mkdir(exist_ok=True)

    workspace_script_path = workspace_dir / relative_script_path
    original_text = workspace_script_path.read_text(encoding="utf-8-sig")
    mutation = {"mutation_applied": False}
    if exercise_repair:
        mutated_text, mutation = remove_first_end_time(original_text)
        workspace_script_path.write_text(mutated_text, encoding="utf-8")

    return {
        "version": "script_realization_v1",
        "realizer_mode": "mirrored_demo_workspace",
        "source_hint": task["source_hint"],
        "demo_root": str(demo_root.relative_to(ROOT)),
        "workspace_dir": str(workspace_dir.relative_to(ROOT)),
        "workspace_script": str(workspace_script_path.relative_to(ROOT)),
        "exercise_repair_probe": exercise_repair,
        "repair_probe": mutation,
        "notes": [
            "v1 mirrors the full demo workspace so mission.exe can resolve includes, outputs, and local dependencies",
            "script generation remains demo-backed for the currently supported benchmark tasks",
        ],
    }


def run_task(task: dict, ir_example_index: dict[str, dict], exercise_repair: bool) -> dict:
    run_dir = OUTPUT_ROOT / task["id"]
    run_dir.mkdir(parents=True, exist_ok=True)

    intent_result = intent_parse_task(task, ir_example_index)
    ir = intent_result["ir"]
    grounded_ir = build_grounded_ir(ir)
    generation_plan = build_generation_plan(
        {
            "source_type": "afsim_agent_v1",
            "source_id": task["id"],
            "source_task_id": task["id"],
            "ir": ir,
        }
    )
    realization = realize_workspace(task, run_dir, exercise_repair=exercise_repair)
    script_path = ROOT / realization["workspace_script"]

    static_before = analyze_script_text(script_path.read_text(encoding="utf-8-sig"), script_label=str(script_path))
    repair_plan = None
    static_after = static_before
    final_script_path = script_path

    if not static_before["static_pass"]:
        repair_plan = build_repair_plan(script_path, script_path.read_text(encoding="utf-8-sig"), {"ir": ir}, generation_plan)
        write_json(run_dir / "repair_plan.json", repair_plan)
        repaired_script_path = run_dir / "workspace" / script_path.name
        repaired_script_path.write_text(repair_plan["repaired_text_preview"], encoding="utf-8")
        final_script_path = repaired_script_path
        static_after = analyze_script_text(final_script_path.read_text(encoding="utf-8-sig"), script_label=str(final_script_path))

    return_code, stdout, stderr = run_mission(str(final_script_path), options=["-es", "-fio"])
    mission_log_text = "\n".join(part for part in [stdout, stderr] if part)
    mission_status = "PASS" if return_code == 0 and "FATAL:" not in mission_log_text else "FAIL"
    mission_log_path = run_dir / "mission.log"
    mission_log_path.write_text(mission_log_text, encoding="utf-8")

    execution_plan = build_execution_repair_plan(
        final_script_path,
        mission_status,
        return_code,
        mission_log_text,
        static_after,
    )

    write_json(run_dir / "intent_result.json", intent_result)
    write_json(run_dir / "ir.json", ir)
    write_json(run_dir / "grounded_ir.json", grounded_ir)
    write_json(run_dir / "generation_plan.json", generation_plan)
    write_json(run_dir / "script_realization.json", realization)
    write_json(run_dir / "static_before.json", static_before)
    write_json(run_dir / "static_after.json", static_after)
    write_json(run_dir / "execution_repair.json", execution_plan)

    summary = {
        "task_id": task["id"],
        "input": task["input"],
        "matched_ir_example_id": intent_result["matched_ir_example_id"],
        "grounding_ok": grounded_ir["all_grounded"],
        "generation_ready": generation_plan["ready_for_generation"],
        "initial_static_pass": static_before["static_pass"],
        "self_repair_triggered": repair_plan is not None,
        "self_repair_success": bool(repair_plan and static_after["static_pass"]),
        "final_static_pass": static_after["static_pass"],
        "mission_status": mission_status,
        "execution_route": execution_plan["repair_recommendation"]["route"],
        "final_script": str(final_script_path.relative_to(ROOT)),
    }
    write_json(run_dir / "task_summary.json", summary)
    return summary


def write_readme(task_summaries: list[dict]) -> None:
    lines = [
        "# AFSIM Agent v1",
        "",
        "当前主系统集成版本。",
        "",
        "## Workflow",
        "",
        "- Natural Language",
        "- Intent Parsing",
        "- AFSIM-IR",
        "- Grounding",
        "- Hierarchical Generation",
        "- Static Verification",
        "- Self Repair",
        "- Execution Repair",
        "- Executable Scenario",
        "",
        "## 当前实现边界",
        "",
        "- Intent Parsing: benchmark-backed",
        "- Script Realization: mirrored demo workspace",
        "- Static Repair: one-round deterministic safe repair + route planning",
        "- Execution Repair: mission log classification + repair routing",
        "",
        "## 任务汇总",
        "",
    ]
    for row in task_summaries:
        lines.append(
            f"- `{row['task_id']}`: final_static_pass={row['final_static_pass']}, "
            f"mission_status={row['mission_status']}, execution_route={row['execution_route']}"
        )
    lines.append("")
    lines.append("## 说明")
    lines.append("")
    lines.append("- `BV1-001` 启用了受控 self-repair probe：移除 `end_time` 后再自动补回。")
    lines.append("- 当前版本已经是完整 workflow，但开放自然语言解析和生成式 IR-to-Script 仍是下一阶段工作。")
    lines.append("")
    (OUTPUT_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run AFSIM Agent v1 on supported benchmark tasks.")
    parser.add_argument("--task-ids", nargs="*", default=DEFAULT_TASK_IDS, help="Benchmark task ids to run.")
    parser.add_argument("--repair-probe-task", default="BV1-001", help="Task id that should exercise one self-repair round.")
    args = parser.parse_args()

    benchmark_index = load_benchmark_index()
    ir_example_index = load_ir_example_index()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    task_summaries = []
    for task_id in args.task_ids:
        if task_id not in benchmark_index:
            raise SystemExit(f"Unknown benchmark task id: {task_id}")
        summary = run_task(
            benchmark_index[task_id],
            ir_example_index,
            exercise_repair=(task_id == args.repair_probe_task),
        )
        task_summaries.append(summary)

    overall = {
        "version": "afsim_agent_v1",
        "task_ids": args.task_ids,
        "repair_probe_task": args.repair_probe_task,
        "counts": {
            "total": len(task_summaries),
            "grounding_ok": sum(1 for row in task_summaries if row["grounding_ok"]),
            "generation_ready": sum(1 for row in task_summaries if row["generation_ready"]),
            "final_static_pass": sum(1 for row in task_summaries if row["final_static_pass"]),
            "mission_pass": sum(1 for row in task_summaries if row["mission_status"] == "PASS"),
        },
        "tasks": task_summaries,
    }
    write_json(OUTPUT_ROOT / "summary.json", overall)
    write_readme(task_summaries)
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
