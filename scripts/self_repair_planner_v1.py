#!/usr/bin/env python3
"""
Task-012: Self Repair Workflow v1

Build a self-repair workflow plan from static checker findings.

Task-012 focuses on turning static findings into an ordered repair plan:

script -> error analysis -> repair steps -> revalidation

This v1 implementation supports two repair modes:
1. safe deterministic edits for a narrow subset of issues
2. IR / grounding / layer-regeneration recommendations for the rest
"""

from __future__ import annotations

import argparse
import json
import re
from difflib import get_close_matches
from pathlib import Path

from static_checker_v1 import (
    BLOCK_STARTS,
    END_TO_START,
    ERROR_TAXONOMY_BY_ID,
    analyze_script_text,
    build_block,
    extract_defined_symbols,
    is_block_start,
)


ROOT = Path(__file__).resolve().parent.parent

# Sourced from AFSIM 2.9.0 official documentation:
# wsf_air_mover.html, wsf_ground_mover.html, wsf_surface_mover.html,
# wsf_subsurface_mover.html, chaff_parcel commands, sensor commands.
SAFE_UNIT_DEFAULTS = {
    # Mover commands (wsf_air_mover.html etc.)
    "maximum_speed": "m/sec",
    "minimum_speed": "m/sec",
    "default_radial_acceleration": "g",
    "default_linear_acceleration": "g",
    "altitude": "m",
    "heading": "deg",
    "speed": "m/sec",
    # Mover timing
    "frame_time": "sec",
    "update_interval": "sec",
    "start_time": "sec",
    # Sensor commands
    "frequency": "ghz",
    "power": "kw",
    "bandwidth": "khz",
    "one_m2_detect_range": "km",
    "maximum_range": "km",
    "minimum_range": "km",
    "pulse_width": "sec",
    "pulse_repetition_frequency": "hz",
    # Chaff parcel commands
    "terminal_velocity": "m/s",
    "bloom_diameter": "m",
    "expansion_time_constant": "sec",
    "deceleration_rate": "m/s2",
    "expiration_time": "sec",
    "ejection_velocity": "m/s",
    # Scenario
    "end_time": "sec",
    "duration": "sec",
}

REPAIR_PRIORITY = {
    "E002": 10,
    "E001": 20,
    "E006": 30,
    "E003": 40,
    "E004": 50,
    "E007": 60,
    "E005": 70,
    "E008": 80,
}


def load_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_duration_value(duration) -> str:
    if isinstance(duration, dict):
        value = duration.get("value")
        unit = duration.get("unit")
        if value is not None and unit:
            return f"{value} {unit}"
    if isinstance(duration, str):
        return duration
    return ""


def extract_ir_duration(ir_context: dict | None, plan_context: dict | None) -> str:
    if ir_context:
        ir = ir_context.get("ir", ir_context)
        duration = ir.get("scenario", {}).get("duration")
        normalized = normalize_duration_value(duration)
        if normalized:
            return normalized
    if plan_context:
        duration = (
            plan_context.get("layers", {})
            .get("scenario_assembly", {})
            .get("end_time")
        )
        normalized = normalize_duration_value(duration)
        if normalized:
            return normalized
    return ""


def build_line_contexts(lines: list[str]) -> dict[int, dict]:
    contexts = {}
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        parts = line.split() if line else []
        head = parts[0] if parts else ""

        if parts and is_block_start(head, parts, stack):
            block = build_block(head, parts, line_no)
            stack.append(block)
            active = list(stack)
        else:
            active = list(stack)
            if parts and head in END_TO_START and stack:
                active = list(stack)
                stack.pop()

        contexts[line_no] = {
            "active_kinds": [item["kind"] for item in active],
            "active_names": [item["name"] for item in active if item.get("name")],
            "nearest_block_kind": active[-1]["kind"] if active else "",
            "nearest_block_name": active[-1]["name"] if active and active[-1].get("name") else "",
        }

    return contexts


def infer_layer_scope(finding: dict, contexts: dict[int, dict]) -> str:
    if finding["line"] <= 0:
        message = finding["message"]
        if "end_time" in message:
            return "scenario_assembly"
        if "route or position" in message:
            return "platform_layer"
        if finding["error_id"] == "E008":
            return "mission_layer"
        return "scenario_scaffold"

    context = contexts.get(finding["line"], {})
    kinds = set(context.get("active_kinds", []))
    if {"processor", "comm", "route"} & kinds:
        return "mission_layer"
    if "weapon" in kinds:
        return "weapon_layer"
    if "sensor" in kinds:
        return "sensor_layer"
    if {"platform", "platform_type", "mover"} & kinds:
        return "platform_layer"
    return "scenario_scaffold"


