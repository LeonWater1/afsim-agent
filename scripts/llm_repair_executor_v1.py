#!/usr/bin/env python3
"""
Task-016: LLM-guided script repair executor.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from execution_repair_planner_v1 import build_execution_repair_plan
from llm_client_v1 import LLMClient, extract_json_object, strip_code_fences
from llm_script_generator_v1 import build_syntax_guardrails
from self_repair_planner_v1 import build_repair_plan
from static_checker_v1 import BLOCK_STARTS, END_TO_START, NESTED_ONLY_KEYWORDS, VALID_WSFS, analyze_script_text, build_block, is_block_start


ROOT = Path(__file__).resolve().parent.parent

BLOCK_LAYER = {
    "script_interface": "scenario_scaffold",
    "event_output": "scenario_assembly",
    "event_pipe": "scenario_assembly",
    "platform": "platform_layer",
    "platform_type": "platform_layer",
    "mover": "platform_layer",
    "route": "mission_layer",
    "sensor": "sensor_layer",
    "antenna_pattern": "sensor_layer",
    "constant_pattern": "sensor_layer",
    "transmitter": "sensor_layer",
    "receiver": "sensor_layer",
    "weapon": "weapon_layer",
    "processor": "mission_layer",
    "comm": "mission_layer",
    "task": "mission_layer",
}

PSEUDO_BLOCK_PAIRS = {
    "comm_network": "end_comm_network",
    "comm_transceiver": "end_comm_transceiver",
    "explicit_weapon": "end_explicit_weapon",
    "radar_sensor": "end_radar_sensor",
    "task_processor": "end_task_processor",
    "track_processor": "end_track_processor",
}


def _task_metadata(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": task.get("id"),
        "difficulty": task.get("difficulty", ""),
        "source_hint": task.get("source_hint", ""),
        "covered_components": task.get("covered_components", []),
        "evaluation_focus": task.get("evaluation_focus", []),
    }


def _summarize_grounded_ir(grounded_ir: dict[str, Any]) -> dict[str, Any]:
    return {
        "all_grounded": grounded_ir.get("all_grounded", False),
        "unresolved_items": grounded_ir.get("unresolved_items", []),
        "entities": [
            {
                "id": entity.get("id"),
                "role": entity.get("role"),
                "domain": entity.get("domain"),
                "platform_type_hint": entity.get("platform_type_hint", ""),
                "matched_platform": entity.get("grounding", {}).get("canonical_id", ""),
                "default_component_bundle": entity.get("grounding", {}).get("row", {}).get("default_component_bundle", []),
            }
            for entity in grounded_ir.get("entities", [])
        ],
    }


def _summarize_generation_plan(generation_plan: dict[str, Any]) -> dict[str, Any]:
    layers = generation_plan.get("layers", {})
    return {
        "generation_order": generation_plan.get("generation_order", []),
        "scenario": layers.get("scenario_scaffold", {}),
        "platform_entities": [
            {
                "entity_id": entity.get("entity_id"),
                "role": entity.get("role"),
                "domain": entity.get("domain"),
                "platform": entity.get("platform_grounding", {}).get("canonical_id"),
                "component_families": entity.get("component_families", {}),
                "ready": entity.get("ready", False),
            }
            for entity in layers.get("platform_layer", {}).get("entities", [])
        ],
        "mission_processors": layers.get("mission_layer", {}).get("processors", []),
        "mission_comms": layers.get("mission_layer", {}).get("comms", []),
        "mission_tasks": layers.get("mission_layer", {}).get("tasks", []),
    }


def _load_task_reference_script(task: dict[str, Any]) -> str:
    source_hint = task.get("source_hint", "")
    if not source_hint:
        return ""

    reference_path = ROOT / source_hint
    if not reference_path.exists():
        return ""
    return "\n".join(reference_path.read_text(encoding="utf-8-sig").splitlines()[:60]).strip()


def _verified_wsf_lines() -> str:
    sorted_wsfs = sorted(VALID_WSFS)
    return "\n".join(" ".join(sorted_wsfs[index : index + 8]) for index in range(0, len(sorted_wsfs), 8))


def _span_layer(kind: str) -> str:
    return BLOCK_LAYER.get(kind, "scenario_scaffold")


def _collect_block_spans(script_text: str) -> list[dict[str, Any]]:
    lines = script_text.splitlines()
    stack: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            block = build_block(head, parts, line_no)
            block["start_line"] = line_no
            block["depth"] = len(stack)
            stack.append(block)
            continue

        if head in END_TO_START and stack:
            block = stack.pop()
            spans.append(
                {
                    "kind": block["kind"],
                    "name": block.get("name", ""),
                    "start_line": block["start_line"],
                    "end_line": line_no,
                    "depth": block["depth"],
                    "layer_scope": _span_layer(block["kind"]),
                    "text": "\n".join(lines[block["start_line"] - 1 : line_no]),
                }
            )

    for block in stack:
        spans.append(
            {
                "kind": block["kind"],
                "name": block.get("name", ""),
                "start_line": block["start_line"],
                "end_line": len(lines),
                "depth": block["depth"],
                "layer_scope": _span_layer(block["kind"]),
                "text": "\n".join(lines[block["start_line"] - 1 :]),
            }
        )

    line_index = 0
    while line_index < len(lines):
        raw = lines[line_index]
        line = raw.strip()
        parts = line.split()
        if not parts or parts[0] not in NESTED_ONLY_KEYWORDS:
            line_index += 1
            continue

        head = parts[0]
        end_token = f"end_{head}"
        end_index = line_index + 1
        while end_index < len(lines):
            maybe_end = lines[end_index].strip().split()
            if maybe_end and maybe_end[0] == end_token:
                break
            end_index += 1
        if end_index >= len(lines):
            end_index = len(lines) - 1

        spans.append(
            {
                "kind": head,
                "name": parts[1] if len(parts) >= 2 else "",
                "start_line": line_index + 1,
                "end_line": end_index + 1,
                "depth": -1,
                "layer_scope": _span_layer(head),
                "text": "\n".join(lines[line_index : end_index + 1]),
            }
        )
        line_index = end_index + 1

    line_index = 0
    while line_index < len(lines):
        raw = lines[line_index]
        line = raw.strip()
        parts = line.split()
        if not parts or parts[0] not in PSEUDO_BLOCK_PAIRS:
            line_index += 1
            continue

        head = parts[0]
        end_token = PSEUDO_BLOCK_PAIRS[head]
        end_index = line_index + 1
        while end_index < len(lines):
            maybe_end = lines[end_index].strip().split()
            if maybe_end and maybe_end[0] == end_token:
                break
            end_index += 1
        if end_index >= len(lines):
            end_index = len(lines) - 1

        spans.append(
            {
                "kind": head,
                "name": parts[1] if len(parts) >= 2 else "",
                "start_line": line_index + 1,
                "end_line": end_index + 1,
                "depth": -1,
                "layer_scope": _span_layer(
                    {
                        "explicit_weapon": "weapon",
                        "radar_sensor": "sensor",
                        "track_processor": "processor",
                        "task_processor": "processor",
                        "comm_network": "comm",
                        "comm_transceiver": "comm",
                    }.get(head, head)
                ),
                "text": "\n".join(lines[line_index : end_index + 1]),
            }
        )
        line_index = end_index + 1

    return spans


def _select_layer_targets(script_text: str, repair_plan: dict[str, Any]) -> list[dict[str, Any]]:
    spans = _collect_block_spans(script_text)
    findings = repair_plan.get("static_analysis", {}).get("findings", [])
    repair_steps = repair_plan.get("repair_steps", [])
    target_layers = set(repair_plan.get("repair_summary", {}).get("target_layers", []))
    selected: dict[tuple[int, int], dict[str, Any]] = {}

    step_by_line = {}
    for step in repair_steps:
        line = step.get("line", 0)
        if line > 0:
            step_by_line.setdefault(line, []).append(step)

    for finding in findings:
        line = finding.get("line", 0)
        if line <= 0:
            continue
        candidate_layers = {step.get("layer_scope") for step in step_by_line.get(line, []) if step.get("layer_scope")}
        if not candidate_layers:
            candidate_layers = target_layers

        candidates = [
            span
            for span in spans
            if span["start_line"] <= line <= span["end_line"]
            and (not candidate_layers or span["layer_scope"] in candidate_layers)
        ]
        if not candidates:
            candidates = [span for span in spans if span["start_line"] <= line <= span["end_line"]]
        if not candidates:
            continue

        chosen = sorted(
            candidates,
            key=lambda span: (span["end_line"] - span["start_line"], -span["depth"]),
        )[0]
        key = (chosen["start_line"], chosen["end_line"])
        selected[key] = {
            **chosen,
            "findings": [
                item
                for item in findings
                if chosen["start_line"] <= item.get("line", 0) <= chosen["end_line"]
            ],
        }

    return sorted(selected.values(), key=lambda item: item["start_line"])


def _merge_replacement_blocks(script_text: str, replacements: list[dict[str, Any]]) -> str:
    lines = script_text.splitlines()
    normalized = []
    for replacement in replacements:
        start_line = int(replacement.get("start_line", 0))
        end_line = int(replacement.get("end_line", 0))
        if "text" not in replacement:
            continue
        text = str(replacement.get("text", "")).strip("\n")
        if start_line <= 0 or end_line < start_line:
            continue
        normalized.append((start_line, end_line, text.splitlines()))

    for start_line, end_line, replacement_lines in sorted(normalized, reverse=True):
        lines[start_line - 1 : end_line] = replacement_lines

    return "\n".join(lines) + ("\n" if lines else "")


def _layer_regeneration_messages(
    task: dict[str, Any],
    ir: dict[str, Any],
    grounded_ir: dict[str, Any],
    generation_plan: dict[str, Any],
    repair_plan: dict[str, Any],
    targets: list[dict[str, Any]],
) -> list[dict[str, str]]:
    system_prompt = """You are the layer-regeneration module of an AFSIM scenario generation agent.

