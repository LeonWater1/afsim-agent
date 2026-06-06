#!/usr/bin/env python3
"""
Task-020: Hierarchical Generation Executor v1

This executor only owns the generation stage:

    IR -> Ground -> [layered generation -> merge] -> full script

It does not perform static checking or repair. Those remain in the outer
pipeline:

    ... -> full script -> Static -> Repair -> mission.exe

Design:
- phase1_skeleton: one serial LLM call
- phase2_shared: one serial LLM call
- phase3_platforms: one independent LLM call per entity (parallel)
- phase4_tasks: one independent LLM call per task (parallel)
- phase5_assembly: one serial LLM call to merge and minimally fix references
"""
from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .reference_rules import build_compact_prompt, build_forbidden_regex, normalise_units, postprocess_script
from .generation_planner import build_generation_plan
from .llm_client import LLMClient, strip_code_fences
from .static_checker import VALID_WSFS


ROOT = Path(__file__).resolve().parent.parent.parent

SORTED_WSFS = sorted(VALID_WSFS)
WSF_BLOCK = "\n".join(
    " ".join(SORTED_WSFS[i : i + 8]) for i in range(0, len(SORTED_WSFS), 8)
)

RULES = build_compact_prompt()

# Concrete AFSIM syntax examples — injected into generation prompts to guide LLM.
# These demonstrate correct AFSIM 2.9.0 syntax for the most common patterns.
_AFSIM_SYNTAX_EXAMPLES = """
CONCRETE AFSIM 2.9.0 SYNTAX EXAMPLES (follow these EXACT patterns):

Example 1 — platform_type with mover:
  platform_type PT_FIGHTER WSF_PLATFORM
     mover WSF_AIR_MOVER
        maximum_speed 500 m/sec
        minimum_speed 50 m/sec
        default_radial_acceleration 5 g
     end_mover
  end_platform_type

Example 2 — platform_type with sensor (radar):
  platform_type PT_RADAR WSF_PLATFORM
     mover WSF_GROUND_MOVER
        maximum_speed 1 m/sec
     end_mover
     sensor radar WSF_RADAR_SENSOR
        frame_time 1 sec
        maximum_range 200 nm
        transmitter
           power 100 kW
           frequency 3000 MHz
        end_transmitter
        receiver
           frequency 3000 MHz
        end_receiver
     end_sensor
  end_platform_type

Example 3 — platform instance with route:
  platform fighter_1 PT_FIGHTER
     side blue
     position 30.5n 120.0e altitude 10000 ft msl
     route
        position 30.5n 120.0e altitude 10000 ft msl speed 200 m/sec
        position 31.0n 121.0e altitude 10000 ft msl speed 200 m/sec
     end_route
  end_platform

Example 4 — platform instance (static):
  platform radar_site PT_RADAR
     side blue
     position 35.0n 118.0e altitude 0 ft msl
  end_platform

Example 5 — event output:
  event_pipe
     file output/scenario.aer
  end_event_pipe

CRITICAL SYNTAX RULES:
- platform_type takes EXACTLY: platform_type <NAME> WSF_PLATFORM (or WSF_BRAWLER_PLATFORM)
- mover takes EXACTLY: mover <WSF_TYPE>  (ONE argument — the WSF type)
- sensor/weapon/processor take: <block> <NAME> <WSF_TYPE>
- platform instance takes: platform <NAME> <TYPE_NAME>
- route is ONLY inside platform — NEVER at top level
- receiver/transmitter are ONLY inside sensor
- end_time is ALWAYS the LAST line at top level
- ALL numeric values MUST have units
"""


def _syntax_examples() -> str:
    return _AFSIM_SYNTAX_EXAMPLES


def _safe_name(text: str, prefix: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text)
    cleaned = cleaned.strip("_") or prefix
    return f"{prefix}_{cleaned}".upper()


def _entity_type_name(entity_id: str) -> str:
    return _safe_name(entity_id, "PT")


def _entity_instance_name(entity_id: str) -> str:
    return entity_id


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _chat_text(client: LLMClient, prompt: str, max_tokens: int = 8192) -> str:
    response = client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return strip_code_fences(response.content)


