#!/usr/bin/env python3
"""
Validate benchmark oracle scripts with AFSIM mission.exe.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from run_mission import load_config


def display_path(path, root):
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def main():
    parser = argparse.ArgumentParser(description="Validate benchmark scripts")
    parser.add_argument(
        "--benchmark-dir",
        default="benchmarks/benchmark_v1",
        help="Benchmark directory containing scripts/",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout per script in seconds",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    benchmark_dir = (root / args.benchmark_dir).resolve()
    logs_dir = benchmark_dir / "validation_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    mission_exe = Path(config["mission_exe"])
    if not mission_exe.exists():
        print(f"mission.exe not found: {mission_exe}", file=sys.stderr)
        return 2

    tasks_file = benchmark_dir / "tasks.jsonl"
    script_entries = []
    if tasks_file.exists():
        for line in tasks_file.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            task = json.loads(line)
            source_hint = task.get("source_hint", "")
            if not source_hint:
                continue
            script = Path(source_hint)
            if not script.is_absolute():
                script = root / source_hint
            script_entries.append((task.get("id", script.stem), script.resolve()))
    else:
        scripts_dir = benchmark_dir / "scripts"
        (scripts_dir / "output").mkdir(parents=True, exist_ok=True)
        for script in sorted(scripts_dir.glob("*.txt")):
            if script.name.startswith("mission-"):
                continue
            script_entries.append((script.stem, script.resolve()))

    results = []
    for task_id, script in script_entries:
        (script.parent / "output").mkdir(parents=True, exist_ok=True)

        safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in task_id)
        log_path = logs_dir / f"{safe_id}_{script.stem}.log"
        cmd = [str(mission_exe), "-es", "-sm", str(script)]
        started_at = datetime.now().isoformat(timespec="seconds")
        try:
            result = subprocess.run(
                cmd,
                cwd=str(script.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=args.timeout,
            )
            output = result.stdout + ("\nSTDERR:\n" + result.stderr if result.stderr else "")
            log_path.write_text(output, encoding="utf-8")
            status = "PASS" if result.returncode == 0 else "FAIL"
            return_code = result.returncode
            error = ""
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + ("\nSTDERR:\n" + exc.stderr if exc.stderr else "")
            log_path.write_text(output, encoding="utf-8", errors="replace")
            status = "TIMEOUT"
            return_code = None
            error = f"Timed out after {args.timeout} seconds"

        results.append(
            {
                "id": task_id,
                "script": display_path(script, root),
                "status": status,
                "return_code": return_code,
                "started_at": started_at,
                "log": str(log_path.relative_to(root)).replace("\\", "/"),
                "error": error,
            }
        )
        print(f"{status:7} {script.name}")

    summary = {
        "benchmark_dir": str(benchmark_dir.relative_to(root)).replace("\\", "/"),
        "validated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "pass": sum(1 for item in results if item["status"] == "PASS"),
        "fail": sum(1 for item in results if item["status"] == "FAIL"),
        "timeout": sum(1 for item in results if item["status"] == "TIMEOUT"),
        "results": results,
    }
    result_path = benchmark_dir / "validation_results.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"summary total={summary['total']} pass={summary['pass']} "
        f"fail={summary['fail']} timeout={summary['timeout']}"
    )
    return 0 if summary["fail"] == 0 and summary["timeout"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
