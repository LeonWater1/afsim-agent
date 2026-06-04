#!/usr/bin/env python3
"""
Task-010/Task-017 support: shared doc-driven context rules.

This module exposes machine-readable AFSIM legality rules that can be consumed
by grounding, generation, and static verification without task-specific logic.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "docs" / "machine" / "afsim_context_rules_v1.json"


@lru_cache(maxsize=1)
def load_context_rules() -> dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8-sig"))


def get_wsf_type_rule(wsf_type: str) -> dict[str, Any] | None:
    if not wsf_type:
        return None
    return load_context_rules().get("wsf_type_host_rules", {}).get(wsf_type)


def get_command_context_rule(command: str) -> dict[str, Any] | None:
    if not command:
        return None
    return load_context_rules().get("command_context_rules", {}).get(command)


def _collect_grounding_wsf_types(grounding_target: dict[str, Any]) -> list[str]:
    candidates = []
    for key in (
        "target_id",
        "backing_wsf_type",
        "backing_weapon_wsf_type",
        "wsf_base_type",
    ):
        value = grounding_target.get(key, "")
        if isinstance(value, str) and value.startswith("WSF_"):
            candidates.append(value)
    return list(dict.fromkeys(candidates))


def derive_grounding_constraints(row: dict[str, Any]) -> dict[str, Any]:
    grounding_target = row.get("grounding_target", {})
    if not isinstance(grounding_target, dict):
        return {}

    constraints = {
        "grounding_target_kind": grounding_target.get("target_kind", ""),
        "wsf_context_rules": [],
        "preferred_declarations": [],
    }

    for wsf_type in _collect_grounding_wsf_types(grounding_target):
        rule = get_wsf_type_rule(wsf_type)
        if not rule:
            continue
        constraints["wsf_context_rules"].append(
            {
                "wsf_type": wsf_type,
                "allowed_block_kinds": rule.get("allowed_block_kinds", []),
                "preferred_declaration": rule.get("preferred_declaration", ""),
                "provenance": rule.get("provenance", []),
            }
        )
        preferred = rule.get("preferred_declaration", "")
        if preferred:
            constraints["preferred_declarations"].append(preferred)

    if row.get("default_component_bundle"):
        constraints["default_component_bundle"] = list(row["default_component_bundle"])

    if not constraints["wsf_context_rules"] and "default_component_bundle" not in constraints:
        return {}
    return constraints
