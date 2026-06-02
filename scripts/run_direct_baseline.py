#!/usr/bin/env python3
"""
Run a direct-prompt baseline for AFSIM benchmark tasks.

This baseline intentionally does not use IR, retrieval, or demo grounding.
It asks DeepSeek to generate scripts from task text alone, then performs static
checks, mission execution, and summary stats.
"""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from run_mission import load_config


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

# Verified WSF_ types extracted from AFSIM 2.9.0 demo scripts that pass mission.exe.
# Types are grouped by category for maintainability.
VALID_WSFS = {
    # Platform / base types
    "WSF_PLATFORM", "WSF_BRAWLER_PLATFORM", "WSF_GROUP",
    # Movers
    "WSF_AIR_MOVER", "WSF_KINEMATIC_MOVER", "WSF_GUIDED_MOVER",
    "WSF_GROUND_MOVER", "WSF_BRAWLER_MOVER", "WSF_SIX_DOF_MOVER",
    "WSF_FIRES_MOVER", "WSF_STRAIGHT_LINE_MOVER", "WSF_OFFSET_MOVER",
    "WSF_POINT_MASS_SIX_DOF_MOVER", "WSF_UNGUIDED_MOVER",
    "WSF_STATIONARY_MOVER",
    "WSF_INTEGRATING_SPACE_MOVER", "WSF_OLD_GUIDED_MOVER",
    "WSF_AERO",
    # Sensors
    "WSF_RADAR_SENSOR", "WSF_ESM_SENSOR", "WSF_EOIR_SENSOR",
    "WSF_GEOMETRIC_SENSOR", "WSF_SAR_SENSOR", "WSF_IRST_SENSOR",
    "WSF_ACOUSTIC_SENSOR", "WSF_LASER_TRACKER",
    "WSF_RF_JAMMER",
    # Processors
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
    # Weapons / lethality
    "WSF_EXPLICIT_WEAPON", "WSF_IMPLICIT_WEAPON",
    "WSF_AIR_TO_AIR_MISSILE", "WSF_CHAFF_WEAPON",
    "WSF_GRADUATED_LETHALITY", "WSF_SPHERICAL_LETHALITY",
    "WSF_AIR_TARGET_FUSE", "WSF_GROUND_TARGET_FUSE",
    "WSF_WEAPON_FUSE",
    # Launch computers
    "WSF_GUIDANCE_COMPUTER", "WSF_AIR_TO_AIR_LAUNCH_COMPUTER",
    "WSF_ATG_LAUNCH_COMPUTER", "WSF_ATA_LAUNCH_COMPUTER",
    "WSF_FIRES_LAUNCH_COMPUTER", "WSF_OLD_GUIDANCE_COMPUTER",
    "WSF_BALLISTIC_MISSILE_LAUNCH_COMPUTER",
    # Comm / messages
    "WSF_COMM_TRANSCEIVER", "WSF_COMM_XMTR", "WSF_COMM_RCVR",
    "WSF_COMM_ROUTER", "WSF_RADIO_TRANSCEIVER", "WSF_RADIO_XMTR",
    "WSF_RADIO_RCVR", "WSF_COMM_ROUTER_PROTOCOL_AD_HOC",
    "WSF_COMM_NETWORK_AD_HOC",
    "WSF_TRACK_MESSAGE", "WSF_CONTROL_MESSAGE", "WSF_ASSET_MESSAGE",
    "WSF_TRACK_DROP_MESSAGE", "WSF_TRACK_NOTIFY_MESSAGE",
    # Electronic warfare / effects
    "WSF_ELECTRONIC_ATTACK", "WSF_ELECTRONIC_PROTECT",
    "WSF_EA_TECHNIQUE", "WSF_EP_TECHNIQUE",
    "WSF_SLB_EFFECT", "WSF_SLC_EFFECT", "WSF_RPJ_EFFECT",
    "WSF_FALSE_TARGET_EFFECT", "WSF_FALSE_TARGET",
    "WSF_JAMMER_POWER_EFFECT", "WSF_POWER_EFFECT",
    "WSF_AGILITY_EFFECT", "WSF_TRACK_EFFECT",
    "WSF_COVER_PULSE_EFFECT", "WSF_PULSE_SUPPRESS_EFFECT",
    "WSF_SIMPLE_FT_EFFECT", "WSF_POL_MOD_EFFECT",
    # Cyber
    "WSF_CYBER_ATTACK", "WSF_CYBER_PROTECT",
    "WSF_CYBER_SCRIPT_EFFECT", "WSF_CYBER_DETONATE_EFFECT",
    "WSF_CYBER_MAN_IN_THE_MIDDLE_EFFECT", "WSF_CYBER_CONSTRAINT",
    # Misc
    "WSF_FUEL", "WSF_BRAWLER_FUEL", "WSF_TABULAR_RATE_FUEL",
    "WSF_RADAR_SIGNATURE", "WSF_LASER_DESIGNATOR",
    "WSF_CHAFF_PARCEL", "WSF_TRACK_MANAGER",
}

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