def _load_reference_script(task_context: dict[str, Any] | None) -> str:
    if not task_context:
        return ""
    source_hint = task_context.get("source_hint", "")
    if not source_hint:
        return ""
    candidates = [
        ROOT / "benchmarks" / "benchmark_v2" / source_hint,
        ROOT / source_hint,
    ]
    for reference_path in candidates:
        if reference_path.exists():
            lines = reference_path.read_text(encoding="utf-8-sig").splitlines()
            # Strip include / include_once / include_file lines — the generated
            # script must be self-contained; reference includes cause LLM to
            # hallucinate non-existent include paths.
            lines = [l for l in lines if not l.strip().startswith(("include_once ", "include_file ", "include "))]
            # Also strip define_path_variable / file_path / log_file — they
            # reference external paths that don't exist in the task directory.
            lines = [l for l in lines if not l.strip().startswith(("define_path_variable ", "file_path ", "log_file "))]
            return "\n".join(lines[:120]).strip()
    return ""


def _reference_section(task_context: dict[str, Any] | None) -> str:
    reference_script = _load_reference_script(task_context)
    if not reference_script:
        return "Verified task-family reference script:\n(none)\n"
    return f"Verified task-family reference script:\n```afsim\n{reference_script}\n```\n"


def _make_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    platform_layer = plan["layers"]["platform_layer"]
    mission_layer = plan["layers"]["mission_layer"]
    manifest = {
        "scenario_name": plan["layers"]["scenario_scaffold"].get("scenario_name", ""),
        "platform_types": {},
        "platform_instances": {},
        "route_ids": [route["route_id"] for route in mission_layer.get("routes", [])],
        "task_ids": [task["task_id"] for task in mission_layer.get("tasks", [])],
    }
    for entity in platform_layer.get("entities", []):
        manifest["platform_types"][entity["entity_id"]] = _entity_type_name(entity["entity_id"])
        manifest["platform_instances"][entity["entity_id"]] = _entity_instance_name(entity["entity_id"])
    return manifest


def p1_skeleton(plan: dict[str, Any], manifest: dict[str, Any], task_context: dict[str, Any] | None) -> str:
    scaffold = plan["layers"]["scenario_scaffold"]
    reference = _reference_section(task_context)
    return f"""PHASE 1: Generate ONLY the scenario skeleton.

Scenario:
- name: {scaffold.get("scenario_name")}
- description: {scaffold.get("description", "")}
- duration: {json.dumps(scaffold.get("duration", {}), ensure_ascii=False)}
- domains: {json.dumps(scaffold.get("domains", []), ensure_ascii=False)}

Generate ONLY:
- an optional comment header
- NEVER include_once, include_file, include, file_path, log_file, or define_path_variable (script must be self-contained)
- no scenario block
- no top-level side declarations
- no location blocks

Do NOT generate:
- platform_type blocks
- platform blocks
- route blocks
- processor logic
- event_pipe / event_output
- end_time

{reference}
{RULES}
"""


def p2_shared(plan: dict[str, Any], manifest: dict[str, Any], task_context: dict[str, Any] | None) -> str:
    platform_layer = plan["layers"]["platform_layer"]
    sensor_layer = {item["component_id"]: item for item in plan["layers"]["sensor_layer"].get("components", [])}
    weapon_layer = {item["component_id"]: item for item in plan["layers"]["weapon_layer"].get("components", [])}
    mission_layer = plan["layers"]["mission_layer"]
    processor_layer = {item["component_id"]: item for item in mission_layer.get("processors", [])}
    comm_layer = {item["component_id"]: item for item in mission_layer.get("comms", [])}

    entity_specs = []
    for entity in platform_layer.get("entities", []):
        component_specs = []
        for family, ids in entity.get("component_families", {}).items():
            for component_id in ids:
                item = (
                    sensor_layer.get(component_id)
                    or weapon_layer.get(component_id)
                    or processor_layer.get(component_id)
                    or comm_layer.get(component_id)
                )
                if item:
                    component_specs.append(
                        {
                            "family": family,
                            "component_id": component_id,
                            "grounding_target": item.get("grounding", {}).get("grounding_target", {}),
                            "constraints": item.get("implementation_constraints", {}),
                        }
                    )
        entity_specs.append(
            {
                "entity_id": entity["entity_id"],
                "platform_type_name": manifest["platform_types"][entity["entity_id"]],
                "platform_base": entity.get("platform_grounding", {}).get("grounding_target", {}),
                "platform_constraints": entity.get("platform_constraints", {}),
                "components": component_specs,
            }
        )

    reference = _reference_section(task_context)
    return f"""PHASE 2: Generate ONLY shared declarations.

Platform type manifest:
{json.dumps(entity_specs, ensure_ascii=False, indent=2)}

Generate ONLY:
- platform_type declarations using the EXACT platform_type_name values above
- inline mover / sensor / weapon / processor / comm declarations inside each platform_type
- standalone shared blocks when required by constraints

Do NOT generate:
- platform instances
- route blocks
- task bindings
- event_pipe / event_output
- end_time

{_syntax_examples()}

{reference}
{RULES}
"""


