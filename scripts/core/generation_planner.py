#!/usr/bin/env python3
"""
Task-011: Hierarchical Generation Planner v1

Build a layered generation plan from AFSIM-IR plus grounding helpers.
"""

import argparse
import json
from pathlib import Path

from .grounding import (
    normalize_component_family,
    resolve_component,
    resolve_platform,
    resolve_side,
    resolve_task,
)


ROOT = Path(__file__).resolve().parent.parent.parent
IR_EXAMPLES_V1_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"
IR_EXAMPLES_V2_PATH = ROOT / "docs" / "machine" / "ir_examples_v2.jsonl"


def load_ir_from_examples(example_id: str):
    for source_type, path in [("ir_examples_v2", IR_EXAMPLES_V2_PATH), ("ir_examples_v1", IR_EXAMPLES_V1_PATH)]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("id") == example_id:
                return {
                    "source_type": source_type,
                    "source_id": example_id,
                    "source_task_id": row.get("source_task_id"),
                    "ir": row.get("ir", {}),
                }
    raise ValueError(f"Example id not found: {example_id}")


def load_ir_from_file(path: Path):
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    if "ir" in data and isinstance(data["ir"], dict):
        ir = data["ir"]
    else:
        ir = data
    return {
        "source_type": "file",
        "source_id": str(path),
        "source_task_id": data.get("source_task_id"),
        "ir": ir,
    }


def index_components(ir: dict):
    component_index = {}
    for family_name, items in ir.get("components", {}).items():
        family = normalize_component_family(family_name)
        for item in items:
            component_index[item["id"]] = {"family": family, "item": item}
    return component_index


def summarize_component_plan(component_id: str, family: str, item: dict):
    grounding = resolve_component(
        family,
        label=item.get("role", ""),
        type_hint=item.get("type_hint", ""),
    )
    unresolved = []
    if not grounding["matched"]:
        unresolved.append(
            {
                "kind": "component_grounding",
                "component_id": component_id,
                "family": family,
                "type_hint": item.get("type_hint", ""),
                "role": item.get("role", ""),
            }
        )
    return {
        "component_id": component_id,
        "family": family,
        "role": item.get("role"),
        "type_hint": item.get("type_hint"),
        "parameters": item.get("parameters", {}),
        "grounding": grounding,
        "implementation_constraints": grounding.get("implementation_constraints", {}),
        "unresolved_items": unresolved,
    }


def build_platform_layer(ir: dict, component_index: dict):
    entities_plan = []
    unresolved = []

    valid_locations = {row["id"] for row in ir.get("locations", [])}
    valid_routes = {row["id"] for row in ir.get("routes", [])}

    for entity in ir.get("entities", []):
        side = resolve_side(entity.get("side", ""))
        platform = resolve_platform(
            label=entity.get("role", ""),
            platform_type_hint=entity.get("platform_type_hint", ""),
        )

        entity_unresolved = []
        if not side["matched"]:
            entity_unresolved.append(
                {"kind": "side_grounding", "entity_id": entity["id"], "side": entity.get("side", "")}
            )
        if not platform["matched"]:
            entity_unresolved.append(
                {
                    "kind": "platform_grounding",
                    "entity_id": entity["id"],
                    "role": entity.get("role", ""),
                    "platform_type_hint": entity.get("platform_type_hint", ""),
                }
            )
        if entity.get("initial_location_ref") and entity["initial_location_ref"] not in valid_locations:
            entity_unresolved.append(
                {
                    "kind": "missing_location_ref",
                    "entity_id": entity["id"],
                    "location_ref": entity.get("initial_location_ref"),
                }
            )
        if entity.get("route_ref") and entity["route_ref"] not in valid_routes:
            entity_unresolved.append(
                {"kind": "missing_route_ref", "entity_id": entity["id"], "route_ref": entity.get("route_ref")}
            )

        referenced_components = []
        missing_component_refs = []
        component_families = {"mover": [], "sensor": [], "weapon": [], "processor": [], "comm": []}

        for ref in entity.get("component_refs", []):
            component_row = component_index.get(ref)
            if not component_row:
                missing_component_refs.append(ref)
                entity_unresolved.append(
                    {"kind": "missing_component_ref", "entity_id": entity["id"], "component_ref": ref}
                )
                continue
            referenced_components.append(ref)
            component_families.setdefault(component_row["family"], []).append(ref)

        entities_plan.append(
            {
                "entity_id": entity["id"],
                "role": entity.get("role"),
                "domain": entity.get("domain"),
                "quantity": entity.get("quantity"),
                "side": side,
                "platform_grounding": platform,
                "platform_constraints": platform.get("implementation_constraints", {}),
                "initial_location_ref": entity.get("initial_location_ref"),
                "route_ref": entity.get("route_ref"),
                "component_refs": referenced_components,
                "component_families": component_families,
                "missing_component_refs": missing_component_refs,
                "ready": not entity_unresolved,
                "unresolved_items": entity_unresolved,
            }
        )
        unresolved.extend(entity_unresolved)

    return {"layer_name": "platform_layer", "entities": entities_plan, "ready": not unresolved, "unresolved_items": unresolved}