def load_tasks(tasks_path: Path):
    tasks = []
    for line in tasks_path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            tasks.append(json.loads(line))
    return tasks


def build_deepseek_messages(task):
    system_prompt = """You generate AFSIM 2.9.0 mission scripts.
//Prompt guidelines:
This is a direct-prompt baseline. Do not use retrieval, examples, oracle scripts, IR, grounding tables, or repair feedback. Use only the user task and your own model knowledge.

Return exactly one complete AFSIM script as plain text. Do not include markdown fences, explanation, JSON, or commentary.

Important constraints:
- Use .txt-style AFSIM/WSF syntax, not pseudo-code.
- Include all required end_xxx tags.
- Include units for physical values.
- Include end_time.
- Prefer simple executable scenario structure when uncertain.
"""
    user_prompt = f"""Task ID: {task['id']}
Natural-language request:
{task['input']}

Generate the complete AFSIM script now."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def strip_code_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip() + "\n"


def call_deepseek(task, api_key, model, api_timeout, max_retries):
    payload = {
        "model": model,
        "messages": build_deepseek_messages(task),
        "temperature": 0.0,
        "max_tokens": 4096,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    request = urllib.request.Request(DEEPSEEK_API_URL, data=body, headers=headers, method="POST")

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=api_timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            return strip_code_fences(data["choices"][0]["message"]["content"])
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"DeepSeek generation failed for {task['id']}: {last_error}")


def check_units(lines):
    errors = []
    unit_pattern = re.compile(
        r"\b(m/sec|km/hr|knots|sec|min|hr|m|km|ft|nm|deg|rad|g|ghz|mhz|hz|kw|db|msl|agl)\b",
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
        # antenna_pattern can also be a reference line inside transmitter/receiver.
        if stack and stack[-1][0] in {"transmitter", "receiver"}:
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
            stack.append((head, line_no))
        elif head in END_TO_START:
            if not stack:
                errors.append((line_no, f"unexpected {head}"))
                continue
            expected_start, start_line = stack.pop()
            expected_end = BLOCK_STARTS[expected_start]
            if head != expected_end:
                errors.append((line_no, f"{head} closes {expected_start} from line {start_line}"))
    for start, line_no in stack:
        errors.append((line_no, f"missing {BLOCK_STARTS[start]}"))
    return errors


def extract_defined_symbols(lines):
    platform_types = set()
    antenna_patterns = set()
    internal_components = defaultdict(set)
    current_platform_type = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "platform_type" and len(parts) >= 2:
            current_platform_type = parts[1]
            platform_types.add(parts[1])
        elif parts[0] == "end_platform_type":
            current_platform_type = None
        elif parts[0] == "antenna_pattern" and len(parts) >= 2:
            antenna_patterns.add(parts[1])
        elif current_platform_type and parts[0] in {"sensor", "weapon", "processor"} and len(parts) >= 2:
            internal_components[current_platform_type].add(parts[1])
    return platform_types, antenna_patterns, internal_components


def check_references(lines):
    platform_types, antenna_patterns, _ = extract_defined_symbols(lines)
    errors = []
    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "platform" and len(parts) >= 3 and parts[2] not in platform_types:
            errors.append((line_no, f"undefined platform type {parts[2]}"))
        if parts[0] == "antenna_pattern" and len(parts) >= 2 and line_no > 1:
            continue
        if parts[0] == "antenna_pattern" and len(parts) >= 2 and parts[1] not in antenna_patterns:
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
            findings.append({"error_id": error_id, "line": line_no, "message": message})

    # Heuristic component mismatch checks.
    if "WSF_RADAR_SENSOR" in script_text and "transmitter" not in script_text:
        findings.append({"error_id": "E007", "line": 0, "message": "radar sensor missing transmitter"})
    if "antenna_pattern" in script_text and "constant_pattern" not in script_text:
        findings.append({"error_id": "E007", "line": 0, "message": "antenna pattern missing constant_pattern"})

    return findings


def semantic_match(task, script_text, mission_status):
    text = task["input"]
    script_upper = script_text.upper()
    if mission_status != "PASS":
        return False

    checks = []
    component_map = {
        "Platform": lambda s: "platform " in s.lower() and "platform_type " in s.lower(),
        "Route": lambda s: "route" in s.lower(),
        "Mover": lambda s: "mover " in s.lower(),
        "Sensor": lambda s: "sensor " in s.lower(),
        "Weapon": lambda s: "weapon " in s.lower(),
        "Processor": lambda s: "processor " in s.lower(),
        "Comm": lambda s: "comm " in s.lower(),
        "Acoustic": lambda s: "ACOUSTIC" in s.upper(),
        "BehaviorTree": lambda s: "BEHAVIOR_TREE" in s.upper(),
        "Space": lambda s: "SPACE_MOVER" in s.upper(),
        "ElectronicWarfare": lambda s: "JAMMER" in s.upper() or "ESM" in s.upper() or "CHAFF" in s.upper(),
        "IADS": lambda s: "SAM" in s.upper() and "RADAR" in s.upper(),
        "LaserDesignator": lambda s: "LASER" in s.upper(),
        "Coverage": lambda s: "HEATMAP" in s.upper(),
        "Cyber": lambda s: "CYBER" in s.upper(),
        "Fires": lambda s: "ARTILLERY" in s.upper(),
    }

    for component in task.get("covered_components", []):
        matcher = component_map.get(component)
        if matcher:
            checks.append(matcher(script_text))

    if "护航" in text or "防御反空" in text:
        checks.append("blue_hvaa" in script_text)
    if "空战" in text:
        checks.append("side red" in script_text and "side blue" in script_text)
    if not checks:
        checks.append("route" in script_text.lower())
    return all(checks)


def infer_primary_error(findings, mission_status):
    if findings:
        return findings[0]["error_id"]
    if mission_status == "FAIL":
        return "E009"
    return ""


def mission_error_to_taxonomy(log_text: str):
    upper = log_text.upper()
    if "TERRAIN DIRECTORY DOES NOT EXIST" in upper or "UNABLE TO OPEN OUTPUT FILE" in upper:
        return "E009"
    if "ADD FAILED FOR NIMA DTED" in upper or "PERMISSION DENIED" in upper:
        return "E009"
    if "UNKNOWN COMMAND:" in upper:
        return "E007"
    if "COULD NOT FIND WEAPON WSF_" in upper or "COULD NOT FIND SENSOR WSF_" in upper or "COULD NOT FIND PROCESSOR WSF_" in upper:
        return "E005"
    if "COULD NOT FIND " in upper or "DOES NOT EXIST" in upper or "UNKNOWN" in upper:
        return "E003"
    return ""


def write_prompt_template(path: Path, model: str):
    content = f"""# Direct Prompt Template v1

