#!/usr/bin/env python3
"""
        "LLM-only evaluation pipeline - no deterministic scaffold, demo copy, or IR postprocess fallback.",

Workflow:
- LLM intent parsing
- AFSIM-IR schema validation
- grounding
- hierarchical generation planning
- LLM script generation
- static verification
- LLM static repair when needed
- mission.exe execution
- LLM execution repair when routed

No deterministic scaffold, demo-copy realization, or IR postprocess patch is used
to produce the final script.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from afsim_agent_v1 import build_grounded_ir
from execution_repair_planner_v1 import build_execution_repair_plan
from hierarchical_generation_executor_v1 import execute_layered_generation
from hierarchical_generation_planner_v1 import build_generation_plan
from llm_client_v1 import LLMClient
from llm_intent_parser_v1 import parse_intent_with_llm
from llm_repair_executor_v1 import llm_execution_repair, llm_static_repair
from llm_script_generator_v1 import generate_script_with_llm
from run_direct_baseline import semantic_match
from run_mission import run_mission
from static_checker_v1 import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark_v1" / "tasks.jsonl"
OUTPUT_ROOT = ROOT / "afsim_agent_v2"

DEFAULT_TASK_IDS = ["BV1-001", "BV1-003", "BV1-017"]
EXECUTION_REPAIRABLE_ROUTES = {
    "return_to_self_repair",
    "return_to_script_logic_repair",
    "return_to_layer_regeneration",
    "return_to_ir",
    "return_to_grounding_or_ir",
    "return_to_grounding",
}


def generate_script_with_layered_executor(
    task: dict[str, Any],
    generation_plan: dict[str, Any],
    client: LLMClient,
    run_dir: Path,
) -> dict[str, Any]:
    layered_dir = run_dir / "layered_generation"
    execution_result = execute_layered_generation(
        generation_plan,
        client,
        layered_dir,
        task_context={
            "task_id": task["id"],
            "input": task.get("input", ""),
            "source_hint": task.get("source_hint", ""),
            "demo_id": task.get("demo_id", ""),
        },
    )
    final_script_path = Path(execution_result["final_script_path"])
    script_text = final_script_path.read_text(encoding="utf-8-sig")
    static_analysis = analyze_script_text(script_text, script_label=str(final_script_path))
    return {
        "version": "hierarchical_generation_executor_v1",
        "generator_mode": "layered_executor_v1",
        "script_text": script_text,
        "static_analysis": static_analysis,
        "attempt_count": execution_result.get("chunk_count", len(execution_result.get("layers", []))),
        "attempts": execution_result.get("layers", []),
        "execution_result": execution_result,
        "artifact_dir": str(layered_dir.relative_to(ROOT)),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_benchmark_index() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load_jsonl(BENCHMARK_PATH)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    path.write_text(text, encoding="utf-8")


def merge_results_rows(path: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    if path.exists():
        for row in load_jsonl(path):
            merged[row["id"]] = row
    for row in rows:
        merged[row["id"]] = row
    return [merged[key] for key in sorted(merged)]


def mission_status_from_run(return_code: int | None, stdout: str, stderr: str) -> tuple[str, str]:
    mission_log_text = "\n".join(part for part in [stdout, stderr] if part)
    mission_status = "PASS" if return_code == 0 and "FATAL:" not in mission_log_text else "FAIL"
    return mission_status, mission_log_text


def assess_script_substance(script_text: str) -> dict[str, Any]:
    effective_lines = [
        line.strip()
        for line in script_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    has_platform_type = any(line.startswith("platform_type ") for line in effective_lines)
    has_platform = any(
        line.startswith("platform ")
        and not line.startswith("platform_type ")
        and len(line.split()) >= 3
        for line in effective_lines
    )
    has_route_or_position = any(
        line.startswith("route")
        or line.startswith("position ")
        or " position " in line
        for line in effective_lines
    )
    core_blocks = {
        "sensor",
        "weapon",
        "processor",
        "comm",
        "event_pipe",
        "event_output",
        "csv_event_output",
        "route",
    }
    core_block_count = sum(1 for line in effective_lines if line.split()[0] in core_blocks)
    has_platform_or_type = has_platform_type or has_platform
    empty_shell = (
        len(effective_lines) <= 4
        and not has_platform_or_type
        and all(line.split()[0] in {"script_interface", "debug", "end_script_interface", "end_time"} for line in effective_lines)
    )
    substantive_ready = (
        has_platform_or_type
        and has_route_or_position
        and len(effective_lines) >= 6
        and (core_block_count >= 1 or has_platform_type)
        and not empty_shell
    )
    return {
        "effective_line_count": len(effective_lines),
        "has_platform_or_type": has_platform_or_type,
        "has_route_or_position": has_route_or_position,
        "core_block_count": core_block_count,
        "empty_shell": empty_shell,
        "substantive_ready": substantive_ready,
    }


def enrich_task_summary(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    final_script_rel = normalized.get("final_script", "")
    final_script_path = ROOT / final_script_rel if final_script_rel else None
    script_text = ""
    if final_script_path and final_script_path.exists():
        script_text = final_script_path.read_text(encoding="utf-8-sig")
    substance = assess_script_substance(script_text)
    normalized["effective_line_count"] = substance["effective_line_count"]
    normalized["has_platform_or_type"] = substance["has_platform_or_type"]
    normalized["has_route_or_position"] = substance["has_route_or_position"]
    normalized["core_block_count"] = substance["core_block_count"]
    normalized["empty_shell"] = substance["empty_shell"]
    normalized["substantive_pass"] = bool(
        normalized.get("mission_status") == "PASS"
        and normalized.get("final_static_pass")
        and substance["substantive_ready"]
    )
    normalized.setdefault("reused_existing", False)
    return normalized


def has_reusable_summary(task_id: str) -> bool:
    summary_path = OUTPUT_ROOT / task_id / "task_summary.json"
    if not summary_path.exists():
        return False
    try:
        summary = read_json(summary_path)
    except json.JSONDecodeError:
        return False
    final_script_rel = summary.get("final_script", "")
    if not final_script_rel:
        return False
    return (ROOT / final_script_rel).exists()


def summarize_grounding_state(grounded_ir: dict[str, Any]) -> dict[str, Any]:
    unresolved = grounded_ir.get("unresolved_items", [])
    unresolved_by_kind: dict[str, int] = {}
    for item in unresolved:
        kind = item.get("kind", "unknown")
        unresolved_by_kind[kind] = unresolved_by_kind.get(kind, 0) + 1
    return {
        "all_grounded": grounded_ir.get("all_grounded", False),
        "unresolved_count": len(unresolved),
        "unresolved_by_kind": unresolved_by_kind,
    }


def extract_failure_family(static_analysis: dict[str, Any], execution_plan: dict[str, Any] | None) -> str:
    if execution_plan:
        primary = execution_plan.get("repair_recommendation", {}).get("primary_error", "")
        if primary:
            return primary
        primary = execution_plan.get("execution_analysis", {}).get("primary_error", "")
        if primary:
            return primary
    return static_analysis.get("primary_error", "")


def compute_primary_root_cause(
    static_before: dict[str, Any],
    pre_repair_execution_plan: dict[str, Any] | None,
) -> str:
    root = extract_failure_family(static_before, pre_repair_execution_plan)
    return root or static_before.get("primary_error", "")


def should_reject_repair_as_drift(
    baseline_family: str,
    baseline_static: dict[str, Any],
    baseline_mission_status: str,
    candidate_family: str,
    candidate_static: dict[str, Any],
    candidate_mission_status: str,
) -> bool:
    if candidate_mission_status == "PASS":
        return False
    if not baseline_family or not candidate_family:
        return False
    if baseline_family == candidate_family:
        return False

    baseline_improved = int(baseline_mission_status == "PASS") + int(baseline_static.get("static_pass", False))
    candidate_improved = int(candidate_mission_status == "PASS") + int(candidate_static.get("static_pass", False))
    if candidate_improved > baseline_improved:
        return False
    return True


def run_mission_for_diagnostics(script_path: Path) -> tuple[str, int | None, str]:
    """Run mission.exe for diagnostic output. Only skip empty shells, never skip on static fail."""
    script_text = script_path.read_text(encoding="utf-8-sig")
    substance = assess_script_substance(script_text)
    if substance["empty_shell"]:
        return "SKIPPED", None, "mission.exe skipped because script is an empty shell"
    return_code, stdout, stderr = run_mission(str(script_path), options=["-es", "-fio"])
    mission_status, mission_log_text = mission_status_from_run(return_code, stdout, stderr)
    return mission_status, return_code, mission_log_text

# Backward-compat alias
run_mission_if_static_pass = run_mission_for_diagnostics


def run_task(
    task: dict[str, Any],
    client: LLMClient | None,
    max_intent_attempts: int,
    max_generation_attempts: int,
    rerun_completed: bool,
) -> dict[str, Any]:
    run_dir = OUTPUT_ROOT / task["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "output").mkdir(exist_ok=True)
    summary_path = run_dir / "task_summary.json"
    if not rerun_completed and summary_path.exists():
        cached_summary = enrich_task_summary(read_json(summary_path))
        final_script_path = ROOT / cached_summary.get("final_script", "")
        if final_script_path.exists():
            cached_summary["reused_existing"] = True
            write_json(summary_path, cached_summary)
            return cached_summary
    write_json(run_dir / "task_input.json", task)

    if client is None:
        raise RuntimeError("LLM client is required when rerun-completed is enabled or no reusable cached summary exists")

    intent_result = parse_intent_with_llm(task["id"], task["input"], client, max_attempts=max_intent_attempts)
    ir = intent_result["ir"]
    grounded_ir = build_grounded_ir(ir)
    generation_plan = build_generation_plan(
        {
            "source_type": "afsim_agent_v2",
            "source_id": task["id"],
            "source_task_id": task["id"],
            "ir": ir,
        }
    )

    if generation_plan.get("ready_for_generation", False):
        script_generation = generate_script_with_layered_executor(
            task,
            generation_plan,
            client,
            run_dir,
        )
    else:
        script_generation = generate_script_with_llm(
            task,
            ir,
            grounded_ir,
            generation_plan,
            client,
            max_attempts=max_generation_attempts,
        )

    generated_script_path = run_dir / "generated_script.txt"
    generated_script_path.write_text(script_generation["script_text"], encoding="utf-8")
    static_before = analyze_script_text(script_generation["script_text"], script_label=str(generated_script_path))

    current_script_text = script_generation["script_text"]
    current_script_path = generated_script_path
    static_after = static_before
    llm_static_repair_result = None

    # Run mission.exe BEFORE repair to capture AFSIM parser diagnostics.
    # Only skip for empty shells — static failures still benefit from mission errors.
    pre_repair_mission_status, pre_repair_mission_code, pre_repair_mission_log = run_mission_for_diagnostics(current_script_path)
    (run_dir / "mission.log").write_text(pre_repair_mission_log, encoding="utf-8")
    pre_repair_execution_plan = build_execution_repair_plan(
        current_script_path,
        pre_repair_mission_status,
        pre_repair_mission_code,
        pre_repair_mission_log,
        static_before,
    )
    write_json(run_dir / "pre_repair_execution.json", pre_repair_execution_plan)

    if not static_before["static_pass"]:
        # Pass mission.exe errors to guide the repair with real AFSIM diagnostics
        llm_static_repair_result = llm_static_repair(
            task, current_script_text, ir, grounded_ir, generation_plan, client,
            mission_errors=(pre_repair_mission_log if pre_repair_mission_status == "FAIL" else ""),
        )
        write_json(run_dir / "llm_static_repair.json", llm_static_repair_result)
        current_script_text = llm_static_repair_result["repaired_text"]
        current_script_path = run_dir / "llm_repaired_script.txt"
        current_script_path.write_text(current_script_text, encoding="utf-8")
        static_after = llm_static_repair_result["static_analysis"]

    # Run mission.exe after repair (or on first script if no repair needed).
    # Always write to mission_final.log so results rows point to the authoritative log.
    mission_status, mission_return_code, mission_log_text = run_mission_for_diagnostics(current_script_path)
    (run_dir / "mission_final.log").write_text(mission_log_text, encoding="utf-8")

    execution_plan = build_execution_repair_plan(
        current_script_path,
        mission_status,
        mission_return_code,
        mission_log_text,
        static_after,
    )
    write_json(run_dir / "execution_repair.json", execution_plan)
    primary_root_cause = compute_primary_root_cause(static_before, pre_repair_execution_plan)

    llm_execution_repair_result = None
    final_script_path = current_script_path
    final_static = static_after
    final_mission_status = mission_status
    final_return_code = mission_return_code
    final_log_text = mission_log_text
    final_execution_plan = execution_plan
    repair_drift = {
        "detected": False,
        "stage": "",
        "baseline_family": "",
        "candidate_family": "",
        "action": "accepted_current_script",
    }

    if (
        llm_static_repair_result is not None
        and not static_after["static_pass"]
        and static_before.get("primary_error")
        and static_after.get("primary_error")
        and static_before["primary_error"] != static_after["primary_error"]
    ):
        before_count = len(static_before.get("static_error_ids", []))
        after_count = len(static_after.get("static_error_ids", []))
        if after_count >= before_count:
            current_script_text = script_generation["script_text"]
            current_script_path = generated_script_path
            static_after = static_before
            mission_status = pre_repair_mission_status
            mission_return_code = pre_repair_mission_code
            mission_log_text = pre_repair_mission_log
            execution_plan = pre_repair_execution_plan
            final_script_path = current_script_path
            final_static = static_after
            final_mission_status = mission_status
            final_return_code = mission_return_code
            final_log_text = mission_log_text
            final_execution_plan = execution_plan
            repair_drift = {
                "detected": True,
                "stage": "static_repair",
                "baseline_family": static_before["primary_error"],
                "candidate_family": llm_static_repair_result["static_analysis"].get("primary_error", ""),
                "action": "reverted_to_pre_repair_script",
            }

    if (
        mission_status == "FAIL"
        and execution_plan["repair_recommendation"]["route"] in EXECUTION_REPAIRABLE_ROUTES
    ):
        llm_execution_repair_result = llm_execution_repair(
            task,
            current_script_text,
            ir,
            grounded_ir,
            generation_plan,
            mission_status,
            mission_return_code,
            mission_log_text,
            client,
        )
        write_json(run_dir / "llm_execution_repair.json", llm_execution_repair_result)
        candidate_script_path = run_dir / "execution_repaired_script.txt"
        candidate_script_path.write_text(llm_execution_repair_result["repaired_text"], encoding="utf-8")
        candidate_static = llm_execution_repair_result["static_analysis"]
        candidate_mission_status, candidate_return_code, candidate_log_text = run_mission_for_diagnostics(candidate_script_path)
        candidate_execution_plan = build_execution_repair_plan(
            candidate_script_path,
            candidate_mission_status,
            candidate_return_code,
            candidate_log_text,
            candidate_static,
        )
        baseline_family = primary_root_cause or extract_failure_family(static_after, execution_plan)
        candidate_family = extract_failure_family(candidate_static, candidate_execution_plan)
        if should_reject_repair_as_drift(
            baseline_family,
            static_after,
            mission_status,
            candidate_family,
            candidate_static,
            candidate_mission_status,
        ):
            repair_drift = {
                "detected": True,
                "stage": "execution_repair",
                "baseline_family": baseline_family,
                "candidate_family": candidate_family,
                "action": "kept_pre_execution_repair_script",
            }
        else:
            final_script_path = candidate_script_path
            final_static = candidate_static
            final_mission_status = candidate_mission_status
            final_return_code = candidate_return_code
            final_log_text = candidate_log_text
            final_execution_plan = candidate_execution_plan

        (run_dir / "mission_final.log").write_text(final_log_text, encoding="utf-8")

    grounding_state = summarize_grounding_state(grounded_ir)
    layer_regeneration_attempt = (
        llm_static_repair_result.get("layer_regeneration_attempt")
        if isinstance(llm_static_repair_result, dict)
        else None
    )
    layer_regeneration_triggered = bool(layer_regeneration_attempt and layer_regeneration_attempt.get("attempted"))
    layer_regeneration_static_pass = bool(
        layer_regeneration_attempt
        and layer_regeneration_attempt.get("static_analysis", {}).get("static_pass")
    )

    write_json(run_dir / "intent_result.json", intent_result)
    write_json(run_dir / "ir.json", ir)
    write_json(run_dir / "grounded_ir.json", grounded_ir)
    write_json(run_dir / "generation_plan.json", generation_plan)
    write_json(run_dir / "script_generation.json", script_generation)
    write_json(run_dir / "static_before.json", static_before)
    write_json(run_dir / "static_after.json", final_static)
    write_json(run_dir / "final_execution_plan.json", final_execution_plan)

    substance = assess_script_substance(final_script_path.read_text(encoding="utf-8-sig"))
    if "execution_result" in script_generation:
        initial_static_pass = bool(script_generation["static_analysis"].get("static_pass", static_before["static_pass"]))
    else:
        initial_static_pass = bool(script_generation.get("attempts", [{}])[0].get("static_analysis", {}).get("static_pass", static_before["static_pass"]))
    final_blocker = ""
    if final_mission_status != "PASS":
        final_blocker = extract_failure_family(final_static, final_execution_plan)
    elif not final_static["static_pass"]:
        final_blocker = final_static.get("primary_error", "")

    summary = {
        "task_id": task["id"],
        "input": task["input"],
        "intent_attempt_count": intent_result["attempt_count"],
        "ir_valid": True,
        "grounding_unresolved_count": grounding_state["unresolved_count"],
        "generation_mode": script_generation["generator_mode"],
        "initial_static_pass": initial_static_pass,
        "llm_static_repair_triggered": llm_static_repair_result is not None,
        "static_repair_mode": llm_static_repair_result.get("mode", "") if llm_static_repair_result else "",
        "layer_regeneration_triggered": layer_regeneration_triggered,
        "layer_regeneration_static_pass": layer_regeneration_static_pass,
        "final_static_pass": final_static["static_pass"],
        "mission_status": final_mission_status,
        "primary_root_cause": primary_root_cause,
        "final_blocker": final_blocker,
        "repair_drift_detected": repair_drift["detected"],
        "repair_drift_stage": repair_drift["stage"],
        "repair_drift_action": repair_drift["action"],
        "repair_drift_baseline_family": repair_drift["baseline_family"],
        "repair_drift_candidate_family": repair_drift["candidate_family"],
        "llm_execution_repair_triggered": llm_execution_repair_result is not None,
        "execution_route": final_execution_plan["repair_recommendation"]["route"],
        "llm_only_script_selected": True,
        "llm_only_pass": final_mission_status == "PASS",
        "final_script": str(final_script_path.relative_to(ROOT)),
        "final_return_code": final_return_code,
        "effective_line_count": substance["effective_line_count"],
        "has_platform_or_type": substance["has_platform_or_type"],
        "has_route_or_position": substance["has_route_or_position"],
        "core_block_count": substance["core_block_count"],
        "empty_shell": substance["empty_shell"],
        "substantive_pass": bool(final_mission_status == "PASS" and final_static["static_pass"] and substance["substantive_ready"]),
        "reused_existing": False,
    }
    write_json(run_dir / "task_summary.json", summary)
    return summary


def to_results_row(task_summary: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    final_static_path = run_dir / "static_after.json"
    final_static = json.loads(final_static_path.read_text(encoding="utf-8-sig"))
    final_script_path = ROOT / task_summary["final_script"]
    final_script_text = final_script_path.read_text(encoding="utf-8-sig")

    repair_attempted = bool(
        task_summary["llm_static_repair_triggered"] or task_summary["llm_execution_repair_triggered"]
    )
    repair_success = task_summary["mission_status"] == "PASS" if repair_attempted else None
    semantic_ok = semantic_match(
        {"input": task_summary["input"], "covered_components": load_benchmark_index()[task_summary["task_id"]].get("covered_components", [])},
        final_script_text,
        task_summary["mission_status"],
    )

    row = {
        "id": task_summary["task_id"],
        "input": task_summary["input"],
        "generated_script": task_summary["final_script"].replace("\\", "/"),
        "syntax_correct": final_static["syntax_correct"],
        "static_pass": final_static["static_pass"],
        "static_errors": final_static["findings"],
        "static_error_ids": final_static["static_error_ids"],
        "mission_status": task_summary["mission_status"],
        "return_code": task_summary["final_return_code"],
        "mission_log": f"afsim_agent_v2/{task_summary['task_id']}/mission_final.log",
        "primary_error": final_static["primary_error"],
        "primary_root_cause": task_summary.get("primary_root_cause", ""),
        "final_blocker": task_summary.get("final_blocker", ""),
        "repair_drift_detected": task_summary.get("repair_drift_detected", False),
        "repair_drift_stage": task_summary.get("repair_drift_stage", ""),
        "secondary_errors": final_static["static_error_ids"][1:],
        "semantic_match": semantic_ok,
        "ir_valid": task_summary["ir_valid"],
        "effective_line_count": task_summary.get("effective_line_count", 0),
        "empty_shell": task_summary.get("empty_shell", False),
        "substantive_pass": task_summary.get("substantive_pass", False),
        "reused_existing": task_summary.get("reused_existing", False),
    }
    if repair_success is not None:
        row["repair_success"] = repair_success
    return row


def write_readme(task_summaries: list[dict[str, Any]], model: str) -> None:
    lines = [
        "# AFSIM Agent v2",
        "",
        "LLM-only evaluation pipeline - no deterministic scaffold, demo copy, or IR postprocess fallback.",
        "",
        "## Workflow",
        "",
        "- Natural Language",
        "- LLM Intent Parsing",
        "- AFSIM-IR Schema Validation",
        "- Grounding",
        "- Hierarchical Generation Plan",
        "- LLM Script Generation",
        "- Static Verification",
        "- LLM Static Repair",
        "- mission.exe",
        "- LLM Execution Repair",
        "",
        "## Results",
        "",
        f"- model: `{model}`",
        "",
    ]
    for row in task_summaries:
        lines.append(
            f"- `{row['task_id']}`: initial_static_pass={row['initial_static_pass']}, "
            f"final_static_pass={row['final_static_pass']}, mission_status={row['mission_status']}, "
            f"generation_mode={row['generation_mode']}, llm_static_repair={row['llm_static_repair_triggered']}, "
            f"layer_regeneration={row.get('layer_regeneration_triggered', False)}, "
            f"llm_execution_repair={row['llm_execution_repair_triggered']}"
        )
    lines.append("")
    (OUTPUT_ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-only AFSIM Agent v2 on benchmark tasks.")
    parser.add_argument("--task-ids", nargs="*", default=DEFAULT_TASK_IDS, help="Benchmark task ids to run.")
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--max-intent-attempts", type=int, default=2)
    parser.add_argument("--max-generation-attempts", type=int, default=1)
    parser.add_argument("--rerun-completed", action="store_true", help="Ignore cached task_summary.json files and rerun completed tasks.")
    parser.add_argument("--max-workers", type=int, default=4, help="Max parallel workers for task execution.")
    args = parser.parse_args()

    benchmark_index = load_benchmark_index()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for task_id in args.task_ids:
        if task_id not in benchmark_index:
            raise SystemExit(f"Unknown benchmark task id: {task_id}")

    # Only require API key when at least one task needs LLM generation.
    needs_llm = args.rerun_completed or any(
        not has_reusable_summary(task_id) for task_id in args.task_ids
    )
    client = LLMClient.from_env(model=args.model) if needs_llm else None

    def _run_one(task_id: str) -> dict[str, Any]:
        return run_task(
            benchmark_index[task_id],
            client,
            max_intent_attempts=args.max_intent_attempts,
            max_generation_attempts=args.max_generation_attempts,
            rerun_completed=args.rerun_completed,
        )

    task_summaries: list[dict[str, Any]] = []
    if args.max_workers <= 1:
        for task_id in args.task_ids:
            task_summaries.append(_run_one(task_id))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(_run_one, task_id): task_id for task_id in args.task_ids}
            for future in as_completed(futures):
                task_summaries.append(future.result())

    model_label = client.model if client is not None else (args.model or "cached_only")
    overall = {
        "name": "full_agent_v2",
        "version": "afsim_agent_v2",
        "mode": "llm_only",
        "benchmark_dir": "benchmarks/benchmark_v1",
        "model": model_label,
        "task_ids": args.task_ids,
        "total": len(task_summaries),
        "counts": {
            "total": len(task_summaries),
            "ir_valid": sum(1 for row in task_summaries if row["ir_valid"]),
            "initial_static_pass": sum(1 for row in task_summaries if row["initial_static_pass"]),
            "final_static_pass": sum(1 for row in task_summaries if row["final_static_pass"]),
            "mission_pass": sum(1 for row in task_summaries if row["mission_status"] == "PASS"),
            "substantive_pass": sum(1 for row in task_summaries if row.get("substantive_pass")),
            "empty_shell_pass": sum(1 for row in task_summaries if row["mission_status"] == "PASS" and row.get("empty_shell")),
            "llm_only_pass": sum(1 for row in task_summaries if row["llm_only_pass"]),
            "llm_static_repair_triggered": sum(1 for row in task_summaries if row["llm_static_repair_triggered"]),
            "layer_regeneration_triggered": sum(1 for row in task_summaries if row.get("layer_regeneration_triggered")),
            "layer_regeneration_static_pass": sum(1 for row in task_summaries if row.get("layer_regeneration_static_pass")),
            "llm_execution_repair_triggered": sum(1 for row in task_summaries if row["llm_execution_repair_triggered"]),
            "reused_existing": sum(1 for row in task_summaries if row.get("reused_existing")),
        },
        "tasks": task_summaries,
    }
    results_rows = [to_results_row(row, OUTPUT_ROOT / row["task_id"]) for row in task_summaries]
    semantic_true = sum(1 for row in results_rows if row["semantic_match"])
    substantive_true = sum(1 for row in results_rows if row.get("substantive_pass"))
    repair_values = [row["repair_success"] for row in results_rows if isinstance(row.get("repair_success"), bool)]
    overall["ir_validity_rate"] = round(overall["counts"]["ir_valid"] / len(task_summaries), 4) if task_summaries else 0.0
    overall["semantic_match_rate"] = round(semantic_true / len(results_rows), 4) if results_rows else 0.0
    overall["substantive_pass_rate"] = round(substantive_true / len(results_rows), 4) if results_rows else 0.0
    overall["repair_success_rate"] = round(sum(1 for value in repair_values if value) / len(repair_values), 4) if repair_values else None
    overall["mission_success_rate"] = round(overall["counts"]["mission_pass"] / len(task_summaries), 4) if task_summaries else 0.0
    overall["syntax_correct_rate"] = round(sum(1 for row in results_rows if row["syntax_correct"]) / len(results_rows), 4) if results_rows else 0.0
    overall["static_pass_rate"] = round(sum(1 for row in results_rows if row["static_pass"]) / len(results_rows), 4) if results_rows else 0.0
    merged_results = merge_results_rows(OUTPUT_ROOT / "results.jsonl", results_rows)
    write_jsonl(OUTPUT_ROOT / "results.jsonl", merged_results)
    write_json(OUTPUT_ROOT / "summary.json", overall)
    write_readme(task_summaries, model_label)
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