def build_component_layer(ir: dict, component_index: dict, family: str, layer_name: str):
    planned = []
    unresolved = []
    referenced_ids = set()

    for entity in ir.get("entities", []):
        for ref in entity.get("component_refs", []):
            row = component_index.get(ref)
            if row and row["family"] == family:
                referenced_ids.add(ref)

    for component_id in sorted(referenced_ids):
        row = component_index[component_id]
        item_plan = summarize_component_plan(component_id, family, row["item"])
        planned.append(item_plan)
        unresolved.extend(item_plan["unresolved_items"])

    return {
        "layer_name": layer_name,
        "components": planned,
        "ready": not unresolved,
        "unresolved_items": unresolved,
    }


def build_mission_layer(ir: dict, component_index: dict):
    unresolved = []

    route_ids = {row["id"] for row in ir.get("routes", [])}
    entity_ids = {row["id"] for row in ir.get("entities", [])}

    processors = []
    comms = []
    tasks = []

    for component_id, row in component_index.items():
        if row["family"] == "processor":
            plan = summarize_component_plan(component_id, "processor", row["item"])
            processors.append(plan)
            unresolved.extend(plan["unresolved_items"])
        elif row["family"] == "comm":
            plan = summarize_component_plan(component_id, "comm", row["item"])
            comms.append(plan)
            unresolved.extend(plan["unresolved_items"])

    for task in ir.get("tasks", []):
        task_grounding = resolve_task(task.get("type", ""))
        task_unresolved = []
        if not task_grounding["matched"]:
            task_unresolved.append(
                {"kind": "task_grounding", "task_id": task["id"], "task_type": task.get("type", "")}
            )

        for ref in task.get("assignee_refs", []):
            if ref not in entity_ids:
                task_unresolved.append({"kind": "missing_assignee_ref", "task_id": task["id"], "entity_ref": ref})
        for ref in task.get("target_refs", []):
            if ref not in entity_ids:
                task_unresolved.append({"kind": "missing_target_ref", "task_id": task["id"], "entity_ref": ref})
        for ref in task.get("location_refs", []):
            if ref not in route_ids and ref not in {loc["id"] for loc in ir.get("locations", [])}:
                task_unresolved.append({"kind": "missing_task_location_ref", "task_id": task["id"], "location_ref": ref})

        tasks.append(
            {
                "task_id": task["id"],
                "task_type": task.get("type"),
                "grounding": task_grounding,
                "implementation_constraints": task_grounding.get("implementation_constraints", {}),
                "assignee_refs": task.get("assignee_refs", []),
                "target_refs": task.get("target_refs", []),
                "location_refs": task.get("location_refs", []),
                "parameters": task.get("parameters", {}),
                "ready": not task_unresolved,
                "unresolved_items": task_unresolved,
            }
        )
        unresolved.extend(task_unresolved)

    routes = []
    for route in ir.get("routes", []):
        route_unresolved = []
        for waypoint in route.get("waypoints", []):
            location_ref = waypoint.get("location_ref")
            if location_ref and location_ref not in {loc["id"] for loc in ir.get("locations", [])}:
                route_unresolved.append(
                    {"kind": "missing_waypoint_location_ref", "route_id": route["id"], "location_ref": location_ref}
                )
        routes.append(
            {
                "route_id": route["id"],
                "kind": route.get("kind"),
                "waypoint_count": len(route.get("waypoints", [])),
                "ready": not route_unresolved,
                "unresolved_items": route_unresolved,
            }
        )
        unresolved.extend(route_unresolved)

    return {
        "layer_name": "mission_layer",
        "processors": processors,
        "comms": comms,
        "routes": routes,
        "tasks": tasks,
        "ready": not unresolved,
        "unresolved_items": unresolved,
    }