def summarize_context(finding: dict, lines: list[str], contexts: dict[int, dict]) -> dict:
    if finding["line"] <= 0 or finding["line"] > len(lines):
        return {"line_text": "", "nearest_block_kind": "", "nearest_block_name": ""}

    context = contexts.get(finding["line"], {})
    return {
        "line_text": lines[finding["line"] - 1],
        "nearest_block_kind": context.get("nearest_block_kind", ""),
        "nearest_block_name": context.get("nearest_block_name", ""),
    }


def build_reference_candidates(lines: list[str]) -> dict:
    platform_types, antenna_patterns, comm_definitions, advanced_behaviors = extract_defined_symbols(lines)
    return {
        "platform_types": sorted(platform_types),
        "antenna_patterns": sorted(antenna_patterns.keys()),
    }


def build_step(
    index: int,
    finding: dict,
    lines: list[str],
    contexts: dict[int, dict],
    ir_context: dict | None,
    plan_context: dict | None,
    reference_candidates: dict,
) -> dict:
    error_id = finding["error_id"]
    message = finding["message"]
    layer_scope = infer_layer_scope(finding, contexts)
    evidence = summarize_context(finding, lines, contexts)
    taxonomy = ERROR_TAXONOMY_BY_ID.get(error_id, {})
    step = {
        "step_id": f"SR-{index:03d}",
        "priority": REPAIR_PRIORITY.get(error_id, 999),
        "error_id": error_id,
        "line": finding["line"],
        "issue": message,
        "layer_scope": layer_scope,
        "default_severity": taxonomy.get("default_severity", ""),
        "repair_hint": taxonomy.get("repair_hint", ""),
        "evidence": evidence,
        "repair_mode": "",
        "auto_repairable": False,
        "needs_ir_context": False,
        "needs_grounding_refresh": False,
        "suggested_action": "",
        "proposed_edit": None,
    }

    if error_id == "E001":
        command = evidence["line_text"].strip().split()[0] if evidence["line_text"].strip() else ""
        default_unit = SAFE_UNIT_DEFAULTS.get(command)
        parts = evidence["line_text"].strip().split()
        if default_unit and message == "numeric argument missing unit" and len(parts) == 2:
            step["repair_mode"] = "safe_direct_edit"
            step["auto_repairable"] = True
            step["suggested_action"] = f"append default unit `{default_unit}` to `{command}`"
            step["proposed_edit"] = {
                "action": "replace_line",
                "target_line": finding["line"],
                "replacement": evidence["line_text"].rstrip() + f" {default_unit}",
            }
        else:
            step["repair_mode"] = "regenerate_from_ir"
            step["needs_ir_context"] = True
            step["suggested_action"] = "regenerate the numeric command from IR or a verified demo template"

    elif error_id == "E002":
        match = re.match(r"missing (end_\w+)", message)
        if match:
            end_tag = match.group(1)
            step["repair_mode"] = "safe_direct_edit"
            step["auto_repairable"] = True
            step["suggested_action"] = f"append missing closing tag `{end_tag}`"
            step["proposed_edit"] = {
                "action": "append_line",
                "target_line": len(lines),
                "replacement": end_tag,
            }
        else:
            step["repair_mode"] = "manual_block_stack_repair"
            step["suggested_action"] = "repair block nesting first, then rerun static verification"

    elif error_id == "E003":
        step["repair_mode"] = "regenerate_from_grounded_ir"
        step["needs_ir_context"] = True
        if "undefined platform type " in message:
            missing = message.split("undefined platform type ", 1)[1]
            candidates = get_close_matches(missing, reference_candidates["platform_types"], n=3)
            step["suggested_action"] = "rename to an existing grounded platform type or add the missing grounded platform definition"
            if candidates:
                step["proposed_edit"] = {"action": "rename_reference", "candidates": candidates}
        elif "undefined antenna pattern " in message:
            missing = message.split("undefined antenna pattern ", 1)[1]
            candidates = get_close_matches(missing, reference_candidates["antenna_patterns"], n=3)
            step["suggested_action"] = "rename to an existing antenna pattern or regenerate the radar/receiver component"
            if candidates:
                step["proposed_edit"] = {"action": "rename_reference", "candidates": candidates}
        else:
            step["suggested_action"] = "rebuild symbol table and repair the unresolved reference from grounded IR"

    elif error_id == "E004":
        step["repair_mode"] = "regenerate_from_ir"
        step["needs_ir_context"] = True
        step["suggested_action"] = "normalize coordinates from IR locations or route waypoints and rewrite the position line"

    elif error_id == "E005":
        step["repair_mode"] = "refresh_grounding"
        step["needs_grounding_refresh"] = True
        step["suggested_action"] = "re-run grounding and replace the unverified WSF or hallucinated entity with a verified target"

    elif error_id == "E006":
        duration = extract_ir_duration(ir_context, plan_context)
        if message == "missing end_time" and duration:
            step["repair_mode"] = "safe_direct_edit"
            step["auto_repairable"] = True
            step["suggested_action"] = f"insert top-level `end_time {duration}` from IR or generation plan"
            step["proposed_edit"] = {
                "action": "append_line",
                "target_line": len(lines) + 1,
                "replacement": f"end_time {duration}",
            }
        else:
            step["repair_mode"] = "regenerate_from_ir"
            step["needs_ir_context"] = True
            step["suggested_action"] = "fill the missing required field from IR or regenerate the affected layer from template"

    elif error_id == "E007":
        if "missing transmitter block" in message or "missing constant_pattern block" in message:
            step["repair_mode"] = "regenerate_component_from_template"
            step["suggested_action"] = "re-render this component from its grounded template so required sub-blocks are present"
        elif "must be nested under" in message or "route block must be nested under platform" in message:
            step["repair_mode"] = "regenerate_layer"
            step["suggested_action"] = "move the block into the legal parent scope and regenerate the owning layer"
        elif "pseudo keyword" in message:
            step["repair_mode"] = "regenerate_layer"
            step["suggested_action"] = "replace the pseudo keyword with a legal block generated from the component profile"
        elif "not supported by WSF_AIR_MOVER" in message:
            step["repair_mode"] = "manual_or_template_edit"
            step["suggested_action"] = "remove the unsupported command or swap to a mover template that supports it"
        else:
            step["repair_mode"] = "regenerate_layer"
            step["suggested_action"] = "regenerate the affected layer using a component-specific template"

    elif error_id == "E008":
        step["repair_mode"] = "regenerate_script_logic"
        step["suggested_action"] = "rewrite the processor script using verified script API and supported control flow only"

    else:
        step["repair_mode"] = "manual_review"
        step["suggested_action"] = "inspect the finding and repair manually"

    return step