Return JSON only.

Rules:
- Return a JSON object with key replacement_blocks.
- replacement_blocks must be an array of objects: start_line, end_line, text.
- Only rewrite the target blocks listed by start_line/end_line.
- Do not rewrite unaffected layers or unrelated blocks.
- The replacement text must be complete for each target block, including matching end_xxx tags.
- If the target block is unsupported and can be omitted while preserving a minimal executable scenario, set text to an empty string to delete only that target block.
- For `weapon <name> WSF_AIR_TO_AIR_MISSILE`, prefer deleting the target weapon block in a minimal self-contained script instead of inventing nested mover/guidance/fuse syntax.
- No markdown, no explanations outside JSON.
"""
    payload = {
        "task": _task_metadata(task),
        "syntax_guardrails": build_syntax_guardrails(),
        "ir_scenario": ir.get("scenario", {}),
        "grounded_ir_summary": _summarize_grounded_ir(grounded_ir),
        "generation_plan_summary": _summarize_generation_plan(generation_plan),
        "repair_summary": repair_plan.get("repair_summary", {}),
        "repair_steps": repair_plan.get("repair_steps", [])[:12],
        "output_rules": _output_repair_rules(ir),
        "verified_wsf_types": sorted(VALID_WSFS),
        "targets": [
            {
                "start_line": target["start_line"],
                "end_line": target["end_line"],
                "kind": target["kind"],
                "name": target.get("name", ""),
                "layer_scope": target["layer_scope"],
                "findings": target.get("findings", []),
                "current_text": target["text"],
            }
            for target in targets
        ],
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]


def attempt_layer_regeneration(
    task: dict[str, Any],
    script_text: str,
    ir: dict[str, Any],
    grounded_ir: dict[str, Any],
    generation_plan: dict[str, Any],
    repair_plan: dict[str, Any],
    client: LLMClient,
) -> dict[str, Any]:
    targets = _select_layer_targets(script_text, repair_plan)
    if not targets:
        return {
            "attempted": False,
            "reason": "no line-scoped target blocks found",
            "target_count": 0,
            "replacement_count": 0,
            "repaired_text": script_text,
            "static_analysis": analyze_script_text(script_text, script_label=f"{task['id']}_layer_regeneration"),
        }

    response = client.chat(
        _layer_regeneration_messages(task, ir, grounded_ir, generation_plan, repair_plan, targets),
        temperature=0.0,
        max_tokens=12288,
        response_format={"type": "json_object"},
    )
    payload = extract_json_object(response.content)
    replacements = payload.get("replacement_blocks", [])
    if not isinstance(replacements, list):
        replacements = []

    allowed_ranges = {(target["start_line"], target["end_line"]) for target in targets}
    filtered_replacements = [
        replacement
        for replacement in replacements
        if (int(replacement.get("start_line", 0)), int(replacement.get("end_line", 0))) in allowed_ranges
    ]
    repaired_text = _merge_replacement_blocks(script_text, filtered_replacements)
    return {
        "attempted": True,
        "model": response.model,
        "target_count": len(targets),
        "targets": [
            {
                "start_line": target["start_line"],
                "end_line": target["end_line"],
                "kind": target["kind"],
                "layer_scope": target["layer_scope"],
                "findings": target.get("findings", []),
            }
            for target in targets
        ],
        "replacement_count": len(filtered_replacements),
        "raw_response_preview": response.content[:1200],
        "repaired_text": repaired_text,
        "static_analysis": analyze_script_text(repaired_text, script_label=f"{task['id']}_layer_regeneration"),
    }


def _output_repair_rules(ir: dict[str, Any]) -> dict[str, Any]:
    scenario = ir.get("scenario", {})
    scenario_name = scenario.get("name", "generated_scenario")
    outputs = scenario.get("outputs", [])
    return {
        "requested_outputs": outputs,
        "allowed_output_blocks": [
            f"event_pipe file output/{scenario_name}.aer end_event_pipe",
            f"event_output file output/{scenario_name}.evt end_event_output",
        ],
        "forbidden_output_commands": ["mission_log", "end_mission_log", "output"],
    }


def _runtime_repair_hints(log_text: str) -> list[str]:
    lowered = log_text.lower()
    hints: list[str] = []
    if "unknown command: frequency_min" in lowered or "unknown command: frequency_max" in lowered or "unknown command: sensitivity" in lowered:
        hints.append("For ESM/bearing-only scenes, do not use frequency_min, frequency_max, or sensitivity. Reuse verified ESM patterns such as detection_sensitivity or documented mode-template structures.")
    if "could not find behavior" in lowered:
        hints.append("Do not reference behavior names unless the self-contained script also provides the verified supporting behavior definitions. If those definitions are external-only, remove the behavior-tree block in the minimal executable approximation.")
    if "wsf_brawler_platform must have a wsf_brawler_mover" in lowered or "wsf_brawler_platform must have a wsf_threat_processor" in lowered:
        hints.append("A Brawler family platform must follow the verified Brawler component bundle: WSF_BRAWLER_MOVER plus WSF_THREAT_PROCESSOR, not a generic WSF_AIR_MOVER approximation.")
    if "unexpected end of data" in lowered:
        hints.append("Close every custom block explicitly, especially chaff_parcel, frequency_maximum_rcs_table, and ejector blocks.")
    if "could not find weapon" in lowered:
        hints.append("Do not keep unresolved direct weapon type references. Replace them with a verified self-contained profile or remove the unsupported weapon block.")
    return hints


def _repair_messages(
    mode: str,
    task: dict[str, Any],
    script_text: str,
    ir: dict[str, Any],
    grounded_ir: dict[str, Any],
    generation_plan: dict[str, Any],
    repair_context: dict[str, Any],
) -> list[dict[str, str]]:
    if mode == "static_repair":
        focus = "Repair the script so it passes the static checker while preserving the intended scenario."
    else:
        focus = "Repair the script based on mission execution feedback and preserve the intended scenario."

    system_prompt = """You are the repair module of an AFSIM scenario generation agent.