该 baseline 模拟“自然语言 -> AFSIM 脚本”的直接生成，不使用：

- AFSIM-IR
- grounding 库
- demo 检索
- reference 检索

统一提示意图：

1. 仅根据任务描述猜测场景结构。
2. 尽量一次性输出完整 AFSIM 脚本。
3. 不做执行反馈修复。

## 当前运行配置

- generator: `deepseek`
- model: `{model}`

DeepSeek 模式下的系统提示只包含 direct generation 约束，不注入 benchmark oracle、demo、reference 文档或错误修复反馈。

## DeepSeek system prompt

```text
You generate AFSIM 2.9.0 mission scripts.

This is a direct-prompt baseline. Do not use retrieval, examples, oracle scripts, IR, grounding tables, or repair feedback. Use only the user task and your own model knowledge.

Return exactly one complete AFSIM script as plain text. Do not include markdown fences, explanation, JSON, or commentary.

Important constraints:
- Use .txt-style AFSIM/WSF syntax, not pseudo-code.
- Include all required end_xxx tags.
- Include units for physical values.
- Include end_time.
- Prefer simple executable scenario structure when uncertain.
```
"""
    path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run direct baseline on benchmark tasks")
    parser.add_argument("--benchmark-dir", default="benchmarks/benchmark_v1")
    parser.add_argument("--output-dir", default="baseline_direct_v1")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--model", default="deepseek-v4-pro", help="DeepSeek model name")
    parser.add_argument("--api-timeout", type=int, default=120, help="DeepSeek API timeout per task")
    parser.add_argument("--max-retries", type=int, default=2, help="DeepSeek API retries per task")
    parser.add_argument("--limit", type=int, default=0, help="Optional number of tasks to run")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    benchmark_dir = (root / args.benchmark_dir).resolve()
    output_dir = (root / args.output_dir).resolve()
    scripts_dir = output_dir / "generated_scripts"
    logs_dir = output_dir / "mission_logs"

    output_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    write_prompt_template(output_dir / "prompt_template.md", args.model)

    tasks = load_tasks(benchmark_dir / "tasks.jsonl")
    if args.limit:
        tasks = tasks[: args.limit]
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is required")

    config = load_config()
    mission_exe = Path(config["mission_exe"])

    summary_rows = []
    error_counter = Counter()
    mission_counter = Counter()

    for task in tasks:
        script_text = call_deepseek(task, api_key, args.model, args.api_timeout, args.max_retries)
        script_path = scripts_dir / f"{task['id']}.txt"
        (script_path.parent / "output").mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text, encoding="utf-8")

        findings = static_analysis(script_text)
        static_error_ids = sorted({item["error_id"] for item in findings})
        static_blocking = any(item["error_id"] in {"E001", "E002", "E003", "E004", "E005", "E006", "E007", "E008"} for item in findings)

        cmd = [str(mission_exe), "-es", "-sm", str(script_path)]
        mission_status = "NOT_RUN"
        return_code = None
        mission_taxonomy = ""
        log_text = ""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(script_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            return_code = result.returncode
            log_text = result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else "")
            mission_status = "PASS" if result.returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired as exc:
            log_text = (exc.stdout or "") + ("\nSTDERR:\n" + exc.stderr if exc.stderr else "")
            mission_status = "TIMEOUT"

        (logs_dir / f"{task['id']}.log").write_text(log_text, encoding="utf-8", errors="replace")
        mission_taxonomy = mission_error_to_taxonomy(log_text)
        semantic_ok = semantic_match(task, script_text, mission_status)

        primary_error = infer_primary_error(findings, mission_status)
        secondary_errors = sorted(
            {
                item["error_id"] for item in findings if item["error_id"] != primary_error
            }
        )
        if mission_taxonomy and primary_error == "E009" and not findings:
            primary_error = mission_taxonomy
        elif mission_taxonomy and mission_taxonomy not in {primary_error, *secondary_errors}:
            if primary_error:
                secondary_errors.append(mission_taxonomy)
            else:
                primary_error = mission_taxonomy

        for error_id in [primary_error] + secondary_errors:
            if error_id:
                error_counter[error_id] += 1
        mission_counter[mission_status] += 1

        summary_rows.append(
            {
                "id": task["id"],
                "input": task["input"],
                "generated_script": str(script_path.relative_to(root)).replace("\\", "/"),
                "static_errors": findings,
                "static_error_ids": static_error_ids,
                "syntax_correct": not any(item["error_id"] in {"E001", "E002", "E004", "E007", "E008"} for item in findings),
                "static_pass": not static_blocking,
                "mission_status": mission_status,
                "return_code": return_code,
                "mission_log": str((logs_dir / f"{task['id']}.log").relative_to(root)).replace("\\", "/"),
                "primary_error": primary_error,
                "secondary_errors": secondary_errors,
                "semantic_match": semantic_ok,
            }
        )
        print(f"{task['id']}: static={len(static_error_ids)} mission={mission_status} semantic={semantic_ok}")

    total = len(summary_rows)
    syntax_correct = sum(1 for row in summary_rows if row["syntax_correct"])
    static_pass = sum(1 for row in summary_rows if row["static_pass"])
    mission_pass = sum(1 for row in summary_rows if row["mission_status"] == "PASS")
    semantic_pass = sum(1 for row in summary_rows if row["semantic_match"])
    failed = total - mission_pass

    summary = {
        "name": "baseline_direct_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generator": "deepseek",
        "model": args.model,
        "benchmark_dir": str(benchmark_dir.relative_to(root)).replace("\\", "/"),
        "total": total,
        "syntax_correct_rate": round(syntax_correct / total, 4) if total else 0.0,
        "static_pass_rate": round(static_pass / total, 4) if total else 0.0,
        "mission_success_rate": round(mission_pass / total, 4) if total else 0.0,
        "error_rate": round(failed / total, 4) if total else 0.0,
        "semantic_match_rate": round(semantic_pass / total, 4) if total else 0.0,
        "counts": {
            "syntax_correct": syntax_correct,
            "static_pass": static_pass,
            "mission_pass": mission_pass,
            "mission_fail": mission_counter["FAIL"],
            "mission_timeout": mission_counter["TIMEOUT"],
            "semantic_match": semantic_pass,
        },
        "error_stats": dict(sorted(error_counter.items())),
        "results": summary_rows,
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "results.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in summary_rows) + "\n",
        encoding="utf-8",
    )
    (output_dir / "error_stats.json").write_text(
        json.dumps({"error_stats": dict(sorted(error_counter.items()))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = f"""# baseline_direct_v1