def attempt_safe_repair(
    script_text: str,
    findings: list[dict],
    ir_context: dict | None,
    plan_context: dict | None,
) -> dict:
    lines = script_text.splitlines()
    applied_actions = []
    touched_lines = set()

    for finding in findings:
        if finding["error_id"] != "E001" or finding["line"] <= 0 or finding["line"] > len(lines):
            continue
        if finding["line"] in touched_lines:
            continue

        parts = lines[finding["line"] - 1].strip().split()
        if not parts:
            continue
        command = parts[0]
        default_unit = SAFE_UNIT_DEFAULTS.get(command)
        if finding["message"] != "numeric argument missing unit" or not default_unit or len(parts) != 2:
            continue

        lines[finding["line"] - 1] = lines[finding["line"] - 1].rstrip() + f" {default_unit}"
        touched_lines.add(finding["line"])
        applied_actions.append(
            {
                "error_id": "E001",
                "action": "replace_line",
                "target_line": finding["line"],
                "replacement": lines[finding["line"] - 1],
            }
        )

    # Fix missing end tags (E002: "missing end_xxx") — stack-based insertion
    # that places each end tag after its closest following block content,
    # rather than blindly appending to the end of the file.
    missing_end_tags = []
    for finding in findings:
        if finding["error_id"] != "E002":
            continue
        match = re.match(r"missing (end_\w+)", finding["message"])
        if match:
            missing_end_tags.append((finding["line"], match.group(1)))

    # Deduplicate and sort: insert deepest-first so nesting stays correct
    seen_tags = set()
    unique_missing = []
    for line_no, end_tag in missing_end_tags:
        if end_tag not in seen_tags:
            seen_tags.add(end_tag)
            unique_missing.append((line_no, end_tag))
    # Find end_time line — insert missing end tags BEFORE end_time
    end_time_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("end_time"):
            end_time_idx = i
            break
    insert_at = end_time_idx if end_time_idx is not None else len(lines)
    for _, end_tag in sorted(unique_missing, key=lambda item: item[0], reverse=True):
        lines.insert(insert_at, end_tag)
        applied_actions.append(
            {
                "error_id": "E002",
                "action": "insert_line",
                "target_line": insert_at + 1,
                "replacement": end_tag,
            }
        )

    # Fix cross-closed blocks (E002: "end_X closes Y from line N").
    # Source: AFSIM 2.9.0 platform_part_commands.html defines 8 platform part types,
    # each with its own end_xxx that must not be interchanged.
    cross_close_findings = []
    for finding in findings:
        if finding["error_id"] != "E002":
            continue
        match = re.match(r"(\w+) closes (\w+) from line (\d+)", finding["message"])
        if match:
            wrong_end = match.group(1)
            closed_kind = match.group(2)
            cross_close_findings.append((finding["line"], wrong_end, closed_kind))

    cross_close_findings.sort(key=lambda item: item[0])
    for line_no, wrong_end, closed_kind in cross_close_findings:
        if line_no <= 0 or line_no > len(lines):
            continue
        correct_end = BLOCK_STARTS.get(closed_kind, f"end_{closed_kind}")
        if wrong_end == correct_end:
            continue
        old_line = lines[line_no - 1]
        lines[line_no - 1] = old_line.replace(wrong_end, correct_end)
        applied_actions.append(
            {
                "error_id": "E002",
                "action": "replace_line",
                "target_line": line_no,
                "replacement": lines[line_no - 1],
                "reason": f"cross-close: {wrong_end} -> {correct_end} (closes {closed_kind})",
            }
        )

    duration = extract_ir_duration(ir_context, plan_context)
    if any(item["error_id"] == "E006" and item["message"] == "missing end_time" for item in findings) and duration:
        lines.append(f"end_time {duration}")
        applied_actions.append(
            {
                "error_id": "E006",
                "action": "append_line",
                "target_line": len(lines),
                "replacement": f"end_time {duration}",
            }
        )

    repaired_text = "\n".join(lines) + ("\n" if lines else "")
    return {
        "applied_actions": applied_actions,
        "repaired_text": repaired_text,
        "post_repair_analysis": analyze_script_text(repaired_text),
    }


