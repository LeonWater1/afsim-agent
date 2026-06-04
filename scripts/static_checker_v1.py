#!/usr/bin/env python3
"""
Static Checker v1 for generated AFSIM scripts.

This module is the single source of truth for static verification rules used by
the direct baseline, RAG baseline, IR-to-script generation, and later repair
loops.
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path


BLOCK_STARTS = {
    "script_interface": "end_script_interface",
    "event_output": "end_event_output",
    "dis_interface": "end_dis_interface",
    "platform_type": "end_platform_type",
    "platform": "end_platform",
    "mover": "end_mover",
    "route": "end_route",
    "sensor": "end_sensor",
    "weapon": "end_weapon",
    "processor": "end_processor",
    "antenna_pattern": "end_antenna_pattern",
    "constant_pattern": "end_constant_pattern",
    "transmitter": "end_transmitter",
    "receiver": "end_receiver",
    "script_variables": "end_script_variables",
    "on_initialize": "end_on_initialize",
    "on_update": "end_on_update",
    "comm": "end_comm",
}

END_TO_START = {value: key for key, value in BLOCK_STARTS.items()}

UNIT_COMMANDS = {
    "maximum_speed",
    "minimum_speed",
    "default_radial_acceleration",
    "default_linear_acceleration",
    "frame_time",
    "update_interval",
    "pulse_width",
    "pulse_repetition_frequency",
    "frequency",
    "power",
    "bandwidth",
    "one_m2_detect_range",
    "altitude",
    "heading",
    "speed",
    "end_time",
    "maximum_range",
    "minimum_range",
}

DEFAULT_SYNTAX_ERROR_IDS = {"E001", "E002", "E004", "E007", "E008"}
DEFAULT_STATIC_BLOCKING_ERROR_IDS = {"E001", "E002", "E003", "E004", "E005", "E006", "E007", "E008"}

SUBCOMPONENT_PSEUDO_KEYWORDS = {"weapon_type", "sensor_type", "processor_type", "mover_type"}
NESTED_ONLY_KEYWORDS = {
    "command_chain": "platform",
    "task": "processor",
}
AIR_MOVER_UNSUPPORTED_COMMANDS = {"default_climb_rate", "default_descent_rate"}
ANTENNA_REFERENCE_PARENTS = {"transmitter", "receiver"}

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "docs" / "machine" / "error_taxonomy_v1.json"

# Verified WSF_ types extracted from AFSIM 2.9.0 demo scripts that pass mission.exe.
VALID_WSFS = {
    "WSF_PLATFORM", "WSF_BRAWLER_PLATFORM", "WSF_GROUP",
    "WSF_AIR_MOVER", "WSF_KINEMATIC_MOVER", "WSF_GUIDED_MOVER",
    "WSF_GROUND_MOVER", "WSF_BRAWLER_MOVER", "WSF_SIX_DOF_MOVER",
    "WSF_FIRES_MOVER", "WSF_STRAIGHT_LINE_MOVER", "WSF_OFFSET_MOVER",
    "WSF_POINT_MASS_SIX_DOF_MOVER", "WSF_UNGUIDED_MOVER",
    "WSF_STATIONARY_MOVER", "WSF_INTEGRATING_SPACE_MOVER",
    "WSF_OLD_GUIDED_MOVER", "WSF_AERO",
    "WSF_RADAR_SENSOR", "WSF_ESM_SENSOR", "WSF_EOIR_SENSOR",
    "WSF_GEOMETRIC_SENSOR", "WSF_SAR_SENSOR", "WSF_IRST_SENSOR",
    "WSF_ACOUSTIC_SENSOR", "WSF_LASER_TRACKER", "WSF_RF_JAMMER",
    "WSF_SCRIPT_PROCESSOR", "WSF_TRACK_PROCESSOR", "WSF_TASK_PROCESSOR",
    "WSF_BRAWLER_PROCESSOR", "WSF_SA_PROCESSOR",
    "WSF_QUANTUM_TASKER_PROCESSOR", "WSF_THREAT_PROCESSOR",
    "WSF_PERCEPTION_PROCESSOR", "WSF_PERFECT_TRACKER",
    "WSF_KALMAN_FILTER", "WSF_ALPHA_BETA_FILTER",
    "WSF_LINKED_PROCESSOR", "WSF_IMAGE_PROCESSOR",
    "WSF_DIRECTION_FINDER_PROCESSOR", "WSF_RIPR_PROCESSOR",
    "WSF_WEAPON_TRACK_PROCESSOR", "WSF_STATE_MACHINE",
    "WSF_FT_SCREENER", "WSF_SIMPLE_SENSORS_MANAGER",
    "WSF_SENSORS_MANAGER_FOV", "WSF_WEAPONS_MANAGER_SAM",
    "WSF_WEAPONS_MANAGER_AI", "WSF_UPLINK_PROCESSOR",
    "WSF_UNCLASS_DISSEMINATE_C", "WSF_UNCLASS_BM",
    "WSF_UNCLASS_ASSET_MANAGER", "WSF_SCRIPT_LAUNCH_COMPUTER",
    "WSF_EXPLICIT_WEAPON", "WSF_IMPLICIT_WEAPON",
    "WSF_AIR_TO_AIR_MISSILE", "WSF_CHAFF_WEAPON",
    "WSF_GRADUATED_LETHALITY", "WSF_SPHERICAL_LETHALITY",
    "WSF_AIR_TARGET_FUSE", "WSF_GROUND_TARGET_FUSE",
    "WSF_WEAPON_FUSE", "WSF_GUIDANCE_COMPUTER",
    "WSF_AIR_TO_AIR_LAUNCH_COMPUTER", "WSF_ATG_LAUNCH_COMPUTER",
    "WSF_ATA_LAUNCH_COMPUTER", "WSF_FIRES_LAUNCH_COMPUTER",
    "WSF_OLD_GUIDANCE_COMPUTER", "WSF_BALLISTIC_MISSILE_LAUNCH_COMPUTER",
    "WSF_COMM_TRANSCEIVER", "WSF_COMM_XMTR", "WSF_COMM_RCVR",
    "WSF_COMM_ROUTER", "WSF_RADIO_TRANSCEIVER", "WSF_RADIO_XMTR",
    "WSF_RADIO_RCVR", "WSF_COMM_ROUTER_PROTOCOL_AD_HOC",
    "WSF_COMM_NETWORK_AD_HOC", "WSF_TRACK_MESSAGE", "WSF_CONTROL_MESSAGE",
    "WSF_ASSET_MESSAGE", "WSF_TRACK_DROP_MESSAGE", "WSF_TRACK_NOTIFY_MESSAGE",
    "WSF_ELECTRONIC_ATTACK", "WSF_ELECTRONIC_PROTECT",
    "WSF_EA_TECHNIQUE", "WSF_EP_TECHNIQUE", "WSF_SLB_EFFECT",
    "WSF_SLC_EFFECT", "WSF_RPJ_EFFECT", "WSF_FALSE_TARGET_EFFECT",
    "WSF_FALSE_TARGET", "WSF_JAMMER_POWER_EFFECT", "WSF_POWER_EFFECT",
    "WSF_AGILITY_EFFECT", "WSF_TRACK_EFFECT", "WSF_COVER_PULSE_EFFECT",
    "WSF_PULSE_SUPPRESS_EFFECT", "WSF_SIMPLE_FT_EFFECT", "WSF_POL_MOD_EFFECT",
    "WSF_CYBER_ATTACK", "WSF_CYBER_PROTECT", "WSF_CYBER_SCRIPT_EFFECT",
    "WSF_CYBER_DETONATE_EFFECT", "WSF_CYBER_MAN_IN_THE_MIDDLE_EFFECT",
    "WSF_CYBER_CONSTRAINT", "WSF_FUEL", "WSF_BRAWLER_FUEL",
    "WSF_TABULAR_RATE_FUEL", "WSF_RADAR_SIGNATURE", "WSF_LASER_DESIGNATOR",
    "WSF_CHAFF_PARCEL", "WSF_TRACK_MANAGER",
}


def load_taxonomy():
    raw = TAXONOMY_PATH.read_text(encoding="utf-8-sig")
    taxonomy = json.loads(raw)
    categories = taxonomy.get("categories", [])
    by_id = {item["id"]: item for item in categories}

    syntax_ids = {
        item["id"] for item in categories if item.get("affects_syntax", False)
    } or DEFAULT_SYNTAX_ERROR_IDS
    static_blocking_ids = {
        item["id"] for item in categories if item.get("blocks_static_pass", False)
    } or DEFAULT_STATIC_BLOCKING_ERROR_IDS

    return taxonomy, by_id, frozenset(syntax_ids), frozenset(static_blocking_ids)


ERROR_TAXONOMY, ERROR_TAXONOMY_BY_ID, SYNTAX_ERROR_IDS, STATIC_BLOCKING_ERROR_IDS = load_taxonomy()


def make_finding(error_id: str, line: int, message: str) -> dict:
    return {"error_id": error_id, "line": line, "message": message}


def build_block(head, parts, line_no):
    if head == "platform_type":
        wsf_type = parts[2] if len(parts) >= 3 else ""
    elif head == "mover":
        wsf_type = parts[1] if len(parts) >= 2 else ""
    elif head in {"sensor", "weapon", "processor"}:
        wsf_type = parts[2] if len(parts) >= 3 else ""
    else:
        wsf_type = ""

    return {
        "kind": head,
        "line": line_no,
        "name": parts[1] if len(parts) >= 2 else "",
        "wsf_type": wsf_type,
        "has_transmitter": False,
        "has_constant_pattern": False,
    }


def find_enclosing_block(stack, kind):
    for block in reversed(stack):
        if block["kind"] == kind:
            return block
    return None


def check_units(lines):
    errors = []
    unit_pattern = re.compile(
        r"\b(m/sec|km/hr|knots|sec|min|hr|m|km|ft|fps|nm|deg|rad|g|ghz|mhz|khz|hz|kw|db|msl|agl)\b",
        re.IGNORECASE,
    )
    numeric_pattern = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?$")
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts and parts[0] in UNIT_COMMANDS:
            tokens = parts[1:]
            if not tokens:
                continue
            if any(token.lower() == "microsec" for token in tokens):
                errors.append((line_no, "unsupported unit microsec"))
                continue
            if numeric_pattern.match(tokens[0]) and not unit_pattern.search(" ".join(tokens[1:])):
                errors.append((line_no, "numeric argument missing unit"))
    return errors


def is_block_start(head, parts, stack):
    if head not in BLOCK_STARTS:
        return False
    if head == "antenna_pattern":
        if stack and stack[-1]["kind"] in ANTENNA_REFERENCE_PARENTS:
            return False
    return True


def check_blocks(lines):
    stack = []
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]
        if is_block_start(head, parts, stack):
            stack.append(build_block(head, parts, line_no))
        elif head in END_TO_START:
            if not stack:
                errors.append((line_no, f"unexpected {head}"))
                continue
            expected_block = stack.pop()
            expected_end = BLOCK_STARTS[expected_block["kind"]]
            if head != expected_end:
                errors.append((line_no, f"{head} closes {expected_block['kind']} from line {expected_block['line']}"))
    for block in stack:
        errors.append((block["line"], f"missing {BLOCK_STARTS[block['kind']]}"))
    return errors


def extract_defined_symbols(lines):
    platform_types = set()
    antenna_patterns = {}
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            block = build_block(head, parts, line_no)
            stack.append(block)
            if head == "platform_type" and block["name"]:
                platform_types.add(block["name"])
            elif head == "antenna_pattern" and block["name"]:
                antenna_patterns[block["name"]] = line_no
            continue

        if head in END_TO_START and stack:
            stack.pop()

    return platform_types, antenna_patterns


def check_references(lines):
    platform_types, antenna_patterns = extract_defined_symbols(lines)
    errors = []
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        head = parts[0]

        if is_block_start(head, parts, stack):
            stack.append(build_block(head, parts, line_no))
            continue

        if head in END_TO_START:
            if stack:
                stack.pop()
            continue

        current_kind = stack[-1]["kind"] if stack else ""

        if head == "platform" and len(parts) >= 3 and parts[2] not in platform_types:
            errors.append((line_no, f"undefined platform type {parts[2]}"))

        if head == "antenna_pattern" and len(parts) >= 2 and current_kind in ANTENNA_REFERENCE_PARENTS:
            if parts[1] not in antenna_patterns:
                errors.append((line_no, f"undefined antenna pattern {parts[1]}"))

    return errors


def check_coordinates(lines):
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line.startswith("position "):
            continue
        if "altitude" in line:
            if not re.search(r"\b\d+(\.\d+)?\s+(m|ft)\s+(msl|agl)\b", line):
                errors.append((line_no, "invalid altitude format"))
        else:
            parts = line.split()
            if len(parts) < 4:
                errors.append((line_no, "position too short"))
        if not (
            re.search(r"\b\d+(\.\d+)?[ns]\b", line.lower())
            and re.search(r"\b\d+(\.\d+)?[ew]\b", line.lower())
        ):
            if not re.search(r"position\s+-?\d+(\.\d+)?\s+-?\d+(\.\d+)?\s+-?\d+(\.\d+)?", line.lower()):
                errors.append((line_no, "invalid coordinate format"))
    return errors


def check_hallucinated_types(lines):
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        for token in line.split():
            if token.startswith("WSF_") and token not in VALID_WSFS:
                errors.append((line_no, f"unknown or ungrounded type {token}"))
    return errors


def check_required_fields(lines):
    text = "\n".join(lines)
    errors = []
    if "end_time" not in text:
        errors.append((0, "missing end_time"))
    if "platform " in text and "route" not in text and "position " not in text:
        errors.append((0, "platforms missing route or position"))
    return errors


def check_script_language(lines):
    errors = []
    text = "\n".join(lines)
    if "cout <<" in text:
        errors.append((0, "unsupported cout"))
    if re.search(r"\?.*:", text):
        errors.append((0, "unsupported ternary operator"))
    if "fmod(" in text:
        errors.append((0, "unsupported fmod"))
    return errors


def check_component_syntax(lines):
    findings = []
    stack = []

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        head = parts[0]
        current_kind = stack[-1]["kind"] if stack else ""
        current_sensor = find_enclosing_block(stack, "sensor")
        current_mover = find_enclosing_block(stack, "mover")

        if is_block_start(head, parts, stack):
            if head == "route" and current_kind != "platform":
                findings.append(make_finding("E007", line_no, "route block must be nested under platform"))
            if head == "constant_pattern" and current_kind != "antenna_pattern":
                findings.append(make_finding("E007", line_no, "constant_pattern must be nested under antenna_pattern"))

            block = build_block(head, parts, line_no)

            if head == "transmitter" and current_sensor is not None:
                current_sensor["has_transmitter"] = True
            if head == "constant_pattern":
                antenna_block = find_enclosing_block(stack, "antenna_pattern")
                if antenna_block is not None:
                    antenna_block["has_constant_pattern"] = True

            stack.append(block)
            continue

        if head in END_TO_START:
            if stack:
                closed = stack.pop()
                if closed["kind"] == "sensor" and closed["wsf_type"] == "WSF_RADAR_SENSOR" and not closed["has_transmitter"]:
                    findings.append(make_finding("E007", closed["line"], "WSF_RADAR_SENSOR missing transmitter block"))
                if closed["kind"] == "antenna_pattern" and not closed["has_constant_pattern"]:
                    findings.append(make_finding("E007", closed["line"], "antenna_pattern missing constant_pattern block"))
            continue

        if head in SUBCOMPONENT_PSEUDO_KEYWORDS:
            findings.append(make_finding("E007", line_no, f"{head} is a pseudo keyword and cannot be used as a standalone command"))

        expected_parent = NESTED_ONLY_KEYWORDS.get(head)
        if expected_parent and current_kind != expected_parent:
            findings.append(make_finding("E007", line_no, f"{head} must be nested under {expected_parent}"))

        if head == "antenna_pattern" and len(parts) >= 2 and current_kind not in ANTENNA_REFERENCE_PARENTS:
            findings.append(make_finding("E007", line_no, "antenna_pattern reference must be nested under transmitter or receiver"))

        if current_mover is not None and current_mover["wsf_type"] == "WSF_AIR_MOVER" and head in AIR_MOVER_UNSUPPORTED_COMMANDS:
            findings.append(make_finding("E007", line_no, f"{head} is not supported by WSF_AIR_MOVER"))

    return findings


def static_analysis(script_text: str):
    lines = script_text.splitlines()
    findings = []

    mapping = {
        "E001": check_units(lines),
        "E002": check_blocks(lines),
        "E003": check_references(lines),
        "E004": check_coordinates(lines),
        "E005": check_hallucinated_types(lines),
        "E006": check_required_fields(lines),
        "E008": check_script_language(lines),
    }

    for error_id, items in mapping.items():
        for line_no, message in items:
            findings.append(make_finding(error_id, line_no, message))

    findings.extend(check_component_syntax(lines))
    return findings


def analyze_script_text(script_text: str, script_label: str = "") -> dict:
    findings = static_analysis(script_text)
    static_error_ids = sorted({item["error_id"] for item in findings})
    primary_error = findings[0]["error_id"] if findings else ""

    return {
        "script": script_label,
        "syntax_correct": not any(item["error_id"] in SYNTAX_ERROR_IDS for item in findings),
        "static_pass": not any(item["error_id"] in STATIC_BLOCKING_ERROR_IDS for item in findings),
        "primary_error": primary_error,
        "static_error_ids": static_error_ids,
        "findings": findings,
    }


def read_script(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def check_script(path: Path) -> dict:
    return analyze_script_text(read_script(path), script_label=str(path))


def collect_scripts(inputs: list[Path], recursive: bool) -> list[Path]:
    scripts = []
    for item in inputs:
        if item.is_file():
            scripts.append(item)
        elif item.is_dir():
            pattern = "**/*.txt" if recursive else "*.txt"
            scripts.extend(sorted(item.glob(pattern)))
    return sorted(dict.fromkeys(scripts))


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    syntax_correct = sum(1 for row in results if row["syntax_correct"])
    static_pass = sum(1 for row in results if row["static_pass"])
    error_counter = Counter()
    for row in results:
        for error_id in row["static_error_ids"]:
            error_counter[error_id] += 1

    return {
        "total": total,
        "syntax_correct": syntax_correct,
        "static_pass": static_pass,
        "syntax_correct_rate": round(syntax_correct / total, 4) if total else 0.0,
        "static_pass_rate": round(static_pass / total, 4) if total else 0.0,
        "error_counts": dict(sorted(error_counter.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Static Checker v1 on AFSIM .txt scripts.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Script file(s) or directory path(s).")
    parser.add_argument("--recursive", action="store_true", help="Scan directories recursively for *.txt files.")
    parser.add_argument("--summary-only", action="store_true", help="Only print aggregate summary JSON.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit with code 1 when any static finding exists.")
    args = parser.parse_args()

    scripts = collect_scripts(args.inputs, args.recursive)
    results = [check_script(path) for path in scripts]
    payload = build_summary(results) if args.summary_only else {"summary": build_summary(results), "results": results}

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.fail_on_findings and any(row["findings"] for row in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
