#!/usr/bin/env python3
"""
Task-009: Refresh Baseline Evaluation Artifacts

This script keeps the original generated scripts and mission logs, but rewrites
derived evaluation files so they reflect the current evaluation protocol:
  - results.jsonl
  - summary.json
  - error_stats.json
  - README.md
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from run_direct_baseline import mission_error_to_taxonomy
from static_checker_v1 import check_script


ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def dump_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows):
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def resolve_run_dir(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def refresh_row(row: dict, run_dir: Path):
    script_rel = row["generated_script"]
    script_path = (ROOT / script_rel).resolve()
    static_result = check_script(script_path)

    refreshed = dict(row)
    refreshed["static_errors"] = static_result["findings"]
    refreshed["static_error_ids"] = static_result["static_error_ids"]
    refreshed["syntax_correct"] = static_result["syntax_correct"]
    refreshed["static_pass"] = static_result["static_pass"]

    mission_taxonomy = ""
    mission_log_rel = row.get("mission_log", "")
    if mission_log_rel:
        mission_log_path = (ROOT / mission_log_rel).resolve()
        if mission_log_path.exists():
            log_text = mission_log_path.read_text(encoding="utf-8-sig", errors="replace")
            mission_taxonomy = mission_error_to_taxonomy(log_text)

    primary_error = static_result["primary_error"]
    secondary_errors = sorted({
        item["error_id"] for item in static_result["findings"] if item["error_id"] != primary_error
    })

    if not primary_error and mission_taxonomy:
        primary_error = mission_taxonomy
    elif mission_taxonomy and mission_taxonomy not in {primary_error, *secondary_errors}:
        secondary_errors.append(mission_taxonomy)

    refreshed["primary_error"] = primary_error
    refreshed["secondary_errors"] = secondary_errors
    return refreshed


def build_summary(summary_seed: dict, rows: list[dict], run_dir: Path):
    total = len(rows)
    syntax_correct = sum(1 for row in rows if row.get("syntax_correct"))
    static_pass = sum(1 for row in rows if row.get("static_pass"))
    mission_counter = Counter(row.get("mission_status", "") for row in rows)
    semantic_match = sum(1 for row in rows if row.get("semantic_match"))

    error_counter = Counter()
    for row in rows:
        error_ids = [row.get("primary_error", "")] + row.get("secondary_errors", [])
        for error_id in error_ids:
            if error_id:
                error_counter[error_id] += 1

    mission_pass = mission_counter["PASS"]
    failed = total - mission_pass

    summary = {
        "name": summary_seed.get("name", run_dir.name),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "generator": summary_seed.get("generator"),
        "model": summary_seed.get("model"),
        "benchmark_dir": summary_seed.get("benchmark_dir"),
        "total": total,
        "syntax_correct_rate": round(syntax_correct / total, 4) if total else 0.0,
        "static_pass_rate": round(static_pass / total, 4) if total else 0.0,
        "mission_success_rate": round(mission_pass / total, 4) if total else 0.0,
        "error_rate": round(failed / total, 4) if total else 0.0,
        "semantic_match_rate": round(semantic_match / total, 4) if total else 0.0,
        "counts": {
            "syntax_correct": syntax_correct,
            "static_pass": static_pass,
            "mission_pass": mission_pass,
            "mission_fail": mission_counter["FAIL"],
            "mission_timeout": mission_counter["TIMEOUT"],
            "semantic_match": semantic_match,
        },
        "error_stats": dict(sorted(error_counter.items())),
        "results": rows,
        "evaluation_refresh": {
            "protocol": "evaluation_protocol_v1",
            "static_metrics_source": "current static_checker_v1",
        },
    }

    retrieval = summary_seed.get("retrieval")
    if retrieval:
        summary["retrieval"] = retrieval

    return summary


def build_readme(summary: dict):
    total = summary["total"]
    counts = summary["counts"]
    lines = [
        f"# {summary['name']}",
        "",
        "## 设置",
        "",
        f"- benchmark: `{summary.get('benchmark_dir')}`",
        f"- total: {total}",
        f"- generator: `{summary.get('generator')}`",
        f"- model: `{summary.get('model')}`",
        "- evaluation_protocol: `evaluation_protocol_v1`",
        "- static_metrics_source: current `static_checker_v1`",
        "",
        "## 指标",
        "",
        f"- Script Correctness: {counts['syntax_correct']}/{total} = {summary['syntax_correct_rate']:.2%}",
        f"- Static Pass Rate: {counts['static_pass']}/{total} = {summary['static_pass_rate']:.2%}",
        f"- mission.exe Success Rate: {counts['mission_pass']}/{total} = {summary['mission_success_rate']:.2%}",
        f"- Semantic Match Rate: {counts['semantic_match']}/{total} = {summary['semantic_match_rate']:.2%}",
        "",
        "## 主要错误分布",
        "",
    ]

    for key, value in sorted(summary["error_stats"].items()):
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "## 说明",
        "",
        "- 本目录保留原始生成脚本与 mission 日志。",
        "- 旧的静态评估结果已被当前 `static_checker_v1` 重算并覆盖。",
        "- `mission_status` 和 `semantic_match` 继续沿用原始运行记录。",
    ])

    if "retrieval" in summary:
        retrieval = summary["retrieval"]
        lines.extend([
            "",
            "## 检索设置",
            "",
            f"- exclude_oracle: `{retrieval.get('exclude_oracle')}`",
            f"- corpus_chunks: {retrieval.get('corpus_chunks')}",
            f"- max_context_chars: {retrieval.get('max_context_chars')}",
            f"- retrieval_strategy: {retrieval.get('strategy')}",
        ])

    return "\n".join(lines) + "\n"


def refresh_run(run_dir: Path):
    summary_path = run_dir / "summary.json"
    results_path = run_dir / "results.jsonl"
    error_stats_path = run_dir / "error_stats.json"
    readme_path = run_dir / "README.md"

    summary_seed = load_json(summary_path)
    rows = load_jsonl(results_path)
    refreshed_rows = [refresh_row(row, run_dir) for row in rows]
    summary = build_summary(summary_seed, refreshed_rows, run_dir)

    dump_json(summary_path, summary)
    dump_jsonl(results_path, refreshed_rows)
    dump_json(error_stats_path, {"error_stats": summary["error_stats"]})
    readme_path.write_text(build_readme(summary), encoding="utf-8")

    return {
        "run_dir": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
        "syntax_correct_rate": summary["syntax_correct_rate"],
        "static_pass_rate": summary["static_pass_rate"],
        "mission_success_rate": summary["mission_success_rate"],
        "semantic_match_rate": summary["semantic_match_rate"],
    }


def main():
    parser = argparse.ArgumentParser(description="Refresh baseline evaluation artifacts with current static checker.")
    parser.add_argument("run_dirs", nargs="+", help="Run directory paths such as baseline_direct_v1 baseline_rag_v1.")
    args = parser.parse_args()

    refreshed = [refresh_run(resolve_run_dir(run_dir)) for run_dir in args.run_dirs]
    print(json.dumps({"refreshed": refreshed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
