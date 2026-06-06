#!/usr/bin/env python3
"""
Task-009: Evaluation Protocol v1

This script reads method outputs such as baseline_direct_v1 and baseline_rag_v1,
refreshes static metrics from the current static checker when generated scripts
are available, and emits a comparable scoreboard.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from core.static_checker import check_script


ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "docs" / "machine" / "evaluation_protocol_v1.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def resolve_run_dir(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def metric_from_bool_rows(rows, field_name: str):
    values = [row[field_name] for row in rows if field_name in row and isinstance(row[field_name], bool)]
    if not values:
        return None
    numerator = sum(1 for value in values if value)
    denominator = len(values)
    return {
        "value": round(numerator / denominator, 4) if denominator else 0.0,
        "numerator": numerator,
        "denominator": denominator,
        "applicable": True,
        "source": f"results.{field_name}",
    }


def metric_from_mission_rows(rows):
    values = [row["mission_status"] for row in rows if "mission_status" in row]
    if not values:
        return None
    numerator = sum(1 for value in values if value == "PASS")
    denominator = len(values)
    return {
        "value": round(numerator / denominator, 4) if denominator else 0.0,
        "numerator": numerator,
        "denominator": denominator,
        "applicable": True,
        "source": "results.mission_status",
    }


def metric_from_summary(summary, summary_field: str):
    if summary_field not in summary:
        return None
    return {
        "value": summary[summary_field],
        "numerator": None,
        "denominator": summary.get("total"),
        "applicable": True,
        "source": f"summary.{summary_field}",
    }


def refresh_static_by_script(run_dir: Path):
    scripts_dir = run_dir / "generated_scripts"
    if not scripts_dir.exists():
        return {}, None

    static_rows = {}
    for script_path in sorted(scripts_dir.glob("*.txt")):
        static_rows[script_path.stem] = check_script(script_path)

    total = len(static_rows)
    if total == 0:
        return static_rows, None

    syntax_correct = sum(1 for row in static_rows.values() if row["syntax_correct"])
    static_pass = sum(1 for row in static_rows.values() if row["static_pass"])
    error_counts = {}
    for row in static_rows.values():
        for error_id in row["static_error_ids"]:
            error_counts[error_id] = error_counts.get(error_id, 0) + 1

    return static_rows, {
        "total": total,
        "syntax_correct": syntax_correct,
        "static_pass": static_pass,
        "syntax_correct_rate": round(syntax_correct / total, 4),
        "static_pass_rate": round(static_pass / total, 4),
        "error_counts": dict(sorted(error_counts.items())),
    }


def refresh_static_from_results_rows(results_rows):
    static_rows = {}
    for row in results_rows:
        script_ref = row.get("generated_script")
        task_id = row.get("id")
        if not script_ref or not task_id:
            continue
        script_path = resolve_run_dir(script_ref)
        if not script_path.exists():
            continue
        static_rows[task_id] = check_script(script_path)

    total = len(static_rows)
    if total == 0:
        return static_rows, None

    syntax_correct = sum(1 for row in static_rows.values() if row["syntax_correct"])
    static_pass = sum(1 for row in static_rows.values() if row["static_pass"])
    error_counts = {}
    for row in static_rows.values():
        for error_id in row["static_error_ids"]:
            error_counts[error_id] = error_counts.get(error_id, 0) + 1

    return static_rows, {
        "total": total,
        "syntax_correct": syntax_correct,
        "static_pass": static_pass,
        "syntax_correct_rate": round(syntax_correct / total, 4),
        "static_pass_rate": round(static_pass / total, 4),
        "error_counts": dict(sorted(error_counts.items())),
    }


def merge_static_rows(results_rows, refreshed_static):
    if not refreshed_static:
        return results_rows

    merged = []
    for row in results_rows:
        merged_row = dict(row)
        static_row = refreshed_static.get(row.get("id", ""))
        if static_row is not None:
            merged_row["syntax_correct"] = static_row["syntax_correct"]
            merged_row["static_pass"] = static_row["static_pass"]
            merged_row["static_error_ids"] = static_row["static_error_ids"]
            merged_row["static_errors"] = static_row["findings"]
        merged.append(merged_row)
    return merged


def infer_method_type(method_name: str):
    name = method_name.lower()
    if "direct" in name:
        return "direct_prompt"
    if "rag" in name:
        return "rag"
    if "ir" in name:
        return "ir_only"
    return "full_agent"


def evaluate_run(run_dir: Path, protocol):
    summary_path = run_dir / "summary.json"
    results_path = run_dir / "results.jsonl"

    summary = load_json(summary_path) if summary_path.exists() else {}
    results_rows = load_jsonl(results_path) if results_path.exists() else []
    refreshed_static_rows, refreshed_static_summary = refresh_static_by_script(run_dir)
    if refreshed_static_summary is None and results_rows:
        refreshed_static_rows, refreshed_static_summary = refresh_static_from_results_rows(results_rows)
    merged_rows = merge_static_rows(results_rows, refreshed_static_rows)

    method_name = summary.get("name") or run_dir.name
    method_type = infer_method_type(method_name)
    total = summary.get("total") or len(merged_rows) or (refreshed_static_summary or {}).get("total", 0)

    metrics = {}
    for metric in protocol["metrics"]:
        metric_id = metric["id"]
        row_field = metric["row_field"]
        summary_field = metric["summary_field"]

        if metric_id == "mission_success_rate":
            value = metric_from_mission_rows(merged_rows) or metric_from_summary(summary, summary_field)
        elif metric_id == "script_correctness" and refreshed_static_summary is not None:
            value = {
                "value": refreshed_static_summary["syntax_correct_rate"],
                "numerator": refreshed_static_summary["syntax_correct"],
                "denominator": refreshed_static_summary["total"],
                "applicable": True,
                "source": "refreshed_static.syntax_correct_rate",
            }
        elif metric_id == "static_pass_rate" and refreshed_static_summary is not None:
            value = {
                "value": refreshed_static_summary["static_pass_rate"],
                "numerator": refreshed_static_summary["static_pass"],
                "denominator": refreshed_static_summary["total"],
                "applicable": True,
                "source": "refreshed_static.static_pass_rate",
            }
        else:
            value = metric_from_bool_rows(merged_rows, row_field) or metric_from_summary(summary, summary_field)

        if value is None:
            metrics[metric_id] = {
                "value": None,
                "numerator": None,
                "denominator": total or None,
                "applicable": False,
                "source": "not_available",
            }
        else:
            metrics[metric_id] = value

    if refreshed_static_summary is not None:
        error_stats = refreshed_static_summary["error_counts"]
    else:
        error_stats = summary.get("error_stats", {})

    notes = []
    if refreshed_static_summary is not None:
        notes.append("static metrics refreshed from current static_checker_v1")
    if not results_rows:
        notes.append("results.jsonl missing; metrics may be incomplete")

    return {
        "method": method_name,
        "method_type": method_type,
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "benchmark_dir": summary.get("benchmark_dir"),
        "total": total,
        "metrics": metrics,
        "error_stats": error_stats,
        "generator": summary.get("generator"),
        "model": summary.get("model"),
        "notes": notes,
    }


def rank_methods(method_rows):
    def sort_key(item):
        metrics = item["metrics"]
        return (
            metrics["mission_success_rate"]["value"] or -1.0,
            metrics["semantic_match_rate"]["value"] or -1.0,
            metrics["static_pass_rate"]["value"] or -1.0,
            metrics["script_correctness"]["value"] or -1.0,
        )

    ranked = sorted(method_rows, key=sort_key, reverse=True)
    return [
        {
            "rank": idx + 1,
            "method": row["method"],
            "mission_success_rate": row["metrics"]["mission_success_rate"]["value"],
            "semantic_match_rate": row["metrics"]["semantic_match_rate"]["value"],
            "static_pass_rate": row["metrics"]["static_pass_rate"]["value"],
            "script_correctness": row["metrics"]["script_correctness"]["value"],
        }
        for idx, row in enumerate(ranked)
    ]


def main():
    parser = argparse.ArgumentParser(description="Evaluate run directories with evaluation_protocol_v1.")
    parser.add_argument("run_dirs", nargs="+", help="Run directory paths such as baseline_direct_v1 or baseline_rag_v1.")
    parser.add_argument("--output", default="", help="Optional output JSON path.")
    args = parser.parse_args()

    protocol = load_json(PROTOCOL_PATH)
    method_rows = [evaluate_run(resolve_run_dir(run_dir), protocol) for run_dir in args.run_dirs]

    payload = {
        "protocol_version": protocol["version"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "methods": method_rows,
        "ranking": rank_methods(method_rows),
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