## 设置

- benchmark: `{summary['benchmark_dir']}`
- total: {total}
- timeout_per_case: {args.timeout} sec
- generator: `deepseek`
- model: `{summary['model']}`
- generation_policy: direct prompt only, no IR, no retrieval, no grounding, no repair feedback

## 指标

- 语法正确率: {summary['counts']['syntax_correct']}/{total} = {summary['syntax_correct_rate']:.2%}
- 静态通过率: {summary['counts']['static_pass']}/{total} = {summary['static_pass_rate']:.2%}
- 可执行率: {summary['counts']['mission_pass']}/{total} = {summary['mission_success_rate']:.2%}
- 错误率: {failed}/{total} = {summary['error_rate']:.2%}
- 语义匹配率: {summary['counts']['semantic_match']}/{total} = {summary['semantic_match_rate']:.2%}

## 主要错误分布

{chr(10).join(f"- {key}: {value}" for key, value in sorted(error_counter.items()))}

## 说明

- 该结果来自 DeepSeek API 的真实 direct prompt 生成，未使用 RAG、IR、grounding、demo oracle 或执行反馈修复。
- 典型失败表现是生成“AFSIM 风格伪代码”，例如 `scenario/end_scenario`、`model = ...`、`--` 注释等 mission.exe 不接受的结构。
- 该 baseline 测到的是无检索、无结构化约束时模型直接写 AFSIM DSL 的能力边界。
"""
    (output_dir / "README.md").write_text(md, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
