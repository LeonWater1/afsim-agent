#!/usr/bin/env python3
"""
Structured mission.exe log parser.

Treats the simulator as the ground-truth judge and extracts four diagnostic
dimensions from every run:

  1. executable      — did the script even pass the AFSIM parser?
  2. error_locations — file:line:column of every parse/compile/runtime error
  3. missing_events  — which expected_events from the IR did NOT fire?
  4. entity_status   — which platforms / sensors / weapons / movers failed phase-1 init?

Outcome is a single ``MissionDiagnostics`` dict that is machine-readable enough
to be fed back into targeted (layer-local) LLM repair, and human-readable
enough to appear in task_summary.json.
"""
from __future__ import annotations

import re
from typing import Any


# ---- phase detection --------------------------------------------------------

_PHASE_MARKERS = [
    ("parser",          "Loading simulation input"),
    ("parser_complete", "Loading simulation input complete"),
    ("init",            "Initializing simulation"),
    ("init_complete",   "Initializing simulation complete"),
    ("run",             "Starting simulation"),
    ("run_complete",    "Simulation complete"),
    ("parser_fatal",    "Reading of simulation input failed"),
]

# ---- error line extraction --------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, str]] = [
    # (regex, category) — order matters: more specific patterns first
    (r"ERROR:\s*Could not find mover (\S+)",                    "missing_mover"),
    (r"ERROR:\s*Could not find weapon (\S+)",                   "missing_weapon"),
    (r"ERROR:\s*Could not find sensor (\S+)",                   "missing_sensor"),
    (r"ERROR:\s*Could not find processor (\S+)",                "missing_processor"),
    (r"ERROR:\s*Could not find platform_type (\S+)",            "missing_platform_type"),
    (r"ERROR:\s*Could not find (?:behavior|group) (\S+)",      "missing_reference"),
    (r"ERROR:\s*Could not find (\S+)",                         "missing_entity"),
    (r"ERROR:\s*Unknown command:\s*(\S+)",                      "unknown_command"),
    (r"ERROR:\s*No frequency bands defined for passive sensor", "esm_no_frequency_band"),
    (r"ERROR:\s*Platform component failed phase one init",      "component_init_failure"),
    (r"ERROR:\s*Initialization of simulation failed",           "init_failed"),
    (r"ERROR:\s*Method '(\S+)' does not exist on class",        "hallucinated_api"),
    (r"ERROR:\s*Invalid method call",                           "invalid_script_api"),
    (r"ERROR:\s*'(\S+)' cannot be used in this context",       "wrong_context_command"),
    (r"FATAL:\s*Could not process input files",                 "parser_fatal"),
    (r"ERROR:\s*(\S+)\s+block must be nested under",            "wrong_block_host"),
    (r"ERROR:\s*(\S+) must have a (\S+) defined",               "missing_companion"),
    (r"ERROR:\s*Unexpected End Of Data",                        "unexpected_eof"),
    (r"ERROR:\s*Bad value for:\s*(\S+)",                        "bad_value"),
    (r"ERROR:\s*Unknown identifier:\s*'(\S+)'",                 "unknown_identifier"),
]

_SOURCE_LOCATION = re.compile(r"'([^']+)',\s*line\s+(\d+)(?:,\s*near column\s+(\d+))?")


