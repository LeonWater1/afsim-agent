#!/usr/bin/env python3
"""Validate Benchmark v2 data format, integrity, and cross-references."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "validation_report.json"

def validate_jsonl(filename: str) -> dict:
    path = ROOT / filename
    result = {"file": filename, "exists": path.exists(), "records": 0, "errors": []}
    if not result["exists"]:
        result["errors"].append("File not found")
        return result
    with open(path, encoding="utf-8-sig") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if "id" not in row:
                    result["errors"].append(f"Line {i}: missing 'id'")
                if "type" not in row:
                    result["errors"].append(f"Line {i}: missing 'type'")
                result["records"] += 1
            except json.JSONDecodeError as e:
                result["errors"].append(f"Line {i}: JSON error — {e}")
    return result

def main() -> int:
    report = {"report": "benchmark_extended_validation", "overall_status": "PASS", "results": []}
    files = ["type_a_instruction_to_script.jsonl", "type_b_script_to_instruction.jsonl",
             "type_c_instruction_to_ir.jsonl", "type_d_ir_to_script.jsonl",
             "type_e_error_to_repair.jsonl"]

    all_ids = set()
    total_errors = 0

    for f in files:
        r = validate_jsonl(f)
        report["results"].append(r)
        total_errors += len(r["errors"])
        path = ROOT / f
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if row.get("id"):
                        if row["id"] in all_ids:
                            r.setdefault("duplicates", []).append(row["id"])
                        all_ids.add(row["id"])
                except json.JSONDecodeError:
                    pass

        # Check minimum count
        if r["records"] < 5:
            r["errors"].append(f"Only {r['records']} records (min 5 required)")
            total_errors += 1

    # Oracle file check
    type_a = ROOT / "type_a_instruction_to_script.jsonl"
    oracle_ok = 0
    oracle_missing = 0
    if type_a.exists():
        for line in type_a.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            script = row.get("oracle_script", "")
            if script and (ROOT / script).exists():
                oracle_ok += 1
            elif script:
                oracle_missing += 1
    report["oracle_files"] = {"found": oracle_ok, "missing": oracle_missing}

    report["total_unique_ids"] = len(all_ids)
    report["total_errors"] = total_errors
    if total_errors > 0:
        report["overall_status"] = "FAIL"

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
