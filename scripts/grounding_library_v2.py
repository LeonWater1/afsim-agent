#!/usr/bin/env python3
"""
Task-019: Grounding Library v2

Upgraded grounding with match levels (full/partial/unresolved), implementation
constraints, companion requirements, and unresolved reasons.  Reads the richer
entity_mapping_v2.json and exposes resolve_* functions that return structured
results with reasons for every match level.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from afsim_context_rules_v1 import derive_grounding_constraints


ROOT = Path(__file__).resolve().parent.parent
MAPPING_V2_PATH = ROOT / "docs" / "machine" / "entity_mapping_v2.json"
MAPPING_V1_PATH = ROOT / "docs" / "machine" / "entity_mapping_v1.json"
IR_EXAMPLES_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"


def load_mapping() -> dict[str, Any]:
    if MAPPING_V2_PATH.exists():
        return json.loads(MAPPING_V2_PATH.read_text(encoding="utf-8-sig"))
    return json.loads(MAPPING_V1_PATH.read_text(encoding="utf-8-sig"))


def normalize_label(text: str) -> str:
    return text.strip().lower().replace("-", "_").replace(" ", "_")


def _matches(label: str, aliases: list[str]) -> bool:
    normalized = normalize_label(label)
    return normalized in {normalize_label(item) for item in aliases}


def normalize_component_family(component_family: str) -> str:
    family = normalize_label(component_family)
    aliases = {
        "movers": "mover", "sensors": "sensor", "weapons": "weapon",
        "processors": "processor", "comms": "comm",
        "communications": "comm", "comm_system": "comm",
    }
    return aliases.get(family, family)


def _make_match(mapping_type: str, match_level: str, row: dict[str, Any] | None = None,
                input_value: str = "", reason: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "matched": match_level != "unresolved",
        "match_level": match_level,
        "mapping_type": mapping_type,
        "input": input_value,
    }
    if row:
        result["canonical_id"] = row.get("canonical_id", "")
        result["row"] = row
        result["match_confidence"] = row.get("match_confidence", "full")
        result["implementation_constraints"] = _merge_constraints(row)
        result["provenance"] = row.get("provenance", [])
        target = row.get("grounding_target", {})
        if target:
            result["grounding_target"] = target
    if reason:
        result["match_reason"] = reason
    return result


def _merge_constraints(row: dict[str, Any]) -> dict[str, Any]:
    """Merge mapping-level implementation_constraints with grounding_target info."""
    constraints: dict[str, Any] = dict(row.get("implementation_constraints", {}))
    target = row.get("grounding_target", {})
    if target.get("required_weapon_blocks"):
        constraints["required_weapon_blocks"] = target["required_weapon_blocks"]
    if target.get("required_spawned_platform_blocks"):
        constraints["required_spawned_platform_blocks"] = target["required_spawned_platform_blocks"]
    if target.get("required_spawned_processor_types"):
        constraints["required_spawned_processor_types"] = target["required_spawned_processor_types"]
    # Also include context-rule derived constraints
    ctx = derive_grounding_constraints(row)
    if ctx.get("preferred_declarations"):
        constraints["preferred_declarations"] = ctx["preferred_declarations"]
    if ctx.get("wsf_context_rules"):
        constraints["wsf_context_rules"] = ctx["wsf_context_rules"]
    return constraints


def resolve_side(label: str) -> dict[str, Any]:
    mapping = load_mapping()["sides"]
    for side_id, row in mapping.items():
        if _matches(label, [side_id, *row.get("aliases", [])]):
            return _make_match("side", row.get("match_confidence", "full"), row, label)
    return _make_match("side", "unresolved", input_value=label,
                       reason=f"Side '{label}' not found in mapping. Known: {list(mapping.keys())}")


def resolve_platform(label: str = "", platform_type_hint: str = "") -> dict[str, Any]:
    mapping = load_mapping()["platform_mappings"]
    input_value = label or platform_type_hint

    for platform_id, row in mapping.items():
        label_aliases = [platform_id, *row.get("match_labels", [])]
        hint_aliases = [platform_id, *row.get("platform_type_hints", [])]
        if label and _matches(label, label_aliases):
            return _make_match("platform", row.get("match_confidence", "full"), row, input_value)
        if platform_type_hint and _matches(platform_type_hint, hint_aliases):
            level = row.get("match_confidence", "full")
            reason = row.get("match_confidence_reason", "") if level == "partial" else ""
            return _make_match("platform", level, row, input_value, reason)

    return _make_match("platform", "unresolved", input_value=input_value,
                       reason=f"Platform '{input_value}' not found in mapping ({len(mapping)} platforms)")


def resolve_task(label: str) -> dict[str, Any]:
    mapping = load_mapping()["task_mappings"]
    for task_id, row in mapping.items():
        aliases = [task_id, *row.get("match_labels", []), *row.get("ir_task_types", [])]
        if _matches(label, aliases):
            level = row.get("match_confidence", "full")
            reason = row.get("match_confidence_reason", "") if level == "partial" else ""
            return _make_match("task", level, row, label, reason)
    return _make_match("task", "unresolved", input_value=label,
                       reason=f"Task '{label}' not found. Known types: {list(mapping.keys())}")


def resolve_component(component_family: str, label: str = "", type_hint: str = "") -> dict[str, Any]:
    component_groups = load_mapping()["component_mappings"]
    family = normalize_component_family(component_family)
    rows = component_groups.get(family, {})
    input_value = label or type_hint

    if label:
        for component_id, row in rows.items():
            aliases = [component_id, *row.get("match_labels", []), *row.get("type_hints", [])]
            if _matches(label, aliases):
                return _make_match(family, row.get("match_confidence", "full"), row, input_value)

    for component_id, row in rows.items():
        aliases = [component_id, *row.get("match_labels", []), *row.get("type_hints", [])]
        if type_hint and _matches(type_hint, aliases):
            level = row.get("match_confidence", "full")
            reason = row.get("match_confidence_reason", "") if level == "partial" else ""
            return _make_match(family, level, row, input_value, reason)

    return _make_match(family, "unresolved", input_value=input_value,
                       reason=f"Component '{input_value}' not found in {family} mappings ({len(rows)} entries)")


def collect_ir_coverage() -> dict[str, Any]:
    """Collect coverage stats across IR examples, with match_level breakdown."""
    if not IR_EXAMPLES_PATH.exists():
        return {"available": False}

    platform_hints: set[str] = set()
    task_hints: set[str] = set()
    component_hints: dict[str, set[str]] = {}
    skipped_lines: list[dict[str, Any]] = []

    for line_number, line in enumerate(IR_EXAMPLES_PATH.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            skipped_lines.append({"line": line_number, "error": f"{exc.msg} at column {exc.colno}"})
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

    # Resolve with match_level breakdown
    def _level_stats(hints, resolver, *args):
        full, partial, unresolved = [], [], []
        for hint in hints:
            r = resolver(*args, hint) if callable(resolver) else resolver(hint)
            level = r.get("match_level", "unresolved")
            if level == "full": full.append(hint)
            elif level == "partial": partial.append(hint)
            else: unresolved.append(hint)
        return {"full": sorted(full), "partial": sorted(partial), "unresolved": sorted(unresolved)}

    plat_stats = _level_stats(platform_hints, lambda h: resolve_platform(platform_type_hint=h))
    task_stats = _level_stats(task_hints, lambda h: resolve_task(h))
    comp_stats = {}
    for family, hints in component_hints.items():
        comp_stats[family] = _level_stats(hints, lambda h: resolve_component(family, type_hint=h))

    total_hints = len(platform_hints) + len(task_hints) + sum(len(h) for h in component_hints.values())
    total_full = len(plat_stats["full"]) + len(task_stats["full"]) + sum(len(c["full"]) for c in comp_stats.values())

    return {
        "available": True,
        "platform_hints_total": len(platform_hints),
        "task_hints_total": len(task_hints),
        "component_hints_total": sum(len(h) for h in component_hints.values()),
        "platform_coverage": plat_stats,
        "task_coverage": task_stats,
        "component_coverage": comp_stats,
        "total_hints": total_hints,
        "total_full_match": total_full,
        "coverage_rate": round(total_full / total_hints, 3) if total_hints else 0.0,
        "skipped_invalid_lines": skipped_lines,
    }


def validate_mapping() -> dict[str, Any]:
    mapping = load_mapping()
    errors = []
    if "match_levels" not in mapping:
        errors.append("missing match_levels definition")

    for platform_id, row in mapping["platform_mappings"].items():
        conf = row.get("match_confidence", "")
        if conf == "partial" and not row.get("match_confidence_reason"):
            errors.append(f"platform {platform_id} is partial but missing match_confidence_reason")

    coverage = collect_ir_coverage()
    total_unresolved = 0
    if coverage.get("available"):
        total_unresolved = (
            len(coverage["platform_coverage"]["unresolved"])
            + len(coverage["task_coverage"]["unresolved"])
            + sum(len(c["unresolved"]) for c in coverage["component_coverage"].values())
        )

    return {
        "ok": not errors,
        "errors": errors,
        "coverage": coverage,
        "unresolved_total": total_unresolved,
        "match_levels_supported": list(mapping.get("match_levels", {}).keys()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Grounding library v2 — richer entity resolution.")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--side", default="")
    parser.add_argument("--platform-hint", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--component-family", default="")
    parser.add_argument("--component-hint", default="")
    args = parser.parse_args()

    if args.validate:
        print(json.dumps(validate_mapping(), ensure_ascii=False, indent=2))
        return
    if args.coverage:
        print(json.dumps(collect_ir_coverage(), ensure_ascii=False, indent=2))
        return
    if args.side:
        print(json.dumps(resolve_side(args.side), ensure_ascii=False, indent=2))
    elif args.platform_hint:
        print(json.dumps(resolve_platform(platform_type_hint=args.platform_hint), ensure_ascii=False, indent=2))
    elif args.task:
        print(json.dumps(resolve_task(args.task), ensure_ascii=False, indent=2))
    elif args.component_family and args.component_hint:
        print(json.dumps(resolve_component(args.component_family, type_hint=args.component_hint), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(collect_ir_coverage(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