def p3_platform(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    entity: dict[str, Any],
    location_index: dict[str, dict[str, Any]],
    task_context: dict[str, Any] | None,
) -> str:
    location = location_index.get(entity.get("initial_location_ref", ""))
    route_ref = entity.get("route_ref", "")
    reference = _reference_section(task_context)
    return f"""PHASE 3: Generate ONLY one platform instance block for this entity.

Entity:
{json.dumps(entity, ensure_ascii=False, indent=2)}

Platform naming contract:
- platform instance name: {manifest["platform_instances"][entity["entity_id"]]}
- platform type name: {manifest["platform_types"][entity["entity_id"]]}

Resolved initial location:
{json.dumps(location or {}, ensure_ascii=False, indent=2)}

Rules:
- Emit EXACTLY one platform block for this entity: platform <NAME> <TYPE>
- Set side and initial position.
- If route_ref is present ({route_ref or "none"}), include a route block INSIDE the platform.
- Do not put platform_type as a command inside a platform block.
- Do not emit event_pipe / event_output / end_time.

{_syntax_examples()}

{reference}
{RULES}
"""


def p4_task(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    task: dict[str, Any],
    route_index: dict[str, dict[str, Any]],
    platform_layer: dict[str, Any],
    task_context: dict[str, Any] | None,
) -> str:
    assignees = []
    for entity in platform_layer.get("entities", []):
        if entity["entity_id"] in task.get("assignee_refs", []):
            assignees.append(
                {
                    "entity_id": entity["entity_id"],
                    "platform_instance_name": manifest["platform_instances"][entity["entity_id"]],
                    "platform_type_name": manifest["platform_types"][entity["entity_id"]],
                    "route_ref": entity.get("route_ref", ""),
                }
            )
    task_routes = []
    for assignee in assignees:
        route_id = assignee.get("route_ref")
        if route_id and route_id in route_index:
            task_routes.append(route_index[route_id])

    logic = plan["layers"].get("logic_layer", {})
    evaluation = plan["layers"].get("evaluation_layer", {})
    reference = _reference_section(task_context)
    return f"""PHASE 4: Generate ONLY task-specific overlays for one task.

Task:
{json.dumps(task, ensure_ascii=False, indent=2)}

Assignee platform mapping:
{json.dumps(assignees, ensure_ascii=False, indent=2)}

Relevant route definitions:
{json.dumps(task_routes, ensure_ascii=False, indent=2)}

Logic model:
{json.dumps(logic, ensure_ascii=False, indent=2)}

Evaluation model:
{json.dumps(evaluation, ensure_ascii=False, indent=2)}

Generate ONLY the pieces that belong to this task:
- route blocks
- task-specific processor / behavior / script overlays
- task binding snippets
- communication or coordination snippets needed for this task

Important:
- If the reference family realizes mission logic through processor scripts / execute blocks / edit blocks, follow that pattern.
- Do NOT invent simplified fake DSL like `task_group`, `assigned_to`, or `parameter message_flow`.

Do NOT regenerate:
- side / location declarations
- platform_type declarations
- platform instance blocks
- event_pipe / event_output
- end_time

The output can be partial snippets. The final assembly stage will merge them.

{reference}
{RULES}
"""


def p5_assembly(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    skeleton_text: str,
    shared_text: str,
    platform_texts: list[dict[str, Any]],
    task_texts: list[dict[str, Any]],
    task_context: dict[str, Any] | None,
) -> str:
    scaffold = plan["layers"]["scenario_scaffold"]
    assembly = plan["layers"]["scenario_assembly"]
    eval_layer = plan["layers"].get("evaluation_layer", {})
    reference = _reference_section(task_context)
    return f"""PHASE 5: Merge all generated chunks into ONE complete AFSIM script.

Manifest:
{json.dumps(manifest, ensure_ascii=False, indent=2)}

Requested outputs:
{json.dumps(assembly.get("outputs", []), ensure_ascii=False)}

Expected events:
{json.dumps(eval_layer.get("expected_events", []), ensure_ascii=False, indent=2)}

Evaluation:
{json.dumps(eval_layer.get("evaluation", {}), ensure_ascii=False, indent=2)}

Duration / end_time:
{json.dumps(scaffold.get("duration", {}), ensure_ascii=False)}

Chunk A - scenario skeleton:
```afsim
{skeleton_text}
```

Chunk B - shared declarations:
```afsim
{shared_text}
```

Chunk C - platform instances:
{json.dumps(platform_texts, ensure_ascii=False, indent=2)}

Chunk D - task overlays:
{json.dumps(task_texts, ensure_ascii=False, indent=2)}

Instructions:
1. Merge all chunks into one complete script. Place platform_type declarations FIRST, then platform instances, then event_pipe/event_output, then end_time.
2. Preserve the exact platform_type names and platform instance names from the manifest.
3. Each platform instance must have: side, position (with coordinates+units), and optionally a route.
4. Do NOT invent new platforms, components, or tasks.
5. The final script MUST NOT contain: mission, task, writeln, extends, sensitivity, scan_mode, engage_iff_permissions, on_message, end_state, shape, or any C++ syntax.
6. sensor references inside platform use inline form: sensor NAME on end_sensor (ONE line).
7. Emit exactly one end_time line as the LAST line of the script at top level (depth 0).
8. CRITICAL: Return a complete AFSIM script. No markdown fences.

{_syntax_examples()}

{reference}
{RULES}
"""


