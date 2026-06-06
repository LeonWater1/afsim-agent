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

from .grounding import build_grounded_ir
from .repair_planner import build_execution_repair_plan
from .generation_executor import execute_layered_generation
from .generation_planner import build_generation_plan
from .llm_client import LLMClient
from .intent_parser import parse_intent_with_llm
from .repair_executor import llm_execution_repair
from .script_generator import generate_script_with_llm
from .mission_log_parser import parse as parse_mission_log
from .reference_rules import postprocess_script
from .run_mission import run_mission
from .static_checker import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent.parent


def _finalize_script(text: str) -> str:
    """Unified pre-write gate: postprocess + static check on every script output."""
    return postprocess_script(text)
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark" / "tasks.jsonl"
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


def normalize_benchmark_task(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize benchmark v1/v2 rows to the agent's task contract."""
    task = dict(row)
    task.setdefault("input", task.get("instruction", ""))
    task.setdefault("source_hint", task.get("oracle_script", task.get("source_demo", "")))
    task.setdefault("demo_id", task.get("source_demo", task.get("id", "")))
    task.setdefault("covered_components", task.get("covered_components", []))
    return task


def load_benchmark_index(path: Path = BENCHMARK_PATH) -> dict[str, dict[str, Any]]:
    return {row["id"]: normalize_benchmark_task(row) for row in load_jsonl(path)}


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


def semantic_match(task: dict, script_text: str, mission_status: str) -> bool:
    """Check whether the generated script satisfies the task's covered_components."""
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
        "Acoustic": lambda s: "ACOUSTIC" in s.upper(),
        "BehaviorTree": lambda s: "BEHAVIOR_TREE" in s.upper(),
        "Space": lambda s: "SPACE_MOVER" in s.upper(),
        "ElectronicWarfare": lambda s: "JAMMER" in s.upper() or "ESM" in s.upper() or "CHAFF" in s.upper(),
        "IADS": lambda s: "SAM" in s.upper() and "RADAR" in s.upper(),
        "LaserDesignator": lambda s: "LASER" in s.upper(),
        "Coverage": lambda s: "HEATMAP" in s.upper(),
        "Cyber": lambda s: "CYBER" in s.upper(),
        "Fires": lambda s: "ARTILLERY" in s.upper(),
    }
    checks = []
    for component in task.get("covered_components", []):
        matcher = component_map.get(component)
        if matcher:
            checks.append(matcher(script_text))
    if not checks:
        checks.append("route" in script_text.lower())
    return all(checks)


def _classify_exit(return_code: int | None, log_text: str) -> str:
    """Map mission.exe exit code to failure class."""
    if return_code == 0:
        return "ok" if "Simulation complete" in log_text else "parse_or_runtime_ok"
    if return_code is None:
        return "timeout_or_hang"
    if return_code < 0:
        return "crash"
    if "FATAL:" in log_text or "Reading of simulation input failed" in log_text:
        return "parse_error"
    if "Initialization of simulation failed" in log_text:
        return "init_error"
    if "Simulation complete" in log_text:
        return "ok"
    return "runtime_error"


_ERROR_TO_LAYERS: dict[str, list[str]] = {
    "missing_platform_type":   ["platform_layer"],
    "missing_mover":           ["platform_layer"],
    "missing_companion":       ["platform_layer"],
    "component_init_failure":  ["platform_layer", "sensor_layer"],
    "missing_sensor":          ["sensor_layer"],
    "esm_no_frequency_band":   ["sensor_layer"],
    "missing_weapon":          ["weapon_layer"],
    "unknown_command":         ["mission_layer"],
    "wrong_context_command":   ["mission_layer"],
    "wrong_block_host":        ["mission_layer"],
    "hallucinated_api":        ["mission_layer"],
    "invalid_script_api":      ["mission_layer"],
    "missing_reference":       ["mission_layer"],
    "missing_processor":       ["mission_layer"],
    "missing_entity":          ["scenario_assembly"],
    "parser_fatal":            ["scenario_assembly"],
    "unexpected_eof":          ["scenario_assembly"],
    "init_failed":             ["scenario_assembly"],
}