def build_logic_layer(ir: dict):
    """Task-018: extract v2 logic fields — behavior_rules, state_machines, engagement, triggers."""
    logic = ir.get("logic", {})
    if not isinstance(logic, dict) or not logic:
        return {
            "layer_name": "logic_layer",
            "behavior_rules": [],
            "state_machines": [],
            "engagement_logic": {},
            "trigger_logic": [],
            "ready": True,
            "unresolved_items": [],
        }

    entity_ids = {row["id"] for row in ir.get("entities", [])}
    task_ids = {row["id"] for row in ir.get("tasks", [])}
    component_ids = set()
    for family_items in ir.get("components", {}).values():
        for item in family_items:
            component_ids.add(item.get("id", ""))

    unresolved = []
    behavior_rules = []
    for rule in logic.get("behavior_rules", []):
        applies_to = rule.get("applies_to", [])
        rule_unresolved = [
            {"kind": "missing_behavior_ref", "rule_id": rule.get("id"), "ref": ref}
            for ref in applies_to
            if ref not in entity_ids and ref not in task_ids
        ]
        behavior_rules.append({
            "rule_id": rule.get("id"),
            "description": rule.get("description", ""),
            "priority": rule.get("priority", 0),
            "applies_to": applies_to,
            "ready": not rule_unresolved,
            "unresolved_items": rule_unresolved,
        })
        unresolved.extend(rule_unresolved)

    state_machines = []
    for sm in logic.get("state_machines", []):
        sm_unresolved = []
        proc_ref = sm.get("processor_ref", "")
        if proc_ref and proc_ref not in component_ids:
            sm_unresolved.append({"kind": "missing_processor_ref", "state_machine_id": sm.get("id"), "ref": proc_ref})
        state_machines.append({
            "state_machine_id": sm.get("id"),
            "processor_ref": proc_ref,
            "initial_state": sm.get("initial_state"),
            "state_count": len(sm.get("states", [])),
            "ready": not sm_unresolved,
            "unresolved_items": sm_unresolved,
        })
        unresolved.extend(sm_unresolved)

    engagement = logic.get("engagement_logic", {})
    engagement_summary = {}
    if engagement:
        engagement_summary = {
            "style": engagement.get("style", ""),
            "target_prioritization": engagement.get("target_prioritization", []),
            "rule_count": len(engagement.get("rules", [])),
        }

    trigger_rules = []
    for tr in logic.get("trigger_logic", []):
        tr_unresolved = []
        for ref in tr.get("source_refs", []):
            if ref not in entity_ids and ref not in component_ids:
                tr_unresolved.append({"kind": "missing_trigger_source", "trigger_id": tr.get("id"), "ref": ref})
        trigger_rules.append({
            "trigger_id": tr.get("id"),
            "trigger": tr.get("trigger"),
            "source_refs": tr.get("source_refs", []),
            "target_refs": tr.get("target_refs", []),
            "ready": not tr_unresolved,
            "unresolved_items": tr_unresolved,
        })
        unresolved.extend(tr_unresolved)

    return {
        "layer_name": "logic_layer",
        "behavior_rules": behavior_rules,
        "state_machines": state_machines,
        "engagement_logic": engagement_summary,
        "trigger_logic": trigger_rules,
        "ready": not unresolved,
        "unresolved_items": unresolved,
    }


def build_evaluation_layer(ir: dict):
    """Task-018: extract v2 evaluation fields — mission_phases, success_criteria, observation_metrics."""
    evaluation = ir.get("evaluation", {})
    if not isinstance(evaluation, dict) or not evaluation:
        return {
            "layer_name": "evaluation_layer",
            "mission_phases": [],
            "success_criteria": {},
            "observation_metrics": [],
            "ready": True,
            "unresolved_items": [],
        }

    unresolved = []

    phases = []
    phase_ids = set()
    for phase in evaluation.get("mission_phases", []):
        phase_ids.add(phase.get("id"))
        objectives = phase.get("objectives", [])
        phases.append({
            "phase_id": phase.get("id"),
            "name": phase.get("name", ""),
            "order": phase.get("order", 0),
            "objective_count": len(objectives),
            "required_objectives": [o["id"] for o in objectives if o.get("required_for_success", True)],
        })

    success = evaluation.get("success_criteria", {})
    success_summary = {}
    if success:
        required_phases = success.get("minimum_phases_required", [])
        missing_phases = [p for p in required_phases if p not in phase_ids]
        unresolved.extend(
            {"kind": "missing_success_phase_ref", "phase_id": p} for p in missing_phases
        )
        success_summary = {
            "overall_condition": success.get("overall_condition", ""),
            "minimum_phases_required": required_phases,
            "score_thresholds": success.get("score_thresholds", {}),
        }

    metrics = []
    for metric in evaluation.get("observation_metrics", []):
        entity_ids = {row["id"] for row in ir.get("entities", [])}
        metric_unresolved = []
        for ref in metric.get("target_refs", []):
            if ref not in entity_ids:
                metric_unresolved.append({"kind": "missing_metric_target_ref", "metric_id": metric.get("id"), "ref": ref})
        metrics.append({
            "metric_id": metric.get("id"),
            "metric_type": metric.get("metric_type"),
            "aggregation": metric.get("aggregation"),
            "threshold": metric.get("threshold"),
            "ready": not metric_unresolved,
            "unresolved_items": metric_unresolved,
        })
        unresolved.extend(metric_unresolved)

    return {
        "layer_name": "evaluation_layer",
        "mission_phases": phases,
        "success_criteria": success_summary,
        "observation_metrics": metrics,
        "ready": not unresolved,
        "unresolved_items": unresolved,
    }