def _run_serial_phase(
    client: LLMClient,
    phase_dir: Path,
    phase_key: str,
    prompt: str,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    start = time.perf_counter()
    text = _chat_text(client, prompt, max_tokens=max_tokens)
    elapsed = time.perf_counter() - start
    _write_text(phase_dir / "prompt.txt", prompt)
    _write_text(phase_dir / "generated.txt", text)
    record = {
        "phase": phase_key,
        "artifact_dir": str(phase_dir),
        "seconds": round(elapsed, 3),
    }
    _write_json(phase_dir / "record.json", record)
    return {"text": text, "record": record}


def _run_parallel_chunks(
    client: LLMClient,
    base_dir: Path,
    phase_key: str,
    work_items: list[dict[str, Any]],
    max_tokens: int = 8192,
) -> list[dict[str, Any]]:
    if not work_items:
        return []

    def _worker(item: dict[str, Any]) -> dict[str, Any]:
        item_dir = base_dir / item["item_id"]
        start = time.perf_counter()
        text = _chat_text(client, item["prompt"], max_tokens=max_tokens)
        elapsed = time.perf_counter() - start
        _write_text(item_dir / "prompt.txt", item["prompt"])
        _write_text(item_dir / "generated.txt", text)
        record = {
            "phase": phase_key,
            "item_id": item["item_id"],
            "seconds": round(elapsed, 3),
            "artifact_dir": str(item_dir),
        }
        _write_json(item_dir / "record.json", record)
        return {
            "item_id": item["item_id"],
            "text": text,
            "record": record,
        }

    results: list[dict[str, Any]] = []
    max_workers = min(25, len(work_items))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_worker, item) for item in work_items]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["item_id"])
    return results


def _postprocess_assembly(script_text: str, manifest: dict) -> str:
    """Deterministic post-processing: dedup merged-chunk declarations.

    Runs AFTER Phase 5 merge, BEFORE static checking.  Does NOT call any LLM —
    purely rule-based dedup that is cheap and safe to run every time.

    Handles the common E010 pattern where Phase 3 (platform chunks) and
    Phase 4 (task chunks) both emit the same template declaration during
    parallel generation, and Phase 5 naively concatenates them.

    Reference repair (E003) is NOT handled here — that requires LLM-level
    understanding and is left to the repair pipeline.
    """
    import re as _re

    lines = script_text.splitlines()
    seen_declarations: dict[str, int] = {}  # key -> first line index
    deduped: list[str] = []
    skip_until_next_block = False
    skip_depth = 0
    depth = 0

    # Block-start keywords that declare a named entity (can be duplicated
    # across chunks during merge).
    _DECLARE_KEYWORDS = {
        "platform_type", "mover", "sensor", "weapon", "processor", "comm",
        "antenna_pattern", "transmitter", "receiver", "platform",
        "constant_pattern", "event_pipe", "event_output",
    }
    _NESTABLE = {"platform", "scenario", "side", "route", "script",
                 "script_interface", "processor", "behavior_tree",
                 "advanced_behavior_tree", "advanced_behavior"}

    for line_no, raw in enumerate(lines):
        line = raw.strip()
        parts = line.split()
        head = parts[0] if parts else ""

        if skip_until_next_block:
            if head in _NESTABLE or head in _DECLARE_KEYWORDS:
                skip_depth += 1
            elif head.startswith("end_"):
                skip_depth -= 1
                if skip_depth <= 0:
                    skip_until_next_block = False
                    skip_depth = 0
            continue

        # Dedup BEFORE depth tracking — otherwise platform/processor/behavior_tree
        # (which are in both _DECLARE_KEYWORDS and _NESTABLE) would never be checked
        # because depth was just incremented.
        if depth == 0 and head in _DECLARE_KEYWORDS and len(parts) >= 2:
            name = parts[1]
            key = f"{head}:{name}"
            if key in seen_declarations:
                skip_until_next_block = True
                skip_depth = 1
                continue
            seen_declarations[key] = line_no

        if head in _NESTABLE:
            depth += 1
        elif head.startswith("end_"):
            depth = max(0, depth - 1)

        deduped.append(raw)

    # Relocate misplaced end_time to the last line at depth 0 (fixes E002).
    end_time_lines = []
    cleaned = []
    for raw in deduped:
        stripped = raw.strip()
        if stripped.startswith("end_time"):
            end_time_lines.append(stripped)
        else:
            cleaned.append(raw)
    if end_time_lines:
        # Keep one end_time with the longest duration (heuristic), drop others
        best = max(end_time_lines, key=len) if end_time_lines else "end_time 120 sec"
        cleaned.append(best)

    return "\n".join(cleaned)