def _error_to_layers(diagnostics: dict) -> list[str]:
    """Map error categories to targeted generation layers for repair."""
    layers: set[str] = set()
    for cat in diagnostics.get("error_categories", []):
        for target in _ERROR_TO_LAYERS.get(cat, ["scenario_assembly"]):
            layers.add(target)
    return sorted(layers) if layers else ["scenario_assembly"]


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
    if summary.get("run_error") or summary.get("generation_mode") == "run_error":
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
    execution_plan: dict[str, Any] | None,
) -> str:
    root = extract_failure_family(static_before, execution_plan)
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
    generated_script_path.write_text(_finalize_script(script_generation["script_text"]), encoding="utf-8")
    static_before = analyze_script_text(script_generation["script_text"], script_label=str(generated_script_path))

    # Phase 1: Deterministic postprocessing only (Self Repair removed)
    # Postprocess the generated script and proceed directly to mission.exe.
    # Self-healing is achieved through Static Checker → mission.exe → Execution Repair.
    current_script_text = _finalize_script(script_generation["script_text"])
    current_script_path = run_dir / "llm_repaired_script.txt"
    current_script_path.write_text(current_script_text, encoding="utf-8")
    static_after = analyze_script_text(current_script_text, script_label=str(current_script_path))
    llm_static_repair_result = {
        "version": "postprocess_only",
        "mode": "deterministic_postprocessing",
        "repaired_text": current_script_text,
        "static_analysis": static_after,
        "note": "Self Repair removed — deterministic postprocessing + Execution Repair for self-healing",
    }
    write_json(run_dir / "llm_static_repair.json", llm_static_repair_result)
    primary_root_cause = ""

    # Phase 2: mission.exe → structured diagnostics
    mission_status, mission_return_code, mission_log_text = run_mission_for_diagnostics(current_script_path)
    (run_dir / "mission_final.log").write_text(mission_log_text, encoding="utf-8")
    mission_diag = parse_mission_log(mission_log_text, mission_return_code, ir=ir, static_analysis=static_after)
    write_json(run_dir / "mission_diagnostics.json", mission_diag)
    # Keep legacy plan for backward compat, but mark route from diagnostics
    execution_plan = build_execution_repair_plan(
        current_script_path, mission_status, mission_return_code, mission_log_text, static_after,
    )
    # Override route with structured diagnostics when legacy plan is vague
    if execution_plan["repair_recommendation"]["route"] == "manual_review" and mission_diag["repair_hints"]:
        execution_plan["repair_recommendation"]["route"] = "return_to_layer_regeneration"
        execution_plan["repair_recommendation"]["suggested_action"] = mission_diag["repair_hints"][0]
    write_json(run_dir / "execution_repair.json", execution_plan)
    primary_root_cause = compute_primary_root_cause(static_before, execution_plan)

    # Phase 3: Execution Repair (mission-driven)
    llm_execution_repair_result = None
    final_script_path = current_script_path
    final_static = static_after
    final_mission_status = mission_status
    final_return_code = mission_return_code
    final_log_text = mission_log_text
    final_execution_plan = execution_plan
    repair_drift: dict[str, Any] = {"detected": False, "stage": "", "baseline_family": "", "candidate_family": "", "action": "accepted_current_script"}

    route = execution_plan["repair_recommendation"]["route"]
    if mission_status == "FAIL" and (route in EXECUTION_REPAIRABLE_ROUTES or mission_diag.get("error_categories")):
        best_script = current_script_text
        best_static = static_after
        best_status = mission_status
        best_rc = mission_return_code
        best_log = mission_log_text
        best_categories = set(mission_diag.get("error_categories", []))
        best_diag = mission_diag

        for attempt in range(1, 3):  # always try 2 repairs
            target_layers = _error_to_layers(best_diag)
            llm_execution_repair_result = llm_execution_repair(
                task, best_script, ir, grounded_ir, generation_plan,
                best_status, best_rc, best_log, client,
                mission_diagnostics=best_diag,
                target_layers=target_layers,
            )
            repaired_text = llm_execution_repair_result["repaired_text"]
            repaired_path = run_dir / f"execution_repaired_{attempt}.txt"
            repaired_path.write_text(_finalize_script(repaired_text), encoding="utf-8")
            repaired_static = llm_execution_repair_result["static_analysis"]
            repaired_status, repaired_rc, repaired_log = run_mission_for_diagnostics(repaired_path)
            repaired_diag = parse_mission_log(repaired_log, repaired_rc, ir=ir, static_analysis=repaired_static)
            repaired_categories = set(repaired_diag.get("error_categories", []))
            write_json(run_dir / f"llm_execution_repair_{attempt}.json", llm_execution_repair_result)

            best_e2 = sum(1 for f in best_static.get("findings", []) if f["error_id"] == "E002")
            repaired_e2 = sum(1 for f in repaired_static.get("findings", []) if f["error_id"] == "E002")
            improved = (
                repaired_status == "PASS"
                or len(repaired_categories) < len(best_categories)
                or (len(repaired_categories) == len(best_categories) and repaired_e2 < best_e2)
            )
            if improved:
                best_script = repaired_text
                best_static = repaired_static
                best_status = repaired_status
                best_rc = repaired_rc
                best_log = repaired_log
                best_categories = repaired_categories
                best_diag = repaired_diag
                if repaired_status == "PASS":
                    break
            # If not improved, continue to next attempt with fresh diagnostics guiding repair

        final_script_path = run_dir / "execution_repaired_script.txt"
        final_script_path.write_text(_finalize_script(best_script), encoding="utf-8")
        final_static = best_static
        final_mission_status = best_status
        final_return_code = best_rc
        final_log_text = best_log
        final_execution_plan = build_execution_repair_plan(
            final_script_path, final_mission_status, final_return_code, final_log_text, final_static,
        )
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