Return exactly one corrected full AFSIM script as plain text.

Rules:
- No markdown fences and no explanation.
- Keep end_xxx tags balanced.
- Preserve all unaffected scenario structure when possible.
- Prefer local edits that directly address the listed findings.
- Do not invent unsupported WSF_* identifiers.
- Do not emit standalone mission_log or output commands.
- Reuse valid block patterns from the verified task-family reference script when available.
- Do not emit include_once, file_path, define_path_variable, or external file dependencies.
- If runtime says `Could not find weapon WSF_*`, replace that direct weapon type usage with a valid self-contained explicit weapon definition or remove the unsupported weapon block in the minimal executable approximation.
"""
    verified_wsfs = _verified_wsf_lines()
    output_rules = _output_repair_rules(ir)
    task_meta = _task_metadata(task)
    grounded_summary = _summarize_grounded_ir(grounded_ir)
    plan_summary = _summarize_generation_plan(generation_plan)
    reference_script = _load_task_reference_script(task)
    runtime_hints = _runtime_repair_hints(
        json.dumps(repair_context, ensure_ascii=False) if isinstance(repair_context, dict) else str(repair_context)
    )
    user_prompt = (
        f"Mode: {mode}\n"
        f"Task ID: {task['id']}\n"
        f"Natural-language request:\n{task['input']}\n\n"
        f"Task metadata:\n{json.dumps(task_meta, ensure_ascii=False, indent=2)}\n\n"
        f"Common syntax guardrails:\n{build_syntax_guardrails()}\n\n"
        f"Verified task-family reference script:\n{reference_script or '(none)'}\n\n"
        f"IR:\n{json.dumps(ir, ensure_ascii=False, indent=2)}\n\n"
        f"Grounded IR Summary:\n{json.dumps(grounded_summary, ensure_ascii=False, indent=2)}\n\n"
        f"Generation Plan Summary:\n{json.dumps(plan_summary, ensure_ascii=False, indent=2)}\n\n"
        f"Repair Context:\n{json.dumps(repair_context, ensure_ascii=False, indent=2)}\n\n"
        f"Output Rules:\n{json.dumps(output_rules, ensure_ascii=False, indent=2)}\n\n"
        f"Verified WSF Types:\n{verified_wsfs}\n\n"
        f"Runtime-specific repair hints:\n{json.dumps(runtime_hints, ensure_ascii=False, indent=2)}\n\n"
        f"{focus}\n\n"
        f"Current script:\n{script_text}\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def llm_static_repair(
    task: dict[str, Any],
    script_text: str,
    ir: dict[str, Any],
    grounded_ir: dict[str, Any],
    generation_plan: dict[str, Any],
    client: LLMClient,
    mission_errors: str = "",
) -> dict[str, Any]:
    initial_repair_plan = build_repair_plan(Path(f"{task['id']}.txt"), script_text, {"ir": ir}, generation_plan)
    # Inject mission.exe errors into repair context for richer diagnostics
    if mission_errors:
        initial_repair_plan["mission_errors"] = mission_errors[:2000]
    safe_repair_attempt = initial_repair_plan.get("safe_repair_attempt", {})
    safe_repair_analysis = safe_repair_attempt.get("post_repair_analysis", {})
    safe_repair_text = initial_repair_plan.get("repaired_text_preview", script_text)
    if safe_repair_analysis.get("static_pass"):
        return {
            "version": "llm_repair_executor_v1",
            "mode": "static_repair_safe_direct_edit",
            "repair_plan": initial_repair_plan,
            "repair_plan_after_safe_repair": None,
            "layer_regeneration_attempt": None,
            "full_script_fallback_used": False,
            "repaired_text": safe_repair_text,
            "static_analysis": safe_repair_analysis,
        }

    working_script_text = safe_repair_text if safe_repair_attempt.get("applied_action_count", 0) > 0 else script_text
    working_repair_plan = (
        build_repair_plan(Path(f"{task['id']}.txt"), working_script_text, {"ir": ir}, generation_plan)
        if working_script_text != script_text
        else initial_repair_plan
    )
    layer_regeneration_attempt: dict[str, Any] | None = None

    if working_repair_plan.get("repair_summary", {}).get("manual_or_regeneration_count", 0) > 0:
        try:
            layer_regeneration_attempt = attempt_layer_regeneration(
                task,
                working_script_text,
                ir,
                grounded_ir,
                generation_plan,
                working_repair_plan,
                client,
            )
            if layer_regeneration_attempt["static_analysis"]["static_pass"]:
                return {
                    "version": "llm_repair_executor_v1",
                    "mode": "static_repair_layer_regeneration",
                    "repair_plan": initial_repair_plan,
                    "repair_plan_after_safe_repair": working_repair_plan if working_repair_plan is not initial_repair_plan else None,
                    "layer_regeneration_attempt": layer_regeneration_attempt,
                    "full_script_fallback_used": False,
                    "repaired_text": layer_regeneration_attempt["repaired_text"],
                    "static_analysis": layer_regeneration_attempt["static_analysis"],
                }
        except Exception as exc:
            layer_regeneration_attempt = {
                "attempted": True,
                "error": str(exc),
                "static_analysis": analyze_script_text(working_script_text, script_label=f"{task['id']}_layer_regeneration_error"),
            }

    # Restore full-script LLM repair only when mission.exe errors are available
    # to guide the repair with real AFSIM parser diagnostics.
    if mission_errors:
        augmented_plan = dict(working_repair_plan)
        augmented_plan["mission_errors"] = mission_errors[:2000]
        response = client.chat(
            _repair_messages("static_repair", task, working_script_text, ir, grounded_ir, generation_plan, augmented_plan),
            temperature=0.0,
            max_tokens=12288,
        )
        repaired_text = strip_code_fences(response.content).strip() + "\n"
        return {
            "version": "llm_repair_executor_v1",
            "mode": "static_repair_full_script",
            "repair_plan": initial_repair_plan,
            "repair_plan_after_safe_repair": working_repair_plan if working_repair_plan is not initial_repair_plan else None,
            "layer_regeneration_attempt": layer_regeneration_attempt,
            "full_script_fallback_used": True,
            "repaired_text": repaired_text,
            "static_analysis": analyze_script_text(repaired_text, script_label=f"{task['id']}_static_repair"),
        }

    # No mission errors to guide repair — return best available text.
    return {
        "version": "llm_repair_executor_v1",
        "mode": "static_repair_safe_direct_edit",
        "repair_plan": initial_repair_plan,
        "repair_plan_after_safe_repair": working_repair_plan if working_repair_plan is not initial_repair_plan else None,
        "layer_regeneration_attempt": layer_regeneration_attempt,
        "full_script_fallback_used": False,
        "repaired_text": working_script_text,
        "static_analysis": analyze_script_text(working_script_text, script_label=f"{task['id']}_static_repair"),
    }


def llm_execution_repair(
    task: dict[str, Any],
    script_text: str,
    ir: dict[str, Any],
    grounded_ir: dict[str, Any],
    generation_plan: dict[str, Any],
    mission_status: str,
    return_code: int | None,
    log_text: str,
    client: LLMClient,
) -> dict[str, Any]:
    static_analysis = analyze_script_text(script_text, script_label=f"{task['id']}_execution_repair")
    execution_plan = build_execution_repair_plan(
        Path(f"{task['id']}.txt"),
        mission_status,
        return_code,
        log_text,
        static_analysis,
    )
    response = client.chat(
        _repair_messages("execution_repair", task, script_text, ir, grounded_ir, generation_plan, execution_plan),
        temperature=0.0,
        max_tokens=12288,
    )
    repaired_text = strip_code_fences(response.content).strip() + "\n"
    return {
        "version": "llm_repair_executor_v1",
        "mode": "execution_repair",
        "execution_plan": execution_plan,
        "repaired_text": repaired_text,
        "static_analysis": analyze_script_text(repaired_text, script_label=f"{task['id']}_execution_repair"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM-guided repair on an AFSIM script.")
    parser.add_argument("--mode", choices=["static_repair", "execution_repair"], required=True)
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--ir-json", required=True)
    parser.add_argument("--grounded-ir-json", required=True)
    parser.add_argument("--plan-json", required=True)
    parser.add_argument("--mission-status", default="FAIL")
    parser.add_argument("--return-code", type=int, default=1)
    parser.add_argument("--log-path")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    task = json.loads(Path(args.task_json).read_text(encoding="utf-8-sig"))
    script_text = Path(args.script).read_text(encoding="utf-8-sig")
    ir_payload = json.loads(Path(args.ir_json).read_text(encoding="utf-8-sig"))
    grounded_ir = json.loads(Path(args.grounded_ir_json).read_text(encoding="utf-8-sig"))
    generation_plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8-sig"))
    ir = ir_payload["ir"] if isinstance(ir_payload, dict) and isinstance(ir_payload.get("ir"), dict) else ir_payload
    log_text = Path(args.log_path).read_text(encoding="utf-8-sig") if args.log_path else ""

    client = LLMClient.from_env(model=args.model)
    if args.mode == "static_repair":
        result = llm_static_repair(task, script_text, ir, grounded_ir, generation_plan, client)
    else:
        result = llm_execution_repair(
            task,
            script_text,
            ir,
            grounded_ir,
            generation_plan,
            args.mission_status,
            args.return_code,
            log_text,
            client,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