def build_repair_plan(
    script_path: Path,
    script_text: str,
    ir_context: dict | None,
    plan_context: dict | None,
) -> dict:
    analysis = analyze_script_text(script_text, script_label=str(script_path))
    lines = script_text.splitlines()
    contexts = build_line_contexts(lines)
    reference_candidates = build_reference_candidates(lines)

    findings = sorted(
        analysis["findings"],
        key=lambda item: (REPAIR_PRIORITY.get(item["error_id"], 999), item["line"], item["message"]),
    )
    repair_steps = [
        build_step(i, finding, lines, contexts, ir_context, plan_context, reference_candidates)
        for i, finding in enumerate(findings, start=1)
    ]

    safe_repair = attempt_safe_repair(script_text, findings, ir_context, plan_context)
    target_layers = []
    for step in repair_steps:
        if step["layer_scope"] not in target_layers:
            target_layers.append(step["layer_scope"])

    auto_steps = [step for step in repair_steps if step["auto_repairable"]]
    needs_regeneration = [step for step in repair_steps if not step["auto_repairable"]]

    if not findings:
        recommended_next_action = "no_repair_needed"
    elif auto_steps and not needs_regeneration:
        recommended_next_action = "apply_safe_repairs_then_revalidate"
    elif auto_steps:
        recommended_next_action = "apply_safe_repairs_then_regenerate_flagged_layers"
    else:
        recommended_next_action = "regenerate_flagged_layers_or_refresh_grounding"

    return {
        "version": "repair_workflow_v1",
        "input": {
            "script_path": str(script_path),
            "has_ir_context": bool(ir_context),
            "has_generation_plan": bool(plan_context),
        },
        "static_analysis": analysis,
        "repair_summary": {
            "finding_count": len(findings),
            "auto_repairable_count": len(auto_steps),
            "manual_or_regeneration_count": len(needs_regeneration),
            "target_layers": target_layers,
            "recommended_next_action": recommended_next_action,
        },
        "repair_steps": repair_steps,
        "safe_repair_attempt": {
            "attempted": True,
            "applied_action_count": len(safe_repair["applied_actions"]),
            "applied_actions": safe_repair["applied_actions"],
            "post_repair_analysis": safe_repair["post_repair_analysis"],
            "improved_finding_count": len(findings) - len(safe_repair["post_repair_analysis"]["findings"]),
        },
        "revalidation_plan": {
            "tool": "static_checker_v1",
            "command_hint": f"python scripts/static_checker_v1.py {script_path}",
            "success_condition": "static_pass == true",
        },
        "repaired_text_preview": safe_repair["repaired_text"],
    }


def main():
    parser = argparse.ArgumentParser(description="Build self-repair workflow plan from static checker findings.")
    parser.add_argument("--script", required=True, help="Path to generated AFSIM script.")
    parser.add_argument("--ir-json", help="Optional IR JSON path for filling repair context.")
    parser.add_argument("--plan-json", help="Optional hierarchical generation plan JSON path.")
    parser.add_argument("--output", help="Optional output JSON path.")
    parser.add_argument("--write-repaired-script", help="Optional path to write the safe-repair preview script.")
    args = parser.parse_args()

    script_path = Path(args.script)
    script_text = script_path.read_text(encoding="utf-8-sig")

    ir_context = load_json_file(Path(args.ir_json)) if args.ir_json else None
    plan_context = load_json_file(Path(args.plan_json)) if args.plan_json else None

    repair_plan = build_repair_plan(script_path, script_text, ir_context, plan_context)
    payload = json.dumps(repair_plan, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    if args.write_repaired_script:
        Path(args.write_repaired_script).write_text(
            repair_plan["repaired_text_preview"],
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
