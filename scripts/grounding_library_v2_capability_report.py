#!/usr/bin/env python3
"""
Generate a lightweight capability report for Task-019 Grounding Library v2.
"""
from __future__ import annotations

import json
from pathlib import Path

from grounding_library_v2 import (
    ROOT,
    collect_ir_coverage,
    resolve_component,
    resolve_platform,
    resolve_task,
    validate_mapping,
)


OUTPUT_PATH = ROOT / "docs" / "machine" / "grounding_library_v2_capability_report.json"


def build_report() -> dict:
    validation = validate_mapping()
    coverage = collect_ir_coverage()
    probes = {
        "commander_platform": resolve_platform(platform_type_hint="commander_platform"),
        "gun_weapon": resolve_component("weapon", type_hint="gun_weapon"),
        "brawler_mover": resolve_component("mover", type_hint="brawler_mover"),
        "time_on_target": resolve_task("time_on_target"),
    }
    return {
        "task": "Task-019",
        "version": "grounding_library_v2_capability_report",
        "validation": validation,
        "coverage": coverage,
        "probe_results": probes,
        "summary": {
            "ok": validation.get("ok", False),
            "coverage_rate": coverage.get("coverage_rate"),
            "platform_hints_total": coverage.get("platform_hints_total"),
            "task_hints_total": coverage.get("task_hints_total"),
            "component_hints_total": coverage.get("component_hints_total"),
        },
    }


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