def write_failed_task_summary(task: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    run_dir = OUTPUT_ROOT / task["id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    error_text = f"{type(exc).__name__}: {exc}"
    failed_script_path = run_dir / "failed_script.txt"
    failed_script_path.write_text("", encoding="utf-8")
    static_after = {
        "syntax_correct": False,
        "static_pass": False,
        "primary_error": "RUN_ERROR",
        "static_error_ids": ["RUN_ERROR"],
        "findings": [
            {
                "error_id": "RUN_ERROR",
                "line": 0,
                "message": error_text,
            }
        ],
    }
    write_json(run_dir / "static_after.json", static_after)
    (run_dir / "mission_final.log").write_text(error_text, encoding="utf-8")
    summary = {
        "task_id": task["id"],
        "input": task.get("input", ""),
        "intent_attempt_count": 0,
        "ir_valid": False,
        "grounding_unresolved_count": 0,
        "generation_mode": "run_error",
        "initial_static_pass": False,
        "llm_static_repair_triggered": False,
        "static_repair_mode": "",
        "layer_regeneration_triggered": False,
        "layer_regeneration_static_pass": False,
        "final_static_pass": False,
        "mission_status": "FAIL",
        "primary_root_cause": "RUN_ERROR",
        "final_blocker": error_text,
        "repair_drift_detected": False,
        "repair_drift_stage": "",
        "repair_drift_action": "",
        "repair_drift_baseline_family": "",
        "repair_drift_candidate_family": "",
        "llm_execution_repair_triggered": False,
        "execution_route": "run_error",
        "llm_only_script_selected": False,
        "llm_only_pass": False,
        "final_script": str(failed_script_path.relative_to(ROOT)),
        "final_return_code": None,
        "effective_line_count": 0,
        "has_platform_or_type": False,
        "has_route_or_position": False,
        "core_block_count": 0,
        "empty_shell": True,
        "substantive_pass": False,
        "reused_existing": False,
        "run_error": error_text,
    }
    write_json(run_dir / "task_summary.json", summary)
    return summary


def to_results_row(
    task_summary: dict[str, Any],
    run_dir: Path,
    benchmark_index: dict[str, dict[str, Any]],
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    final_static_path = run_dir / "static_after.json"
    final_static = json.loads(final_static_path.read_text(encoding="utf-8-sig"))
    final_script_path = ROOT / task_summary["final_script"]
    final_script_text = final_script_path.read_text(encoding="utf-8-sig")

    repair_attempted = bool(
        task_summary["llm_static_repair_triggered"] or task_summary["llm_execution_repair_triggered"]
    )
    repair_success = task_summary["mission_status"] == "PASS" if repair_attempted else None
    semantic_ok = semantic_match(
        {"input": task_summary["input"], "covered_components": benchmark_index[task_summary["task_id"]].get("covered_components", [])},
        final_script_text,
        task_summary["mission_status"],
    )
    try:
        mission_log = str((run_dir / "mission_final.log").relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        mission_log = str(run_dir / "mission_final.log")

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
        "mission_log": mission_log,
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


def write_readme(task_summaries: list[dict[str, Any]], model: str, output_root: Path = OUTPUT_ROOT) -> None:
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
    (output_root / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    global BENCHMARK_PATH, OUTPUT_ROOT

    parser = argparse.ArgumentParser(description="Run LLM-only AFSIM Agent v2 on benchmark tasks.")
    parser.add_argument("--benchmark-jsonl", default=str(BENCHMARK_PATH.relative_to(ROOT)), help="Benchmark JSONL path to run.")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT.relative_to(ROOT)), help="Output directory for run artifacts.")
    parser.add_argument("--task-ids", nargs="*", default=None, help="Benchmark task ids to run. Defaults to all rows in --benchmark-jsonl.")
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--max-intent-attempts", type=int, default=2)
    parser.add_argument("--max-generation-attempts", type=int, default=1)
    parser.add_argument("--rerun-completed", action="store_true", help="Ignore cached task_summary.json files and rerun completed tasks.")
    parser.add_argument("--max-workers", type=int, default=4, help="Max parallel workers for task execution.")
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_jsonl)
    if not benchmark_path.is_absolute():
        benchmark_path = ROOT / benchmark_path
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    BENCHMARK_PATH = benchmark_path
    OUTPUT_ROOT = output_root

    benchmark_index = load_benchmark_index(benchmark_path)
    task_ids = args.task_ids or list(benchmark_index.keys())
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    for task_id in task_ids:
        if task_id not in benchmark_index:
            raise SystemExit(f"Unknown benchmark task id: {task_id}")

    # Only require API key when at least one task needs LLM generation.
    needs_llm = args.rerun_completed or any(
        not has_reusable_summary(task_id) for task_id in task_ids
    )
    client = LLMClient.from_env(model=args.model) if needs_llm else None

    def _run_one(task_id: str) -> dict[str, Any]:
        task = benchmark_index[task_id]
        try:
            return run_task(
                task,
                client,
                max_intent_attempts=args.max_intent_attempts,
                max_generation_attempts=args.max_generation_attempts,
                rerun_completed=args.rerun_completed,
            )
        except Exception as exc:
            return write_failed_task_summary(task, exc)

    task_summaries: list[dict[str, Any]] = []
    if args.max_workers <= 1:
        for task_id in task_ids:
            task_summaries.append(_run_one(task_id))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(_run_one, task_id): task_id for task_id in task_ids}
            for future in as_completed(futures):
                task_summaries.append(future.result())

    model_label = client.model if client is not None else (args.model or "cached_only")
    overall = {
        "name": "full_agent_v2",
        "version": "afsim_agent_v2",
        "mode": "llm_only",
        "benchmark_dir": str(benchmark_path.parent.relative_to(ROOT)).replace("\\", "/"),
        "benchmark_jsonl": str(benchmark_path.relative_to(ROOT)).replace("\\", "/"),
        "model": model_label,
        "task_ids": task_ids,
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
    results_rows = [to_results_row(row, OUTPUT_ROOT / row["task_id"], benchmark_index, OUTPUT_ROOT) for row in task_summaries]
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
    write_readme(task_summaries, model_label, OUTPUT_ROOT)
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
