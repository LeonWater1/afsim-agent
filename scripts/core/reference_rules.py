#!/usr/bin/env python3
"""
AFSIM Reference Rules v1 — centralized rule extraction from human-authored references.

Sources (loaded once at import):
  - references/commands_reference.md   — valid block shapes, command grammar, units
  - references/common_mistakes.md      — forbidden patterns, error examples

Excluded:
  - references/commands.md  — contains {} DSL, RUN_SIMULATION, Time() etc. that
    conflict with the current .txt generation pipeline.

Exports for prompt injection, static checking, and safe repair.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REFERENCES = ROOT / "references"

# ---- Unit defaults (from commands_reference.md § 常用单位) -------------------
VALID_UNITS = {
    "speed":     ["m/sec", "km/hr", "knots", "kts"],
    "distance":  ["m", "km", "ft", "nm"],
    "time":      ["sec", "min", "hr"],
    "angle":     ["deg", "rad"],
    "accel":     ["g", "m/sec^2"],
    "mass":      ["kg", "lb"],
    "power":     ["W", "kW", "MW"],
    "freq":      ["Hz", "kHz", "MHz", "GHz"],
}

SAFE_UNIT_DEFAULTS: dict[str, str] = {
    "maximum_speed":              "m/sec",
    "minimum_speed":              "m/sec",
    "speed":                      "m/sec",
    "default_radial_acceleration": "g",
    "default_linear_acceleration": "g",
    "turn_rate_limit":            "deg/sec",
    "scan_rate":                  "deg/sec",
    "maximum_range":              "nm",
    "minimum_range":              "nm",
    "altitude":                   "ft msl",
    "depth":                      "m",
    "frame_time":                 "sec",
    "update_interval":            "sec",
    "firing_interval":            "sec",
    "reload_time":                "sec",
    "pause_time":                 "sec",
    "end_time":                   "sec",
    "creation_time":              "sec",
    "pulse_width":                "sec",
    "empty_mass":                 "kg",
    "fuel_mass":                  "kg",
    "payload_mass":               "kg",
    "length":                     "m",
    "width":                      "m",
    "height":                     "m",
    "heading":                    "deg",
    "field_of_view":              "deg",
    "bank_angle_limit":           "deg",
    "climb_rate":                 "m/sec",
    "dive_rate":                  "m/sec",
    "maximum_climb_rate":         "m/sec",
    "transmitter_power":          "kW",
    "frequency":                  "MHz",
    "frequency_band":             "MHz",  # pair: <lower> <unit> <upper> <unit>
    "pulse_repetition_frequency": "Hz",
    "beamwidth":                  "deg",
    "radial_acceleration":        "g",
    "linear_acceleration":        "m/sec^2",
}

# Unit normalisation: LLM-common mistakes → correct
# Ordered list of (wrong, correct) — longer patterns must come first.
UNIT_NORMALISATIONS: list[tuple[str, str]] = [
    ("m/s2",     "m/sec^2"),
    ("m/s",      "m/sec"),
    ("km/h",     "km/hr"),
    ("kph",      "km/hr"),
    ("mph",      "knots"),
    ("microsec", "usec"),
]

# ---- Forbidden patterns (from common_mistakes.md) ----------------------------
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\bcout\s*<<", "use print() instead of cout"),
    (r"\bendl\b", "use print() instead of endl"),
    (r"\bfmod\s*\(", "fmod() not supported in AFSIM script"),
    (r"\?\s*[^:]+:", "ternary operator (?:) not supported in AFSIM script"),
    (r"\(int\)|\(double\)|\(float\)", "C-style type casting not supported"),
    (r"\bdefault_climb_rate\b", "WSF_AIR_MOVER does not support default_climb_rate"),
    (r"\bdefault_descent_rate\b", "WSF_AIR_MOVER does not support default_descent_rate"),
    (r"\bmax_speed\b", "use maximum_speed instead of max_speed"),
    (r"\bmin_speed\b", "use minimum_speed instead of min_speed"),
    (r"\bmax_alt\b", "use maximum_altitude instead of max_alt"),
    (r"\bconsole\b", "console is not an AFSIM command"),
    (r"\bbehavior_bundle\b", "behavior_bundle is not a valid AFSIM block keyword — use behavior_tree or advanced_behavior_tree"),
    (r"loop\b(?!.*\bend_loop\b)", "do not use loop in routes; use at_end_of_path extrapolate"),
    # script/end_script inside on_initialize/on_update
    (r"on_initialize\s*\n\s*script\b", "on_initialize does not need script/end_script wrapping"),
    (r"on_update\s*\n\s*script\b", "on_update does not need script/end_script wrapping"),
]

# ---- Legal block shapes (from commands_reference.md) -------------------------
LEGAL_BLOCK_SHAPES: dict[str, list[str]] = {
    "platform":      ["platform <name> <type>", "end_platform"],
    "platform_type": ["platform_type <name> <type>", "end_platform_type"],
    "mover":         ["mover <type>", "end_mover"],
    "route":         ["route", "navigation", "end_navigation", "end_route"],
    "sensor":        ["sensor <name> <type>", "end_sensor"],
    "weapon":        ["weapon <name> <type>", "end_weapon"],
    "processor":     ["processor <name> <type>", "end_processor"],
    "comm":          ["comm <name> <type>", "end_comm"],
    "antenna_pattern": ["antenna_pattern <name>", "constant_pattern", "end_constant_pattern", "end_antenna_pattern"],
    "event_pipe":    ["event_pipe", "end_event_pipe"],
    "event_output":  ["event_output", "end_event_output"],
}

# ---- Block hierarchy (from commands_reference.md) ----------------------------
# Maps each block keyword to its valid parent contexts.
# "top" = allowed at depth 0.  A missing parent means the block is floating.
BLOCK_HIERARCHY: dict[str, set[str]] = {
    # Truly top-level structural blocks
    "platform_type":     {"top"},
    "platform":          {"top"},
    "event_pipe":        {"top"},
    "event_output":      {"top"},
    "script_interface":  {"top"},
    # Component templates: valid standalone (top) AND inside parent blocks
    "mover":             {"top", "platform_type"},
    "sensor":            {"top", "platform_type", "platform"},
    "weapon":            {"top", "platform_type", "platform"},
    "processor":         {"top", "platform_type", "platform"},
    "comm":              {"top", "platform_type", "platform"},
    "antenna_pattern":   {"top", "platform_type", "platform"},
    "chaff_parcel":      {"top", "platform_type"},
    # MUST be inside platform — cannot float
    "route":             {"platform"},
    # Sub-blocks — strictly nested
    "transmitter":       {"sensor"},
    "receiver":          {"sensor"},
    "constant_pattern":  {"antenna_pattern"},
    "navigation":        {"route"},
    "ejector":           {"weapon"},
    # Electronic warfare (ref: demos/electronic_warfare/spot_jamming.txt)
    "electronic_warfare": {"top", "platform"},
    "electronic_attack":  {"platform", "electronic_warfare"},
    "technique":          {"electronic_warfare", "electronic_attack", "processor"},
    "effect":             {"technique"},
    "script_variables":  {"processor"},
    "on_initialize":     {"processor"},
    "on_update":         {"processor"},
    "behavior_tree":     {"processor"},
    "advanced_behavior_tree": {"processor"},
    "behavior_node":     {"behavior_tree", "advanced_behavior_tree", "selector", "sequence", "parallel", "condition"},
    "script":            {"processor", "behavior_tree", "advanced_behavior_tree"},
    "parallel":          {"behavior_tree", "advanced_behavior_tree", "selector", "sequence", "condition"},
    "selector":          {"behavior_tree", "advanced_behavior_tree"},
    "sequence":          {"behavior_tree", "advanced_behavior_tree"},
    "condition":         {"behavior_tree", "advanced_behavior_tree", "selector", "sequence", "parallel"},
    "ejector":           {"weapon"},
}

# Keywords that push onto the block stack (open a new scope).
_BLOCK_OPEN = {k for k in BLOCK_HIERARCHY if k != "end_time"}

# Map each open keyword to its matching end tag.
_BLOCK_CLOSE_MAP: dict[str, str] = {
    "platform_type":     "end_platform_type",
    "platform":          "end_platform",
    "mover":             "end_mover",
    "route":             "end_route",
    "sensor":            "end_sensor",
    "weapon":            "end_weapon",
    "processor":         "end_processor",
    "comm":              "end_comm",
    "transmitter":       "end_transmitter",
    "receiver":          "end_receiver",
    "constant_pattern":  "end_constant_pattern",
    "navigation":        "end_navigation",
    "antenna_pattern":   "end_antenna_pattern",
    "chaff_parcel":      "end_chaff_parcel",
    "script_interface":  "end_script_interface",
    "script_variables":  "end_script_variables",
    "on_initialize":     "end_on_initialize",
    "on_update":         "end_on_update",
    "behavior_tree":     "end_behavior_tree",
    "advanced_behavior_tree": "end_advanced_behavior_tree",
    "behavior_node":     "end_behavior_node",
    "script":            "end_script",
    "parallel":          "end_parallel",
    "selector":          "end_selector",
    "sequence":          "end_sequence",
    "condition":         "end_condition",
    "ejector":           "end_ejector",
    "electronic_warfare": "end_electronic_warfare",
    "electronic_attack":  "end_electronic_attack",
    "technique":          "end_technique",
    "effect":             "end_effect",
    "event_pipe":        "end_event_pipe",
    "event_output":      "end_event_output",
}


def repair_block_structure(lines: list[str]) -> list[str]:
    """Deterministic block-stack repair.

    Fixes the most common E002 patterns without LLM involvement:
    1. Cross-closing: end_route when platform is on stack → auto-insert missing closes
    2. Missing sibling close: transmitter then receiver → insert end_transmitter
    3. Floating blocks at depth 0: route at top level → skip silently
    """
    stack: list[str] = []          # open block keywords
    output: list[str] = []
    inserted: set[str] = set()     # end tags already inserted by repair
    skipping: int = 0              # depth while skipping a floating block

    for raw in lines:
        stripped = raw.strip()
        parts = stripped.split()
        head = parts[0] if parts else ""

        # ---- Skip mode: consume floating block ----
        if skipping > 0:
            if head in _BLOCK_OPEN:
                skipping += 1
            elif head.startswith("end_"):
                skipping -= 1
            continue

        # ---- Block open ----
        if head in _BLOCK_OPEN:
            # technique/effect without a WSF type are references, not new blocks
            if head in ("technique", "effect") and len(parts) >= 2 and not parts[-1].startswith("WSF_"):
                output.append(raw)
                continue
            # Inline block close detection — "sensor NAME on end_sensor", etc.
            # The inline form closes the block on the same line, so do NOT push onto stack.
            _close_tag = _BLOCK_CLOSE_MAP.get(head, f"end_{head}")
            if _close_tag in parts[1:]:
                output.append(raw)
                continue
            parents = BLOCK_HIERARCHY.get(head, set())

            if not stack:
                if "top" in parents:
                    pass  # valid at top level, just push
                else:
                    # Requires a parent but none exists → floating block, skip
                    skipping = 1
                    continue
            else:
                # Stack not empty.  Close blocks that cannot contain this one.
                # If the stack top IS a valid parent, do nothing.
                while stack and stack[-1] not in parents:
                    kw = stack.pop()
                    tag = _BLOCK_CLOSE_MAP.get(kw, f"end_{kw}")
                    output.append(tag)
                    inserted.add(tag)

            # After closing blocks: if stack is now empty and this block requires
            # a parent (not valid at top level), skip it as a floating block.
            # Example: receiver inside platform_type → close platform_type first,
            # then receiver has no valid parent at depth 0 → skip.
            if not stack and "top" not in parents:
                skipping = 1
                continue

            stack.append(head)
            output.append(raw)
            continue

        # ---- Block close ----
        if head.startswith("end_"):
            if head in inserted:
                inserted.discard(head)
                continue

            # Match end tag to stack
            found = None
            for kw, tag in _BLOCK_CLOSE_MAP.items():
                if tag == head:
                    found = kw
                    break

            if found is None:
                # Unknown end tag — treat as hallucinated and skip
                # (e.g. end_execute, end_state, end_on_message)
                continue

            # Find matching open on stack
            idx = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == found:
                    idx = i
                    break

            if idx is not None:
                # Close everything above the match (cross-close fix)
                while len(stack) > idx + 1:
                    kw = stack.pop()
                    tag = _BLOCK_CLOSE_MAP.get(kw, f"end_{kw}")
                    output.append(tag)
                    inserted.add(tag)
                stack.pop()  # pop the matched block
                output.append(raw)
            else:
                # No matching open → this end tag is orphaned, skip it
                # Common case: end_platform_type without platform_type,
                # end_platform without platform (when platform_type already closed)
                continue
            continue

        output.append(raw)

    # Close remaining open blocks at end
    while stack:
        kw = stack.pop()
        output.append(_BLOCK_CLOSE_MAP.get(kw, f"end_{kw}"))

    return output

def build_compact_prompt() -> str:
    """Single compact block suitable for injection into LLM system prompts."""
    unit_lines = ", ".join(
        f"{k}: {'|'.join(v)}" for k, v in sorted(VALID_UNITS.items())
    )
    forbidden_lines = "\n".join(
        f"- {msg}" for _, msg in FORBIDDEN_PATTERNS[:10]
    )
    shape_lines = "\n".join(
        f"- {' '.join(shapes[0:1])} ... {shapes[-1]}" for shapes in LEGAL_BLOCK_SHAPES.values()
    )
    return f"""AFSIM 2.9.0 Reference Rules (compact):