def build_scenario_assembly(ir: dict, layers: list[dict]):
    unresolved = []
    layer_readiness = {layer["layer_name"]: layer["ready"] for layer in layers}
    required_order = [
        "scenario_scaffold",
        "platform_layer",
        "sensor_layer",
        "weapon_layer",
        "mission_layer",
        "scenario_assembly",
    ]

    if not ir.get("scenario", {}).get("duration"):
        unresolved.append({"kind": "missing_duration", "field": "scenario.duration"})

    outputs = ir.get("scenario", {}).get("outputs", [])

    return {
        "layer_name": "scenario_assembly",
        "required_order": required_order,
        "end_time": ir.get("scenario", {}).get("duration"),
        "outputs": outputs,
        "layer_readiness": layer_readiness,
        "ready": not unresolved and all(layer_readiness.values()),
        "unresolved_items": unresolved,
    }


def build_generation_plan(ir_source: dict):
    ir = ir_source["ir"]
    component_index = index_components(ir)

    scenario_scaffold = {
        "layer_name": "scenario_scaffold",
        "scenario_name": ir.get("scenario", {}).get("name"),
        "description": ir.get("scenario", {}).get("description"),
        "duration": ir.get("scenario", {}).get("duration"),
        "domains": ir.get("scenario", {}).get("domains", []),
        "outputs": ir.get("scenario", {}).get("outputs", []),
        "side_ids": [row.get("id") for row in ir.get("sides", [])],
        "location_ids": [row.get("id") for row in ir.get("locations", [])],
        "locations": [{"id": row.get("id"), "kind": row.get("kind"), "position": row.get("position")} for row in ir.get("locations", [])],
        "constraint_keys": sorted(ir.get("constraints", {}).keys()),
        "ready": bool(ir.get("scenario", {}).get("name") and ir.get("scenario", {}).get("duration")),
        "unresolved_items": [],
    }

    platform_layer = build_platform_layer(ir, component_index)
    sensor_layer = build_component_layer(ir, component_index, "sensor", "sensor_layer")
    weapon_layer = build_component_layer(ir, component_index, "weapon", "weapon_layer")
    mission_layer = build_mission_layer(ir, component_index)
    logic_layer = build_logic_layer(ir)
    evaluation_layer = build_evaluation_layer(ir)
    assembly_layer = build_scenario_assembly(
        ir,
        [scenario_scaffold, platform_layer, sensor_layer, weapon_layer, mission_layer, logic_layer, evaluation_layer],
    )

    manual_review_items = []
    for layer in [platform_layer, sensor_layer, weapon_layer, mission_layer, logic_layer, evaluation_layer, assembly_layer]:
        manual_review_items.extend(layer["unresolved_items"])

    ready_for_generation = (
        scenario_scaffold["ready"]
        and platform_layer["ready"]
        and sensor_layer["ready"]
        and weapon_layer["ready"]
        and mission_layer["ready"]
        and logic_layer["ready"]
        and evaluation_layer["ready"]
        and assembly_layer["ready"]
    )

    return {
        "version": "hierarchical_generation_plan_v1",
        "source": {
            "source_type": ir_source["source_type"],
            "source_id": ir_source["source_id"],
            "source_task_id": ir_source.get("source_task_id"),
        },
        "generation_order": [
            "scenario_scaffold",
            "platform_layer",
            "sensor_layer",
            "weapon_layer",
            "mission_layer",
            "logic_layer",
            "evaluation_layer",
            "scenario_assembly",
        ],
        "layers": {
            "scenario_scaffold": scenario_scaffold,
            "platform_layer": platform_layer,
            "sensor_layer": sensor_layer,
            "weapon_layer": weapon_layer,
            "mission_layer": mission_layer,
            "logic_layer": logic_layer,
            "evaluation_layer": evaluation_layer,
            "scenario_assembly": assembly_layer,
        },
        "manual_review_items": manual_review_items,
        "ready_for_generation": ready_for_generation,
    }


def main():
    parser = argparse.ArgumentParser(description="Build layered generation plan from AFSIM-IR.")
    parser.add_argument("--example-id", help="IR example id from docs/machine/ir_examples_v1.jsonl")
    parser.add_argument("--ir-json", help="Path to JSON file containing raw IR or wrapper object with `ir`.")
    parser.add_argument("--output", help="Optional output path for generated plan JSON.")
    args = parser.parse_args()

    if not args.example_id and not args.ir_json:
        raise SystemExit("Provide --example-id or --ir-json.")

    if args.example_id:
        ir_source = load_ir_from_examples(args.example_id)
    else:
        ir_source = load_ir_from_file(Path(args.ir_json))

    plan = build_generation_plan(ir_source)
    payload = json.dumps(plan, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
