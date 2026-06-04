#!/usr/bin/env python3
"""
Task-010: Grounding Library v1

This module loads docs/machine/entity_mapping_v1.json and provides lookup helpers for side,
platform, task, and component grounding.
"""

import argparse
import json
from pathlib import Path

from afsim_context_rules_v1 import derive_grounding_constraints


ROOT = Path(__file__).resolve().parent.parent
MAPPING_PATH = ROOT / "docs" / "machine" / "entity_mapping_v1.json"
IR_EXAMPLES_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"


def load_mapping():
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8-sig"))


def normalize_label(text: str) -> str:
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def _matches(label: str, aliases: list[str]) -> bool:
    normalized = normalize_label(label)
    return normalized in {normalize_label(item) for item in aliases}


def normalize_component_family(component_family: str) -> str:
    family = normalize_label(component_family)
    aliases = {
        "movers": "mover",
        "sensors": "sensor",
        "weapons": "weapon",
        "processors": "processor",
        "comms": "comm",
        "communications": "comm",
        "comm_system": "comm",
    }
    return aliases.get(family, family)


def resolve_side(label: str):
    mapping = load_mapping()["sides"]
    for side_id, row in mapping.items():
        if _matches(label, [side_id, *row.get("aliases", [])]):
            return {"matched": True, "mapping_type": "side", "canonical_id": row["canonical_id"], "row": row}
    return {"matched": False, "mapping_type": "side", "input": label}


def resolve_platform(label: str = "", platform_type_hint: str = ""):
    mapping = load_mapping()["platform_mappings"]
    for platform_id, row in mapping.items():
        label_aliases = [platform_id, *row.get("match_labels", [])]
        hint_aliases = [platform_id, *row.get("platform_type_hints", [])]
        if label and _matches(label, label_aliases):
            return {
                "matched": True,
                "mapping_type": "platform",
                "canonical_id": row["canonical_id"],
                "row": row,
                "implementation_constraints": derive_grounding_constraints(row),
            }
        if platform_type_hint and _matches(platform_type_hint, hint_aliases):
            return {
                "matched": True,
                "mapping_type": "platform",
                "canonical_id": row["canonical_id"],
                "row": row,
                "implementation_constraints": derive_grounding_constraints(row),
            }
    return {"matched": False, "mapping_type": "platform", "input": label or platform_type_hint}


def resolve_task(label: str):
    mapping = load_mapping()["task_mappings"]
    for task_id, row in mapping.items():
        aliases = [task_id, *row.get("match_labels", []), *row.get("ir_task_types", [])]
        if _matches(label, aliases):
            return {
                "matched": True,
                "mapping_type": "task",
                "canonical_id": row["canonical_id"],
                "row": row,
                "implementation_constraints": derive_grounding_constraints(row),
            }
    return {"matched": False, "mapping_type": "task", "input": label}


def resolve_component(component_family: str, label: str = "", type_hint: str = ""):
    component_groups = load_mapping()["component_mappings"]
    family = normalize_component_family(component_family)
    rows = component_groups.get(family, {})

    if label:
        for component_id, row in rows.items():
            aliases = [component_id, *row.get("match_labels", []), *row.get("type_hints", [])]
            if _matches(label, aliases):
                return {
                    "matched": True,
                    "mapping_type": family,
                    "canonical_id": row["canonical_id"],
                    "row": row,
                    "implementation_constraints": derive_grounding_constraints(row),
                }

    for component_id, row in rows.items():
        aliases = [component_id, *row.get("match_labels", []), *row.get("type_hints", [])]
        if type_hint and _matches(type_hint, aliases):
            return {
                "matched": True,
                "mapping_type": family,
                "canonical_id": row["canonical_id"],
                "row": row,
                "implementation_constraints": derive_grounding_constraints(row),
            }
    return {"matched": False, "mapping_type": family, "input": label or type_hint}