Required units: {unit_lines}

Forbidden (will cause FATAL):
{forbidden_lines}

Legal block shapes:
{shape_lines}

CRITICAL — script must be self-contained:
- NEVER use include_once, include_file, or include — the generated script must be fully self-contained with no external file references.
- NEVER use define_path_variable, file_path, or log_file — they reference external paths.
- NEVER emit ${{...}} or $(...) variable references.
- NEVER reference external files like _common.txt, platforms/*.txt, utils/*.txt, scenarios/*.txt — all content must be inline.

CRITICAL — block nesting (every open block MUST be closed):
- platform_type contains: mover, sensor, weapon, processor, comm, antenna_pattern
- platform contains: route, sensor (inline 'on' only), comm (inline 'on' only)
- sensor (radar) contains: transmitter (with power X kW AND frequency X MHz — BOTH required), receiver (with frequency X MHz)
- transmitter REQUIRES: power AND frequency parameters inside
- receiver is ONLY valid inside sensor — NEVER at top level or inside platform directly
- route contains: position waypoints (NOT navigation/end_navigation)
- route is ONLY valid inside platform — NEVER at top level
- processor contains: on_initialize, on_update, behavior_tree, advanced_behavior_tree
- All components (mover/sensor/weapon/processor/comm) declared INSIDE platform_type, NEVER after end_platform_type.
- event_output and event_pipe are top-level ONLY — NEVER inside platform or platform_type

CRITICAL — valid WSF types (only use these; NEVER invent types):
- platform: WSF_PLATFORM | WSF_BRAWLER_PLATFORM
- mover: WSF_AIR_MOVER | WSF_GROUND_MOVER | WSF_KINEMATIC_MOVER | WSF_GUIDED_MOVER | WSF_SIX_DOF_MOVER | WSF_UNGUIDED_MOVER | WSF_INTEGRATING_SPACE_MOVER
- sensor: WSF_RADAR_SENSOR | WSF_ACOUSTIC_SENSOR | WSF_ESM_SENSOR | WSF_EOIR_SENSOR | WSF_GEOMETRIC_SENSOR | WSF_LASER_TRACKER
- weapon: WSF_AIR_TO_AIR_MISSILE | WSF_CHAFF_WEAPON | WSF_EXPLICIT_WEAPON
- CRITICAL: WSF_AIR_TO_AIR_MISSILE requires spawned_platform_type inside the weapon block. If you cannot provide full spawned platform setup, use WSF_EXPLICIT_WEAPON instead or omit the weapon block entirely. Using WSF_AIR_TO_AIR_MISSILE without spawned_platform_type causes FATAL 'Could not find weapon'.
- processor: WSF_SCRIPT_PROCESSOR | WSF_TRACK_PROCESSOR | WSF_TASK_PROCESSOR
- comm: WSF_COMM_TRANSCEIVER | WSF_COMM_XMTR | WSF_COMM_RCVR | WSF_COMM_ROUTER
- NEVER use: WSF_BEHAVIOR_PROCESSOR, WSF_BEHAVIOR_BUNDLE, WSF_GENERIC_SENSOR, WSF_PROCESSOR, WSF_BEHAVIOR_BUNDLE, air_engage_processor, fighter_aircraft_basic, WSF_WATER_MOVER, WSF_COMM

CRITICAL — common mistakes to avoid (these cause FATAL parse errors):
- NEVER use these invalid commands: detect_event, on_message, end_on_message, end_state, engage_iff_permissions, end_execute, mission_log, message_type, end_platform_type (without matching platform_type)
- Use maximum_speed NOT max_speed; minimum_speed NOT min_speed; maximum_altitude NOT max_alt
- Use default_radial_acceleration NOT acceleration
- end_time MUST be the LAST line of the script at top level (depth 0)
- ALL numeric parameters MUST include units (m/sec, ft, nm, sec, deg, g, kW, MHz, etc.)
- A platform_type that uses a mover/sensor/weapon/processor/comm must declare it INSIDE the platform_type block BEFORE end_platform_type
- sensor reference inside platform: use 'sensor NAME on end_sensor' on ONE line (inline)
- When platform_type declares a mover/sensor/weapon/processor, always close the block BEFORE end_platform_type
- Do NOT put component blocks (mover/sensor/weapon/processor) at top level — they belong inside platform_type
- event_pipe and event_output go at script top level, NOT inside platform blocks
- NEVER use C++ syntax: cout, <<, endl, fmod(), ternary (? :), or C-style casts — use print() instead
- NEVER nest script/end_script inside on_initialize or on_update — write code directly
- NEVER use navigation/end_navigation inside route — just list position waypoints
- transmitter without power AND frequency inside = FATAL error at mission.exe"""


def build_forbidden_regex() -> list[tuple[re.Pattern, str]]:
    """Compiled regex list for use in static checker."""
    return [(re.compile(p, re.IGNORECASE), msg) for p, msg in FORBIDDEN_PATTERNS]


def normalise_units(text: str) -> str:
    """Apply unit normalisations using word-boundary regex to avoid substring bugs."""
    result = text
    for wrong, correct in UNIT_NORMALISATIONS:
        result = re.sub(r'\b' + re.escape(wrong) + r'\b', correct, result)
    return result


def postprocess_script(script_text: str, script_dir: str | None = None) -> str:
    """Shared post-process applied to ALL LLM outputs (generation + repair).

    Phases:
    -1. Remove unresolvable include directives (source: mission.exe FATAL on missing includes)
     0. Fix known invalid command aliases (source: static_checker KNOWN_INVALID_ALIASES)
     1. Normalise unit strings (m/s2 → m/sec^2, m/s → m/sec, microsec → usec)
     2. Convert ``<number> usec`` → ``<number>e-6 sec``
     3. Remove known-hallucinated directives (source: UNSUPPORTED_DIRECTIVES from static checker)
     4. Strip lines starting with unresolvable variable refs ($(...), ${...})
     5. Block-structure repair (cross-close, auto-insert missing closes)
     6. Dedup top-level declarations (fixes E010)
     7. Relocate end_time to the last line at depth 0 (fixes E002)
    """
    # ---- Phase -2: Strip markdown fences and code block markers ----
    # Source: LLM repair sometimes includes ```afsim ... ``` fences despite
    # "no markdown fences" instruction. strip_code_fences handles this, but
    # repair paths sometimes deliver text that still contains fences.
    script_text = re.sub(r'^```\w*\s*\n?', '', script_text, flags=re.MULTILINE)
    script_text = re.sub(r'\n?```\s*$', '', script_text, flags=re.MULTILINE)

    # ---- Phase -1.5: Fix non-WSF mover/component names ----
    # Source: LLM often invents human-readable names (air_mover_basic, etc.)
    # instead of using WSF_ types. These cause "Could not find mover X" errors.
    # Only fix when the invented name appears as mover/weapon/sensor type arg.
    _MOVER_NAME_FIXES = {
        'air_mover_basic': 'WSF_AIR_MOVER',
        'air_mover': 'WSF_AIR_MOVER',
        'ground_mover_basic': 'WSF_GROUND_MOVER',
        'ground_mover': 'WSF_GROUND_MOVER',
        'kinematic_mover_basic': 'WSF_KINEMATIC_MOVER',
        'kinematic_mover': 'WSF_KINEMATIC_MOVER',
        'guided_mover_basic': 'WSF_GUIDED_MOVER',
        'guided_mover': 'WSF_GUIDED_MOVER',
        'brawler_mover_basic': 'WSF_BRAWLER_MOVER',
        'brawler_mover': 'WSF_BRAWLER_MOVER',
        'six_dof_mover_basic': 'WSF_SIX_DOF_MOVER',
        'six_dof_mover': 'WSF_SIX_DOF_MOVER',
        'unguided_mover_basic': 'WSF_UNGUIDED_MOVER',
        'space_mover_basic': 'WSF_INTEGRATING_SPACE_MOVER',
        'mover_air': 'WSF_AIR_MOVER',
        'mover_ground': 'WSF_GROUND_MOVER',
        'mover_kinematic': 'WSF_KINEMATIC_MOVER',
        'basic_mover': 'WSF_KINEMATIC_MOVER',
    }
    for _bad, _good in _MOVER_NAME_FIXES.items():
        # Only fix when used as a type argument (e.g., "mover air_mover_basic")
        script_text = re.sub(
            rf'(^|\s)mover\s+{re.escape(_bad)}(\s|$)',
            rf'\1mover {_good}\2',
            script_text,
            flags=re.MULTILINE,
        )

    # ---- Phase -1: Remove unresolvable includes and external path refs ----
    # Source: mission.exe produces FATAL "Cannot open file: X" for missing includes.
    # Also remove file_path, log_file, define_path_variable — they reference external
    # paths that do not exist in the task directory and cause LLM to hallucinate.
    # AFSIM cannot recover from missing include files.
    from pathlib import Path as _Path
    _KNOWN_MISSING_PATTERNS = {
        "_common.txt", "common.txt", "scenario.txt",
        "scenarios/orbiter.txt", "platforms/brawler_platform.txt",
        "platforms/brawler_flight_lead.txt", "utils/BM_Utilities.txt",
        "setup/setup.txt", "setup/terrain.txt",
        "processors/asset_manager.txt", "processors/disseminate_c2.txt",
        "processors/battle_manager.txt", "processors/simple_sensors_manager.txt",
        "processors/weapons_manager_sam.txt",
        "comm/datalinks.txt", "platforms/common.txt", "platforms/target.txt",
        "platforms/iads_cmdr.txt", "platforms/radar_company.txt",
        "platforms/ew_radar.txt", "platforms/acq_radar.txt",
        "platforms/tt_radar.txt", "platforms/sam_battalion.txt",
        "platforms/sam_launcher.txt", "platforms/ucav.txt",
        "platforms/ACFT_BD.FXW", "platforms/ACFT_BD.txt",
    }
    _lines = script_text.splitlines()
    _result = []
    for _line in _lines:
        _stripped = _line.strip()
        if _stripped.startswith(("include_once ", "include_file ", "include ")):
            _parts = _stripped.split()
            if len(_parts) >= 2:
                _path = _parts[1].rstrip("#").strip().strip('"').strip("'")
                # Skip includes with unresolvable variables
                if "${" in _path or "$(" in _path:
                    continue
                # Skip known missing files
                if _path in _KNOWN_MISSING_PATTERNS:
                    continue
                # Skip hallucinated directory patterns
                _base = _path
                _is_hallucinated = False
                for _hdir in ["scenarios/", "utils/", "setup/", "processors/", "comm/", "platforms/"]:
                    if _base.startswith(_hdir):
                        _is_hallucinated = True
                        break
                if _is_hallucinated:
                    continue
                # Check actual file existence if script_dir provided
                if script_dir:
                    _candidate = _Path(script_dir) / _path
                    if not _candidate.exists():
                        # Also check AFSIM demos dir
                        _demo_candidate = _Path(r"C:\Program Files\afsim-2.9.0-win64\demos") / _path
                        if not _demo_candidate.exists():
                            continue
        # Strip file_path, log_file, define_path_variable — they reference
        # external paths and cause LLM to hallucinate non-existent file refs.
        if _stripped.startswith(("file_path ", "log_file ", "define_path_variable ")):
            continue
        _result.append(_line)
    script_text = "\n".join(_result)

    # ---- Phase 0: Fix known invalid command aliases ----
    # Source: static_checker_v1.py KNOWN_INVALID_ALIASES + FORBIDDEN_PATTERNS,
    # confirmed by mission.exe diagnostics.
    _COMMAND_FIXES = [
        (r'\bmax_speed\b', 'maximum_speed'),
        (r'\bmin_speed\b', 'minimum_speed'),
        (r'\bmax_alt\b', 'maximum_altitude'),
        (r'\bacceleration\b', 'default_radial_acceleration'),
        (r'\bturn_radius\b', 'turn_rate_limit'),
        (r'\bengagement_range\b', 'maximum_range'),
        (r'\bdefault_climb_rate\b', 'maximum_climb_rate'),
        (r'\bdefault_descent_rate\b', 'maximum_climb_rate'),
        (r'\bclimb_rate\b', 'maximum_climb_rate'),
        (r'\bdescent_rate\b', 'maximum_climb_rate'),
        (r'\bon_initialize2\b', 'on_initialize'),
        (r'\bat_interval_of\b', 'at_interval'),
        (r'\binitial_position\b', 'position'),
        (r'\bbehavior_bundle\b', 'behavior_tree'),
        (r'\bend_on_message\b', 'end_processor'),
        (r'\bend_state\b', 'end_script'),
        (r'\bend_process\b', 'end_processor'),
        (r'\bfeet\b', 'ft'),
        (r'\bseconds\b', 'sec'),
    ]
    # Fix zero values for parameters that AFSIM requires > 0
    # Source: mission.exe "Expected value '0' to be > 0"
    script_text = re.sub(r'\bminimum_speed\s+0(\s|$)', r'minimum_speed 1\1', script_text)
    script_text = re.sub(r'\bmaximum_speed\s+0(\s|$)', r'maximum_speed 1\1', script_text)
    # Fix bad scan_mode values — AFSIM only accepts specific mode names
    script_text = re.sub(r'\bscan_mode\s+"raster"\b', '', script_text)
    script_text = re.sub(r'\bscan_mode\s+\S+', '', script_text)
    for _pat, _repl in _COMMAND_FIXES:
        script_text = re.sub(_pat, _repl, script_text)
    # Fix .NAME() → .Name() (C++ vs AFSIM script method naming)
    script_text = re.sub(r'\.NAME\(\)', '.Name()', script_text)
    # Fix set_task( → (not valid AFSIM script API)
    script_text = re.sub(r'\bset_task\s*\(', 'print("set_task: "', script_text)
    # Fix Python/C# syntax in AFSIM script: WsfEntity, self., .Current()
    script_text = re.sub(r'\bWsfEntity\b', 'WsfPlatform', script_text)
    script_text = re.sub(r'\bself\.', 'PLATFORM.', script_text)
    script_text = re.sub(r'\.Current\(\)', '', script_text)
    # Strip lines with invalid AFSIM script API calls (hallucinated methods)
    script_text = re.sub(r'^.*\bGetPlatformByName\b.*$', '', script_text, flags=re.MULTILINE)
    script_text = re.sub(r'^.*\bFindPlatform\b.*$', '', script_text, flags=re.MULTILINE)
    # ---- Phase 0.44: Fix AFSIM script language syntax ----
    # AFSIM script uses C++-style syntax. LLM often generates hybrid syntax
    # (Python and/or/not, Ada-style then/elseif/endif). Fix these systematically.
    # Source: mission.exe diagnostics from BV1-001, BV1-014, BV1-027.
    # Step 1: Logical operators (Python → C++)
    script_text = re.sub(r'\band\b', '&&', script_text)
    script_text = re.sub(r'\bor\b', '||', script_text)
    script_text = re.sub(r'\bnot\b', '!', script_text)
    # Step 2: if (...) then → if (...) — AFSIM script uses C++ syntax, no 'then'
    script_text = re.sub(r'\bif\s*\(([^)]*)\)\s*then\b', r'if (\1)', script_text)
    # Step 3: elseif/elsif (...) then → } else if (...)
    script_text = re.sub(r'\belseif\s*\(([^)]*)\)\s*then\b', r'} else if (\1)', script_text)
    script_text = re.sub(r'\belsif\s*\(([^)]*)\)\s*then\b', r'} else if (\1)', script_text)
    # Step 4: elseif/elsif (...) (no then) → } else if (...)
    script_text = re.sub(r'\belseif\s*\(([^)]*)\)', r'} else if (\1)', script_text)
    script_text = re.sub(r'\belsif\s*\(([^)]*)\)', r'} else if (\1)', script_text)
    # Step 5: standalone else on its own line → } else {
    script_text = re.sub(r'\n(\s*)\belse\b\s*\n', r'\n\1} else {\n', script_text)
    # Step 6: endif / end_if → }
    script_text = re.sub(r'\bendif\b', '}', script_text)
    script_text = re.sub(r'\bend_if\b', '}', script_text)
    # Step 7: Remove orphaned 'then' (not preceded by if)
    # Fix hallucinated AFSIM script APIs — confirmed invalid by mission.exe
    # Source: BV1-025 mission log "Unknown identifier: comm_receive_message"
    script_text = re.sub(r'\bcomm_receive_message\b', 'print', script_text)
    script_text = re.sub(r'\bcomm_send_message\b', 'print', script_text)
    script_text = re.sub(r'\bget_track_by_id\b', 'print', script_text)
    script_text = re.sub(r'\bsend_task_to_platform\b', 'print', script_text)

    # ---- Phase 0.445: Extract random_seed from inside blocks to top level ----
    # random_seed is only valid at top level (depth 0), not inside event_pipe or other blocks.
    # Source: AFSIM 2.9.0 official demos (1v1.txt line 54); mission.exe BV1-003.
    _random_seed_lines = []
    _lines = script_text.splitlines()
    _result = []
    for _line in _lines:
        _stripped = _line.strip()
        if re.match(r'^random_seed\s+\d+', _stripped):
            _random_seed_lines.append(_stripped)
            # Skip this line — will be added at top level
            continue
        _result.append(_line)
    script_text = "\n".join(_result)
    # Add random_seed lines just before end_time (at top level)
    if _random_seed_lines:
        _rs_line = _random_seed_lines[0]  # Keep only the first one
        script_text = re.sub(
            r'(\nend_time\s)',
            r'\n' + _rs_line + r'\n\1',
            script_text,
            count=1,
        )

    # ---- Phase 0.45: Fix WSF mover types used as platform_type type ----
    # Source: LLM generates "platform_type X WSF_AIR_MOVER" — mover type misused
    # as platform type. Fix: replace with WSF_PLATFORM.
    _MOVER_WSF_TYPES = {'WSF_AIR_MOVER', 'WSF_GROUND_MOVER', 'WSF_KINEMATIC_MOVER',
                        'WSF_GUIDED_MOVER', 'WSF_BRAWLER_MOVER', 'WSF_SIX_DOF_MOVER',
                        'WSF_UNGUIDED_MOVER', 'WSF_INTEGRATING_SPACE_MOVER',
                        'WSF_STRAIGHT_LINE_MOVER', 'WSF_OFFSET_MOVER',
                        'WSF_POINT_MASS_SIX_DOF_MOVER', 'WSF_OLD_GUIDED_MOVER',
                        'WSF_FIRES_MOVER'}
    for _mt in _MOVER_WSF_TYPES:
        script_text = re.sub(
            rf'(platform_type\s+\S+\s+){re.escape(_mt)}(\s|$)',
            rf'\1WSF_PLATFORM\2',
            script_text,
        )
    # Fix: duplicate WSF type in mover/sensor/weapon/processor declarations
    # LLM generates "mover WSF_AIR_MOVER WSF_AIR_MOVER" (extra type arg)
    script_text = re.sub(
        r'(mover\s+)(WSF_\w+)\s+\2(\s|$)',
        r'\1\2\3',
        script_text,
    )
    script_text = re.sub(
        r'(sensor\s+\S+\s+)(WSF_\w+)\s+\2(\s|$)',
        r'\1\2\3',
        script_text,
    )
    script_text = re.sub(
        r'(weapon\s+\S+\s+)(WSF_\w+)\s+\2(\s|$)',
        r'\1\2\3',
        script_text,
    )
    # Fix: WSF_AIR_TO_AIR_MISSILE is not available as a standalone weapon type
    # in default AFSIM plugins. Convert to WSF_EXPLICIT_WEAPON which is the
    # generic standalone weapon type. Source: mission.exe "Could not find weapon
    # WSF_AIR_TO_AIR_MISSILE" on BV1-004, BV1-005.
    script_text = re.sub(
        r'(weapon\s+\S+\s+)WSF_AIR_TO_AIR_MISSILE\b',
        r'\1WSF_EXPLICIT_WEAPON',
        script_text,
    )
    script_text = re.sub(
        r'(processor\s+\S+\s+)(WSF_\w+)\s+\2(\s|$)',
        r'\1\2\3',
        script_text,
    )

    # ---- Phase 0.5: Fix known wrong WSF types ----
    # Source: VALID_WSFS in static_checker_v1.py — official AFSIM 2.9.0 type whitelist.
    # ONLY replace types NOT in the whitelist. Keep all whitelisted types.
    from .static_checker import VALID_WSFS as _VALID_WSFS
    _NON_WHITELIST_TYPE_REPLACEMENTS = {
        'WSF_BEHAVIOR_PROCESSOR': 'WSF_TASK_PROCESSOR',
        'WSF_BEHAVIOR_BUNDLE': 'WSF_TASK_PROCESSOR',
        'WSF_GENERIC_SENSOR': 'WSF_GEOMETRIC_SENSOR',
        'WSF_PROCESSOR': 'WSF_SCRIPT_PROCESSOR',
        'WSF_WATER_MOVER': 'WSF_GROUND_MOVER',
        'WSF_COMM': 'WSF_COMM_TRANSCEIVER',
        'air_engage_processor': 'WSF_TASK_PROCESSOR',
        'integrating_space_mover_basic': 'WSF_INTEGRATING_SPACE_MOVER',
        'RADAR_HOMING': 'GUIDANCE_SEMI_ACTIVE',
        'fighter_aircraft_basic': 'WSF_PLATFORM',
        'WSF_SENSOR': 'WSF_GEOMETRIC_SENSOR',
        'WSF_MOVER': 'WSF_KINEMATIC_MOVER',
        'WSF_WEAPON': 'WSF_EXPLICIT_WEAPON',
        'WSF_TASK': 'WSF_TASK_PROCESSOR',
        'WSF_TRACK': 'WSF_TRACK_PROCESSOR',
        'detect_target_processor': 'WSF_SCRIPT_PROCESSOR',
        'fighter_mover': 'WSF_AIR_MOVER',
        'basic_radar': 'WSF_RADAR_SENSOR',
    }
    for _pat, _repl in _NON_WHITELIST_TYPE_REPLACEMENTS.items():
        # Only replace if the target IS in the whitelist (safety check)
        if _repl in _VALID_WSFS:
            script_text = re.sub(r'\b' + re.escape(_pat) + r'\b', _repl, script_text)

    # ---- Phase 0.82: Fix invalid inline constructs ----
    # Source: mission.exe diagnostics.  event_pipe / event_output do NOT take a
    # name after the keyword — only 'file <path>' goes inside the block.
    # Pattern: event_pipe <word-that-isnt-file> → event_pipe
    script_text = re.sub(r'^(\s*)event_pipe\s+(?!file\b)(\S+)(.*)$', r'\1event_pipe\3', script_text, flags=re.MULTILINE)
    script_text = re.sub(r'^(\s*)event_output\s+(?!file\b)(\S+)(.*)$', r'\1event_output\3', script_text, flags=re.MULTILINE)
    # Also fix event_output with detect_event inline
    script_text = re.sub(r'event_output\s+detect_event\b', 'event_output', script_text)

    # ---- Phase 0.81: Strip XML-like tags (LLM hallucinates <BehaviorTree> etc.) ----
    script_text = re.sub(r'<\w+>', '', script_text)
    script_text = re.sub(r'</\w+>', '', script_text)

    # ---- Phase 0.83: Fix cout << / endl patterns in script (C++ in AFSIM) ----
    # Source: FORBIDDEN_PATTERNS.  cout/endl are C++ not AFSIM script.
    # Replace with AFSIM print() calls.
    script_text = re.sub(r'cout\s*<<\s*"([^"]*)"\s*<<\s*endl\s*;', r'print("\1");', script_text)
    script_text = re.sub(r'cout\s*<<\s*"([^"]*)"\s*<<\s*(\w+)\s*<<\s*"([^"]*)"\s*<<\s*endl\s*;', r'print("\1", \2, "\3");', script_text)

    # ---- Phase 0.84: Remove empty event_output blocks ----
    # event_output with no content between open and close → remove entirely
    script_text = re.sub(r'^\s*event_output\s*\n\s*end_event_output\s*$', '', script_text, flags=re.MULTILINE)
    # Source: static_checker_v1.py UNSUPPORTED_DIRECTIVES, confirmed by mission.exe
    _HALLUCINATED_DIRECTIVES = {
        "engage_iff_permissions", "end_engage_iff_permissions",
        "conditional_section", "end_conditional_section",
        "conditionals", "end_conditionals",
        "feature_present", "on_message", "end_on_message",
        "end_state", "observer", "end_observer",
        "navigation", "end_navigation", "repeat",
        "message_type", "weapon_table", "scoring_factors",
        "end_weapon_table", "end_scoring_factors",
        "track_established", "slew_mode", "one_m2_detect_range",
        "on_task_complete", "script_variables", "end_script_variables",
        "beam_pattern", "beam", "end_beam",
        "comm_link", "comm_network", "end_comm_network",
        "comm_transceiver", "end_comm_transceiver",
        "end_explicit_weapon", "end_radar_sensor",
        "end_task_processor", "end_track_processor",
        "explicit_weapon", "process", "end_process",
        "radar_sensor", "task_processor", "track_processor",
        "ea_technique", "end_ea_technique",
        "detect_event", "amend_platform", "end_amend_platform",
        "end_edit",  # LLM often places end_edit at wrong level
        "internal_link",  # NOT a valid comm parameter — causes cascading parser failure
        "end_execute",  # LLM hallucinates execute/end_execute blocks
        "execute",  # LLM uses "execute" as a standalone block
        "end_state", "state",  # State machine blocks not valid at generic scope
        "track_output_comm",  # Not a valid AFSIM command
        "engage",  # engage is only valid inside processor, not standalone
        "end_mission_sequence",  # LLM tries to create mission_sequence blocks
        "mission_sequence",
        "end_on_entry", "on_entry",  # Only valid in specific processor contexts
        "end_on_exit", "on_exit",
        "end_behavior", "behavior",  # Use behavior_tree not bare behavior
        "event_type",  # LLM hallucinated — not a valid AFSIM command
        "report_interval",  # Valid in some contexts but not as standalone
        "sensor_type",  # LLM uses this instead of valid sensor WSF types
        "weapon_type",  # LLM uses this instead of valid weapon WSF types
        "end_engagement_settings",  # Not valid in generic scripts
        "engagement_settings",
        "end_track", "end_entity",  # LLM hallucinations
        "target",  # Valid inside processor, not standalone
        "on_track",  # LLM hallucinated — not valid AFSIM
        "on_track_drop",  # Only valid inside specific processor
        "on_detection",  # LLM hallucinated
        "on_launch",  # LLM hallucinated
        "frequency_band",  # Valid in specific sensor contexts only, not standalone
        "minimum_range",  # Valid in sensor only, not standalone
        "end_laser_designations",  # LLM hallucinated
        "sensor_mode",  # LLM hallucinated — not valid standalone
        "rf_band",  # LLM hallucinated
        "acoustic_type",  # Valid inside acoustic_signature only, not standalone
        "spatial_domain",  # Valid inside platform_type only
        "mission",  # LLM uses as standalone — not a valid AFSIM command
        "end_mission",  # LLM hallucinated close for mission block
        "enable",  # Valid only in specific contexts, not standalone
        "radar_signature",  # Valid inside platform_type only, not standalone
        "infrared_signature",  # Valid inside platform_type only, not standalone
        "optical_signature",  # Valid inside platform_type only, not standalone
        "task",  # Only valid inside processor, not standalone — LLM often puts at top level
        "end_task",  # LLM hallucinated close for task block
        "writeln",  # LLM hallucinated C++ function — not valid AFSIM
        "format",  # LLM hallucinated function call
        "sensitivity",  # LLM hallucinated — not validated in this corpus
        "shape",  # LLM hallucinated — not a standalone AFSIM command
        "extends",  # LLM hallucinated C++/Java syntax — not valid AFSIM
        "detection_range",  # LLM hallucinated sensor parameter
        "primary_route",  # LLM hallucinated
        "empty_mass_kg",  # LLM hallucinated (correct: empty_mass with kg unit)
        "swerling_case",  # LLM hallucinated sensor parameter
        "lethality",  # LLM hallucinated weapon parameter
        "detect_range",  # LLM hallucinated
        "spherical_lethality",  # LLM hallucinated — use WSF_SPHERICAL_LETHALITY
        "choose_tree",  # LLM hallucinated advanced_behavior reference
        "track_filter",  # LLM hallucinated processor sub-component
        "designate_comm",  # LLM hallucinated comm type
        "local",  # LLM uses as type — not valid AFSIM
        "maximum_speed",  # Valid inside mover only — strip when at wrong context
        "frequency",  # Valid inside transmitter only — strip when at wrong context
        "datalink",  # LLM hallucinated comm type
        "quantity",  # LLM uses as standalone — valid only in specific contexts
        "detect_target_tracker",  # LLM hallucinated processor type
        "integrator",  # LLM hallucinated — valid only in specific sub-contexts
        "iads_c2_comm",  # LLM hallucinated comm type
        "track_sensor",  # LLM hallucinated — not a valid standalone command
        "initial_speed",  # LLM hallucinated — use speed inside route position
        "on_task_received",  # LLM hallucinated — not a valid AFSIM handler
        "on_task_complete",  # LLM hallucinated — not a valid AFSIM handler
        "on_track_added",  # LLM hallucinated event handler
        "fly_route",  # LLM hallucinated advanced_behavior reference
        "units",  # LLM hallucinated — not a standalone AFSIM parameter
        "launched_platform",  # LLM hallucinated — valid only in specific contexts
        "db",  # LLM uses as standalone — it's a unit, not a command
        "deg",  # LLM uses as standalone — it's a unit, not a command
        "scenario",  # LLM hallucinated — not a valid AFSIM command
        "motor",  # LLM hallucinated weapon sub-component at wrong level
        "reports_range",  # LLM uses at wrong context
        "default_quantity",  # LLM uses at wrong context
    }
    _lines = script_text.splitlines()
    _result = []
    _skip_depth = 0
    for _line in _lines:
        _stripped = _line.strip()
        _parts = _stripped.split()
        _head = _parts[0] if _parts else ""
        if _skip_depth > 0:
            if _head in BLOCK_HIERARCHY:
                _skip_depth += 1
            elif _head.startswith("end_"):
                _skip_depth -= 1
            continue
        if _head in _HALLUCINATED_DIRECTIVES:
            if _head in BLOCK_HIERARCHY or _head in _BLOCK_OPEN:
                _skip_depth = 1  # skip the entire block
            else:
                _skip_depth = 1
            continue
        # Also check: does the line contain any hallucinated directive mid-line?
        # Use word-boundary check for patterns like writeln(...)
        _has_hallucinated = any(
            re.search(r'\b' + re.escape(_kw) + r'\b', _stripped)
            for _kw in _HALLUCINATED_DIRECTIVES
            if _kw not in _parts  # already checked _head == _kw above
        )
        if _has_hallucinated:
            continue
        # Also skip 'edit platform ...' blocks which LLM often places inside processors
        if _head == "edit" and len(_parts) >= 2:
            _skip_depth = 1  # skip edit and everything until end_edit
            continue
        _result.append(_line)
    script_text = "\n".join(_result)

    # ---- Phase 0.85: Fix empty/incomplete transmitter/receiver blocks ----
    # Source: AFSIM requires transmitter to have power+frequency parameters.
    # Fix 1: Empty blocks (no content between open and close on consecutive lines).
    script_text = re.sub(
        r'(\s*)transmitter\s*\n\s*end_transmitter',
        r'\1transmitter\n\1   power 1 kW\n\1   frequency 1000 MHz\n\1end_transmitter',
        script_text
    )
    # Fix 2: Transmitters with content but missing power or frequency
    # Find transmitter...end_transmitter blocks and ensure power+frequency exist
    _tx_blocks = re.findall(
        r'(transmitter\s*\n.*?end_transmitter)',
        script_text, re.DOTALL
    )
    for _tx in _tx_blocks:
        _fixed = _tx
        if 'power ' not in _tx:
            _fixed = re.sub(r'(transmitter\s*\n)', r'\1   power 1 kW\n', _fixed)
        if 'frequency ' not in _tx:
            _fixed = re.sub(r'(transmitter\s*\n\s*)', r'\1   frequency 1000 MHz\n', _fixed)
        if _fixed != _tx:
            script_text = script_text.replace(_tx, _fixed)
    script_text = re.sub(
        r'(\s*)receiver\s*\n\s*end_receiver',
        r'\1receiver\n\1   frequency 1000 MHz\n\1end_receiver',
        script_text
    )

    # ---- Phase 0.87: Fix common invalid WSF type mistakes ----
    # Source: mission.exe confirmed. WSF_COMM is NOT available in default plugins;
    # WSF_COMM_TRANSCEIVER IS available. Do NOT swap them.
    # Only fix clearly hallucinated types confirmed wrong by mission.exe.
    # WSF_PROCESSOR (no qualifier) → WSF_SCRIPT_PROCESSOR (confirmed invalid via mission.exe)

    # ---- Phase 0.88: Fix WSF_AIR_TO_AIR_MISSILE → WSF_AIR_TO_AIR_MISSILE ----
    # Actually check if this type exists. If not, use generic type.
    # For now, leave it — mission.exe will tell us.

    # ---- Phase 0.89: Remove orphaned blocks after end_platform/end_platform_type ----
    # Source: AFSIM block hierarchy. Sub-blocks (mover/sensor/weapon/processor/comm)
    # appearing at depth 0 right after end_platform/end_platform_type are orphaned.
    # Valid standalone definitions appear BEFORE the platforms that use them.
    _lines = script_text.splitlines()
    _result = []
    _i = 0
    _BLOCK_STARTS = {"mover", "sensor", "weapon", "processor", "comm",
                     "transmitter", "receiver", "route", "antenna_pattern"}
    # Only sub-component blocks are orphaned after end_platform.
    # platform, platform_type, event_pipe, event_output are valid at top level.
    while _i < len(_lines):
        _line = _lines[_i]
        _stripped = _line.strip()
        _parts = _stripped.split()
        _head = _parts[0] if _parts else ""

        # Detect end_platform or end_platform_type followed by orphaned blocks
        if _head in ("end_platform", "end_platform_type"):
            _result.append(_line)
            _i += 1
            # Skip blank lines and check if next non-blank is an orphaned block
            _peek = _i
            while _peek < len(_lines) and not _lines[_peek].strip():
                _result.append(_lines[_peek])
                _peek += 1
            if _peek < len(_lines):
                _ps = _lines[_peek].strip()
                _ph = _ps.split()[0] if _ps.split() else ""
                if _ph in _BLOCK_STARTS:
                    # Skip this orphaned block entirely
                    _sd = 1
                    _peek += 1
                    while _peek < len(_lines) and _sd > 0:
                        _cs = _lines[_peek].strip()
                        _ch = _cs.split()[0] if _cs.split() else ""
                        if _ch in _BLOCK_STARTS or _ch in BLOCK_HIERARCHY:
                            _sd += 1
                        elif _ch.startswith("end_"):
                            _sd -= 1
                        _peek += 1
                    _i = _peek
                    continue
            continue

        _result.append(_line)
        _i += 1
    script_text = "\n".join(_result)

    # ---- Phase 0.9: Strip lines with unresolvable variable refs ----
    script_text = re.sub(r'^.*\$\(\w+\).*$', '', script_text, flags=re.MULTILINE)
    script_text = re.sub(r'^.*\$\{\w+\}.*$', '', script_text, flags=re.MULTILINE)

    # ---- Phase 1: Normalize units ----
    text = normalise_units(script_text)
    # Convert "X usec" → "Xe-6 sec"
    text = re.sub(r'(\d+\.?\d*)\s+usec\b', r'\1e-6 sec', text)
    # Fix ea_technique: illegal top-level -> valid electronic_warfare (ref: spot_jamming.txt)
    # Pattern 1: inline `constant_pattern gain X U` → proper sub-block
    text = re.sub(
        r'^\s*constant_pattern\s+\bgain\b\s+(\S+)\s+(\S+)',
        r'  constant_pattern\n      peak_gain \1 \2\n    end_constant_pattern',
        text, flags=re.MULTILINE,
    )
    # Pattern 2: bare `gain X U` inside structured constant_pattern → peak_gain
    text = re.sub(
        r'^(\s+)\bgain\b\s+(\d+\.?\d*\s+\S+)',
        r'\1peak_gain \2',
        text, flags=re.MULTILINE,
    )
    # Fix ea_technique: illegal top-level block → valid electronic_warfare (ref: spot_jamming.txt)
    text = re.sub(
        r'^ea_technique\s+(\S+)\s+WSF_EA_TECHNIQUE\s*$',
        r'electronic_warfare EA WSF_ELECTRONIC_ATTACK\n   technique \1 WSF_EA_TECHNIQUE',
        text, flags=re.MULTILINE,
    )
    text = re.sub(r'^end_ea_technique\s*$', r'   end_technique\nend_electronic_warfare', text, flags=re.MULTILINE)
    lines = text.splitlines()

    # ---- Phase 0: Block-structure repair ----
    lines = repair_block_structure(lines)

    # ---- Phase 1: Dedup top-level declarations ----
    _DECLARE = {"platform_type", "mover", "sensor", "weapon", "processor", "comm",
                "antenna_pattern", "transmitter", "receiver", "platform",
                "constant_pattern", "event_pipe", "event_output"}
    _NESTABLE = {"platform", "scenario", "side", "route", "script",
                 "script_interface", "processor", "behavior_tree",
                 "advanced_behavior_tree", "advanced_behavior"}
    seen: dict[str, int] = {}
    deduped: list[str] = []
    depth = 0
    skip_depth = 0
    skipping = False

    for raw in lines:
        stripped = raw.strip()
        parts = stripped.split()
        head = parts[0] if parts else ""

        if skipping:
            if head in _NESTABLE or head in _DECLARE:
                skip_depth += 1
            elif head.startswith("end_"):
                skip_depth -= 1
                if skip_depth <= 0:
                    skipping = False
                    skip_depth = 0
            continue

        # Dedup BEFORE depth tracking
        if depth == 0 and head in _DECLARE and len(parts) >= 2:
            key = f"{head}:{parts[1]}"
            if key in seen:
                skipping = True
                skip_depth = 1
                continue
            seen[key] = len(deduped)

        if head in _NESTABLE:
            depth += 1
        elif head.startswith("end_"):
            depth = max(0, depth - 1)

        deduped.append(raw)

    # ---- Phase 2: Relocate end_time ----
    end_time_lines = []
    cleaned = []
    for raw in deduped:
        stripped = raw.strip()
        if stripped.startswith("end_time"):
            end_time_lines.append(stripped)
        else:
            cleaned.append(raw)
    if end_time_lines:
        best = max(end_time_lines, key=len)
        cleaned.append(best)
    elif not any(l.strip().startswith("end_time") for l in cleaned):
        cleaned.append("end_time 120 sec")

    return "\n".join(cleaned)