def parse(log_text: str, return_code: int | None,
          ir: dict | None = None,
          static_analysis: dict | None = None) -> dict[str, Any]:
    """Produce structured MissionDiagnostics from raw mission.exe output."""

    # ---- 1. executable --------------------------------------------------
    phases_reached = _detect_phases(log_text)
    run_complete = "run_complete" in phases_reached
    parser_ok = "parser_fatal" not in phases_reached
    init_ok = "init_complete" in phases_reached

    executable = bool(run_complete and return_code == 0)

    # ---- 2. error_locations ---------------------------------------------
    error_lines: list[dict[str, Any]] = []
    for raw_line in log_text.splitlines():
        line = raw_line.strip()
        for pattern, category in _ERROR_PATTERNS:
            m = re.search(pattern, line)
            if m:
                entry: dict[str, Any] = {
                    "category": category,
                    "raw": line,
                }
                target = m.group(1) if m.lastindex and m.lastindex >= 1 else ""
                if target:
                    entry["target"] = target
                loc = _SOURCE_LOCATION.search(line)
                if loc:
                    entry["source_file"] = loc.group(1)
                    entry["line"] = int(loc.group(2))
                    if loc.lastindex and loc.lastindex >= 3 and loc.group(3):
                        entry["column"] = int(loc.group(3))
                error_lines.append(entry)
                break

    # ---- 3. missing_events ----------------------------------------------
    missing_events: list[dict[str, Any]] = []
    if ir and run_complete:
        expected = ir.get("expected_events", [])
        log_upper = log_text.upper()
        for evt in expected:
            eid = evt.get("id", "")
            if eid and eid.upper() not in log_upper:
                missing_events.append({"event_id": eid, "type": evt.get("type", "")})

    # ---- 4. entity_status -----------------------------------------------
    entity_status: list[dict[str, Any]] = []
    if ir:
        for entity in ir.get("entities", []):
            eid = entity.get("id", "")
            role = entity.get("role", "")
            side = entity.get("side", "")
            ent_upper = eid.upper()
            status = "unknown"
            if eid and ent_upper in log_text.upper():
                status = "present_in_log"
            if run_complete:
                status = "executed"
            # Check for init failures mentioning this entity
            for err in error_lines:
                if err.get("target", "").upper() == ent_upper:
                    status = "init_failed"
                    break
            entity_status.append({
                "entity_id": eid, "role": role, "side": side, "status": status,
            })

    # ---- aggregate -------------------------------------------------------
    phase_sequence = [p for p, _ in _PHASE_MARKERS if phases_reached.get(p)]

    return {
        "executable": executable,
        "return_code": return_code,
        "phases_reached": phase_sequence,
        "parser_passed": parser_ok,
        "init_passed": init_ok,
        "error_count": len(error_lines),
        "errors": error_lines,
        "error_categories": sorted({e["category"] for e in error_lines}),
        "missing_events": missing_events,
        "entity_status": entity_status,
        "repair_hints": _derive_hints(error_lines, static_analysis),
    }


def _detect_phases(log_text: str) -> dict[str, bool]:
    reached: dict[str, bool] = {}
    for name, marker in _PHASE_MARKERS:
        reached[name] = marker in log_text
    return reached


def _derive_hints(error_lines: list[dict], static_analysis: dict | None) -> list[str]:
    """Generate machine-readable repair hints from error categories."""
    hints: list[str] = []
    categories = {e["category"] for e in error_lines}

    if "missing_mover" in categories:
        hints.append("grounding: add or fix mover mapping; check entity_mapping_v2 for valid mover targets")
    if "missing_weapon" in categories:
        hints.append("grounding: add or fix weapon mapping; check weapon block uses WSF_EXPLICIT_WEAPON with spawned_platform")
    if "missing_sensor" in categories:
        hints.append("grounding: add or fix sensor mapping; verify sensor template is declared before platform references it")
    if "missing_platform_type" in categories:
        hints.append("grounding: platform_type not found; verify platform_type_hint resolves to a declared template")
    if "unknown_command" in categories:
        hints.append("generation: remove unknown command or replace with documented equivalent; check BLOCK_STARTS and KNOWN_AFSIM_TOKENS")
    if "esm_no_frequency_band" in categories:
        hints.append("component: add frequency_band to ESM sensor block")
    if "component_init_failure" in categories:
        hints.append("component: check required sub-blocks and initialization parameters per WSF type host rules")
    if "hallucinated_api" in categories or "invalid_script_api" in categories:
        hints.append("script: replace hallucinated API with verified instance-style pattern from official demos")
    if "wrong_context_command" in categories:
        hints.append("context: move command to correct host block per command_context_rules")
    if "missing_companion" in categories:
        hints.append("companion: add required companion block per wsf_type_host_rules")
    if "wrong_block_host" in categories:
        hints.append("structure: move block under correct parent per block hierarchy")
    if "parser_fatal" in categories:
        hints.append("parser: fix fatal syntax errors first — static checker may have missed them")
    if "bad_value" in categories:
        targets = [e.get("target", "") for e in error_lines if e["category"] == "bad_value"]
        for t in targets:
            hints.append(f"value: bad value for '{t}' — check format, units, and valid range")
    if "unknown_identifier" in categories:
        targets = [e.get("target", "") for e in error_lines if e["category"] == "unknown_identifier"]
        for t in targets:
            hints.append(f"script: unknown identifier '{t}' — remove or replace with AFSIM script variable")
    if categories == {"parser_fatal"} and not any(
        e["category"] not in ("parser_fatal", "init_failed") for e in error_lines
    ):
        hints.append("synthetic: parser_fatal without specific error line → check block structure, end_time placement, and floating route")
    if not hints:
        hints.append("manual: no automated repair hint available; inspect full log and IR")

    # Add static checker hints as context
    if static_analysis and static_analysis.get("primary_error"):
        hints.append(f"static_context: primary_error={static_analysis['primary_error']}")

    return hints
