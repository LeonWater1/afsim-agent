#!/usr/bin/env python3
"""
Task-014: Execution Repair Workflow v1

Analyze mission.exe feedback and turn it into a structured execution-repair plan.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from run_mission import run_mission
from static_checker_v1 import analyze_script_text


ROOT = Path(__file__).resolve().parent.parent

VALIDATION_CASES = [
    {
        "name": "pass_without_errors",
        "log_text": "",
        "return_code": 0,
        "static_analysis": {"primary_error": ""},
        "expected": {"mission_pass": True, "route": "no_repair_needed"},
    },
    {
        "name": "environment_missing_include",
        "log_text": "FATAL: Cannot open file: _common.aer",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E009", "route": "fix_execution_environment"},
    },
    {
        "name": "script_compile_error",
        "log_text": "ERROR: Unable to compile script\nERROR: Void' script cannot return a value",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E008", "route": "return_to_script_logic_repair"},
    },
    {
        "name": "grounding_failure_from_runtime",
        "log_text": "ERROR: could not find mover",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E005", "route": "return_to_grounding"},
    },
    {
        "name": "weapon_profile_missing_from_runtime",
        "log_text": "ERROR: Could not find weapon WSF_AIR_TO_AIR_MISSILE",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E005", "route": "return_to_grounding"},
    },
    {
        "name": "fallback_to_static",
        "log_text": "ERROR: unknown command: processorx",
        "return_code": 1,
        "static_analysis": {"primary_error": "E007"},
        "expected": {"primary_error": "E007", "route": "return_to_layer_regeneration"},
    },
    {
        "name": "unknown_command_without_static_precursor",
        "log_text": "ERROR: unknown command: processorx",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E007", "route": "return_to_layer_regeneration"},
    },
    {
        "name": "context_forbidden_keyword",
        "log_text": "ERROR: 'mode' cannot be used in this context",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E007", "route": "return_to_layer_regeneration"},
    },
    {
        "name": "behavior_reference_missing",
        "log_text": "ERROR: Could not find behavior planned_route",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E003", "route": "return_to_grounding_or_ir"},
    },
    {
        "name": "unexpected_end_of_data",
        "log_text": "ERROR: Unexpected End Of Data",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E002", "route": "return_to_self_repair"},
    },
    {
        "name": "brawler_component_requirement",
        "log_text": "ERROR: WSF_BRAWLER_PLATFORM must have a WSF_BRAWLER_MOVER defined!",
        "return_code": 1,
        "static_analysis": {"primary_error": ""},
        "expected": {"primary_error": "E006", "route": "return_to_layer_regeneration"},
    },
]


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def classify_from_static(static_analysis: dict) -> dict:
    primary = static_analysis.get("primary_error", "")
    if not primary:
        return {
            "primary_error": "",
            "route": "manual_review",
            "suggested_action": "inspect execution feedback manually",
        }

    routes = {
        "E001": ("return_to_self_repair", "fill missing units and rerun static verification before mission.exe"),
        "E002": ("return_to_self_repair", "repair block structure and closing tags before mission.exe"),
        "E003": ("return_to_grounding_or_ir", "repair unresolved references from grounded IR before rerun"),
        "E004": ("return_to_ir", "normalize coordinates from IR and regenerate the affected lines"),
        "E005": ("return_to_grounding", "replace hallucinated or unsupported entities through grounding"),
        "E006": ("return_to_self_repair", "fill missing required fields from IR or template"),
        "E007": ("return_to_layer_regeneration", "regenerate the affected layer or component template"),
        "E008": ("return_to_script_logic_repair", "rewrite unsupported script logic or API usage"),
    }
    route, action = routes.get(primary, ("manual_review", "inspect the execution failure manually"))
    return {"primary_error": primary, "route": route, "suggested_action": action}


def extract_error_lines(log_text: str) -> list[str]:
    lines = []
    for raw in log_text.splitlines():
        line = raw.strip()
        if "ERROR:" in line or "FATAL:" in line:
            lines.append(line)
    return lines


def build_rerun_preconditions(execution_analysis: dict) -> list[str]:
    route = execution_analysis["route"]
    stage = execution_analysis["inferred_stage"]
    preconditions = ["apply the recommended repair at the routed stage"]

    if route == "no_repair_needed":
        return ["no repair required"]

    if route == "fix_execution_environment":
        preconditions.append(
            "verify mission.exe path, mirrored workspace, dependent include files, and writable output directories"
        )
    elif route in {"return_to_self_repair", "return_to_script_logic_repair", "return_to_layer_regeneration"}:
        preconditions.append("rerun static_checker_v1 after the repair changes the script text")
    elif route in {"return_to_grounding", "return_to_grounding_or_ir"}:
        preconditions.append("refresh grounding outputs before regenerating the affected block or layer")
    elif route == "return_to_ir":
        preconditions.append("regenerate downstream artifacts from the corrected IR before rerun")

    if stage in {"mission_layer", "component_generation", "static_or_generation"}:
        preconditions.append("rerun mission.exe only after the regenerated script passes static verification")

    return preconditions


def classify_execution(log_text: str, static_analysis: dict, return_code: int | None) -> dict:
    error_lines = extract_error_lines(log_text)
    primary_error = ""
    classifier = "unknown_failure"
    route = "manual_review"
    suggested_action = "inspect mission log and rerun manually"
    stage = "execution"

    def has(pattern: str) -> bool:
        return re.search(pattern, log_text, re.IGNORECASE) is not None

    if return_code == 0 and not error_lines:
        return {
            "mission_pass": True,
            "primary_error": "",
            "classifier": "pass",
            "route": "no_repair_needed",
            "inferred_stage": "none",
            "suggested_action": "mission execution passed",
            "evidence_lines": [],
        }

    if has(r"mission\.exe not found|cannot open file:|terrain directory does not exist|permission denied|add failed"):
        primary_error = "E009"
        classifier = "environment_or_dependency_error"
        route = "fix_execution_environment"
        stage = "execution_environment"
        suggested_action = (
            "run from a mirrored writable directory, ensure dependent include/terrain files exist, "
            "and rerun mission.exe with a resolved absolute script path"
        )
    elif has(r"unable to compile script|error in script|method '.*' does not exist|unknown identifier|invalid method call|';' expected|void' script cannot return a value"):
        primary_error = "E008"
        classifier = "script_compile_or_api_error"
        route = "return_to_script_logic_repair"
        stage = "mission_layer"
        suggested_action = "rewrite processor or script blocks using verified API and rerun static + mission verification"
    elif has(r"unknown command:"):
        static_route = classify_from_static(static_analysis)
        classifier = "input_parse_or_structure_error"
        stage = "static_or_generation"
        if static_route["primary_error"]:
            primary_error = static_route["primary_error"]
            route = static_route["route"]
            suggested_action = static_route["suggested_action"]
        else:
            primary_error = "E007"
            route = "return_to_layer_regeneration"
            suggested_action = "regenerate the affected layer or component template"
    elif has(r"cannot be used in this context"):
        primary_error = "E007"
        classifier = "context_forbidden_keyword"
        route = "return_to_layer_regeneration"
        stage = "static_or_generation"
        suggested_action = "remove the context-forbidden command and regenerate the affected block with verified syntax"
    elif has(r"could not find comm|unknown comm"):
        primary_error = "E003"
        classifier = "missing_comm_definition_or_reference"
        route = "return_to_grounding_or_ir"
        stage = "mission_layer"
        suggested_action = "define the referenced comm/network type in the self-contained script or regenerate the communication layer from grounded IR"
    elif has(r"could not find behavior"):
        primary_error = "E003"
        classifier = "missing_behavior_definition"
        route = "return_to_grounding_or_ir"
        stage = "mission_layer"
        suggested_action = "define the referenced advanced_behavior in the self-contained script or remove the unsupported behavior-tree reference"
    elif has(r"unexpected end of data"):
        primary_error = "E002"
        classifier = "unterminated_custom_block"
        route = "return_to_self_repair"
        stage = "static_or_generation"
        suggested_action = "close every opened custom block and nested table explicitly before rerunning mission.exe"
    elif has(r"could not find mover|could not find weapon"):
        primary_error = "E005"
        classifier = "ungrounded_component_type"
        route = "return_to_grounding"
        stage = "grounding"
        suggested_action = "replace the unresolved mover, weapon, or component type with a verified grounded target"
    elif has(r"bad value for:"):
        primary_error = "E006"
        classifier = "invalid_required_value"
        route = "return_to_ir"
        stage = "ir_or_generation"
        suggested_action = "repair the invalid parameter value from IR or regenerate the affected block"
    elif has(r"expected value '.*' to be > 0"):
        primary_error = "E001"
        classifier = "invalid_positive_numeric_value"
        route = "return_to_self_repair"
        stage = "static_or_generation"
        suggested_action = "replace zero or negative physical parameters that must be positive and rerun static verification"
    elif has(r"wsf_brawler_platform must have a wsf_brawler_mover|wsf_brawler_platform must have a wsf_threat_processor"):
        primary_error = "E006"
        classifier = "missing_brawler_required_components"
        route = "return_to_layer_regeneration"
        stage = "component_generation"
        suggested_action = "when using a Brawler family platform, include the verified Brawler mover and threat processor pattern rather than approximating with generic air-platform components"
    elif has(r"no .* defined|failed phase one initialization|initialization of simulation failed"):
        primary_error = "E006"
        classifier = "missing_required_component_or_initialization"
        route = "return_to_layer_regeneration"
        stage = "component_generation"
        suggested_action = "add the required supporting component or regenerate the affected component template"
    else:
        static_route = classify_from_static(static_analysis)
        if static_route["primary_error"]:
            primary_error = static_route["primary_error"]
            classifier = "execution_failure_with_static_precursor"
            route = static_route["route"]
            stage = "static_or_generation"
            suggested_action = static_route["suggested_action"]

    return {
        "mission_pass": False,
        "primary_error": primary_error,
        "classifier": classifier,
        "route": route,
        "inferred_stage": stage,
        "suggested_action": suggested_action,
        "evidence_lines": error_lines[:8],
    }


def build_execution_repair_plan(
    script_path: Path,
    mission_status: str,
    return_code: int | None,
    log_text: str,
    static_analysis: dict,
) -> dict:
    execution_analysis = classify_execution(log_text, static_analysis, return_code)
    return {
        "version": "execution_repair_spec_v1",
        "input": {
            "script_path": str(script_path),
            "mission_status": mission_status,
            "return_code": return_code,
        },
        "static_analysis": static_analysis,
        "execution_analysis": execution_analysis,
        "repair_recommendation": {
            "primary_error": execution_analysis["primary_error"],
            "route": execution_analysis["route"],
            "inferred_stage": execution_analysis["inferred_stage"],
            "suggested_action": execution_analysis["suggested_action"],
        },
        "rerun_plan": {
            "preconditions": build_rerun_preconditions(execution_analysis),
            "command_hint": f"python scripts/run_mission.py -es -fio {script_path}",
            "success_condition": "mission_status == PASS",
        },
    }


def run_validation_suite() -> dict:
    cases = []
    passed = 0
    for case in VALIDATION_CASES:
        actual = classify_execution(case["log_text"], case["static_analysis"], case["return_code"])
        failures = []
        for key, expected_value in case["expected"].items():
            if actual.get(key) != expected_value:
                failures.append(
                    {
                        "field": key,
                        "expected": expected_value,
                        "actual": actual.get(key),
                    }
                )
        ok = not failures
        if ok:
            passed += 1
        cases.append(
            {
                "name": case["name"],
                "ok": ok,
                "expected": case["expected"],
                "actual": actual,
                "failures": failures,
            }
        )
    return {
        "suite": "execution_repair_planner_v1",
        "passed": passed,
        "total": len(cases),
        "all_passed": passed == len(cases),
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description="Build execution-repair plan from mission.exe feedback.")
    parser.add_argument("--script", help="Path to target script.")
    parser.add_argument("--run", action="store_true", help="Run mission.exe before analysis.")
    parser.add_argument("--mission-log", help="Existing mission log file to analyze instead of live run.")
    parser.add_argument("--output", help="Output JSON path.")
    parser.add_argument("--write-mission-log", help="Optional path to write captured mission output.")
    parser.add_argument("--validate", action="store_true", help="Run built-in classifier validation cases.")
    args = parser.parse_args()

    if args.validate:
        payload = json.dumps(run_validation_suite(), ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return

    if not args.script:
        parser.error("--script is required unless --validate is used")

    script_path = Path(args.script).resolve()
    static_analysis = analyze_script_text(load_text(script_path), script_label=str(script_path))

    mission_status = "NOT_RUN"
    return_code = None
    log_text = ""

    if args.run:
        return_code, stdout, stderr = run_mission(str(script_path), options=["-es", "-fio"])
        log_text = "\n".join(part for part in [stdout, stderr] if part)
        mission_status = "PASS" if return_code == 0 and "FATAL:" not in log_text else "FAIL"
    elif args.mission_log:
        log_text = load_text(Path(args.mission_log))
        mission_status = "PASS" if "FATAL:" not in log_text and "ERROR:" not in log_text else "FAIL"

    if args.write_mission_log and log_text:
        Path(args.write_mission_log).write_text(log_text, encoding="utf-8")

    plan = build_execution_repair_plan(script_path, mission_status, return_code, log_text, static_analysis)
    payload = json.dumps(plan, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