def collect_ir_coverage():
    if not IR_EXAMPLES_PATH.exists():
        return {"available": False}

    platform_hints = set()
    task_hints = set()
    component_hints: dict[str, set[str]] = {}
    skipped_lines = []

    for line_number, line in enumerate(IR_EXAMPLES_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            skipped_lines.append(
                {
                    "line": line_number,
                    "error": f"{exc.msg} at column {exc.colno}",
                }
            )
            continue
        ir = row.get("ir", {})

        for entity in ir.get("entities", []):
            hint = entity.get("platform_type_hint") or ""
            if hint:
                platform_hints.add(hint)

        for task in ir.get("tasks", []):
            hint = task.get("type") or ""
            if hint:
                task_hints.add(hint)

        for family_name, entries in ir.get("components", {}).items():
            family = normalize_component_family(family_name)
            for entry in entries:
                hint = entry.get("type_hint") or ""
                if hint:
                    component_hints.setdefault(family, set()).add(hint)

    unresolved_platforms = sorted(hint for hint in platform_hints if not resolve_platform(platform_type_hint=hint)["matched"])
    unresolved_tasks = sorted(hint for hint in task_hints if not resolve_task(hint)["matched"])

    unresolved_components = {}
    for family, hints in component_hints.items():
        missing = sorted(hint for hint in hints if not resolve_component(family, type_hint=hint)["matched"])
        if missing:
            unresolved_components[family] = missing

    return {
        "available": True,
        "platform_hints_total": len(platform_hints),
        "task_hints_total": len(task_hints),
        "component_hints_total": sum(len(hints) for hints in component_hints.values()),
        "unresolved_platform_hints": unresolved_platforms,
        "unresolved_task_hints": unresolved_tasks,
        "unresolved_component_hints": unresolved_components,
        "skipped_invalid_lines": skipped_lines,
    }


def validate_mapping():
    mapping = load_mapping()
    required_top_keys = {"version", "sides", "platform_mappings", "task_mappings", "component_mappings"}
    missing = sorted(required_top_keys - set(mapping))
    if missing:
        return {"ok": False, "missing_top_keys": missing}

    for side_id, row in mapping["sides"].items():
        if "canonical_id" not in row:
            return {"ok": False, "reason": f"side {side_id} missing canonical_id"}

    for platform_id, row in mapping["platform_mappings"].items():
        if "canonical_id" not in row:
            return {"ok": False, "reason": f"platform mapping {platform_id} missing canonical_id"}
        if "grounding_target" not in row:
            return {"ok": False, "reason": f"platform mapping {platform_id} missing grounding_target"}
        if "target_kind" not in row["grounding_target"] or "target_id" not in row["grounding_target"]:
            return {"ok": False, "reason": f"platform mapping {platform_id} grounding_target missing target_kind/target_id"}

    for task_id, row in mapping["task_mappings"].items():
        if "canonical_id" not in row:
            return {"ok": False, "reason": f"task mapping {task_id} missing canonical_id"}
        if "grounding_target" not in row:
            return {"ok": False, "reason": f"task mapping {task_id} missing grounding_target"}
        if "target_kind" not in row["grounding_target"] or "target_id" not in row["grounding_target"]:
            return {"ok": False, "reason": f"task mapping {task_id} grounding_target missing target_kind/target_id"}

    for family, family_rows in mapping["component_mappings"].items():
        for component_id, row in family_rows.items():
            if "canonical_id" not in row:
                return {"ok": False, "reason": f"component mapping {family}.{component_id} missing canonical_id"}
            if "grounding_target" not in row:
                return {"ok": False, "reason": f"component mapping {family}.{component_id} missing grounding_target"}
            if "target_kind" not in row["grounding_target"] or "target_id" not in row["grounding_target"]:
                return {"ok": False, "reason": f"component mapping {family}.{component_id} grounding_target missing target_kind/target_id"}

    coverage = collect_ir_coverage()
    if coverage.get("available"):
        unresolved_components = coverage.get("unresolved_component_hints", {})
        unresolved_any = bool(
            coverage.get("unresolved_platform_hints")
            or coverage.get("unresolved_task_hints")
            or any(unresolved_components.values())
        )
        return {"ok": not unresolved_any, "coverage": coverage}

    return {"ok": True, "coverage": coverage}


def main():
    parser = argparse.ArgumentParser(description="Grounding library v1 helper.")
    parser.add_argument("--validate", action="store_true", help="Validate docs/machine/entity_mapping_v1.json.")
    parser.add_argument("--side", default="", help="Resolve side label.")
    parser.add_argument("--platform", default="", help="Resolve platform label.")
    parser.add_argument("--platform-hint", default="", help="Resolve platform_type_hint.")
    parser.add_argument("--task", default="", help="Resolve task label.")
    parser.add_argument("--component-family", default="", help="Resolve component family such as mover/sensor/weapon/processor/comm.")
    parser.add_argument("--component", default="", help="Resolve component label.")
    parser.add_argument("--component-hint", default="", help="Resolve component type_hint.")
    args = parser.parse_args()

    if args.validate:
        print(json.dumps(validate_mapping(), ensure_ascii=False, indent=2))
        return

    if args.side:
        print(json.dumps(resolve_side(args.side), ensure_ascii=False, indent=2))
        return

    if args.platform or args.platform_hint:
        print(json.dumps(resolve_platform(args.platform, args.platform_hint), ensure_ascii=False, indent=2))
        return

    if args.task:
        print(json.dumps(resolve_task(args.task), ensure_ascii=False, indent=2))
        return

    if args.component_family and (args.component or args.component_hint):
        print(json.dumps(resolve_component(args.component_family, args.component, args.component_hint), ensure_ascii=False, indent=2))
        return

    print(json.dumps({"ok": True, "version": load_mapping()["version"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