def execute_layered_generation(
    plan: dict[str, Any],
    client: LLMClient,
    run_dir: Path,
    task_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layers_dir = run_dir / "layers"
    layers_dir.mkdir(parents=True, exist_ok=True)

    manifest = _make_manifest(plan)
    _write_json(run_dir / "manifest.json", manifest)

    platform_layer = plan["layers"]["platform_layer"]
    mission_layer = plan["layers"]["mission_layer"]
    location_index = {
        item["id"]: item for item in plan["layers"]["scenario_scaffold"].get("locations", [])
        if item.get("id")
    }
    route_index = {item["route_id"]: item for item in mission_layer.get("routes", [])}

    phase1 = _run_serial_phase(
        client,
        layers_dir / "phase1_skeleton",
        "phase1_skeleton",
        p1_skeleton(plan, manifest, task_context),
    )
    phase2 = _run_serial_phase(
        client,
        layers_dir / "phase2_shared",
        "phase2_shared",
        p2_shared(plan, manifest, task_context),
    )

    platform_items = [
        {
            "item_id": entity["entity_id"],
            "prompt": p3_platform(plan, manifest, entity, location_index, task_context),
        }
        for entity in platform_layer.get("entities", [])
    ]
    phase3 = _run_parallel_chunks(
        client,
        layers_dir / "phase3_platforms",
        "phase3_platforms",
        platform_items,
    )

    task_items = [
        {
            "item_id": task["task_id"],
            "prompt": p4_task(plan, manifest, task, route_index, platform_layer, task_context),
        }
        for task in mission_layer.get("tasks", [])
    ]
    phase4 = _run_parallel_chunks(
        client,
        layers_dir / "phase4_tasks",
        "phase4_tasks",
        task_items,
    )

    assembly_prompt = p5_assembly(
        plan,
        manifest,
        phase1["text"],
        phase2["text"],
        phase3,
        phase4,
        task_context,
    )
    phase5 = _run_serial_phase(
        client,
        layers_dir / "phase5_assembly",
        "phase5_assembly",
        assembly_prompt,
        max_tokens=12288,
    )

    final_path = run_dir / "final_script.txt"
    final_text = postprocess_script(phase5["text"])
    _write_text(final_path, final_text)

    result = {
        "version": "hierarchical_generation_executor_v1",
        "plan_version": plan.get("version", ""),
        "source": plan.get("source", {}),
        "mode": "independent_layers_then_merge",
        "chunk_count": 2 + len(phase3) + len(phase4) + 1,
        "parallel_groups": {
            "platforms": len(phase3),
            "tasks": len(phase4),
        },
        "layers": [
            phase1["record"],
            phase2["record"],
            *[item["record"] for item in phase3],
            *[item["record"] for item in phase4],
            phase5["record"],
        ],
        "final_script_path": str(final_path),
    }
    _write_json(run_dir / "execution_result.json", result)
    return result


def run_on_ir_example(example_id: str, client: LLMClient, output_dir: Path | None = None) -> dict[str, Any]:
    from .generation_planner import load_ir_from_examples

    ir_source = load_ir_from_examples(example_id)
    plan = build_generation_plan(ir_source)
    if not plan["ready_for_generation"]:
        raise RuntimeError(f"Plan not ready: {plan.get('manual_review_items', [])}")
    run_dir = output_dir or (ROOT / "layered_generation_artifacts_v1" / example_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "generation_plan.json", plan)
    return execute_layered_generation(plan, client, run_dir)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--example-id", required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    client = LLMClient.from_env()
    result = run_on_ir_example(
        args.example_id,
        client,
        Path(args.output_dir) if args.output_dir else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
