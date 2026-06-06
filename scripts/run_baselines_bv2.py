#!/usr/bin/env python3
"""Direct Prompt and RAG baselines for benchmark_extended Type A."""
import argparse, json, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core.llm_client import LLMClient, strip_code_fences
from core.reference_rules import postprocess_script, build_compact_prompt
from core.script_generator import build_syntax_guardrails
from core.static_checker import analyze_script_text
from core.run_mission import run_mission

# Load Agent's generation prompt components once (proper ablation: same prompt, no pipeline)
_RULES = build_compact_prompt()
_GUARDRAILS = build_syntax_guardrails()


def direct_prompt(instruction: str, client: LLMClient) -> str:
    prompt = f"""Generate a valid AFSIM 2.9.0 scenario script for the following requirement:

{instruction}

{_RULES}

{_GUARDRAILS}

Return ONLY the complete AFSIM script as plain text. No markdown, no explanation."""
    resp = client.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=8192)
    return strip_code_fences(resp.content).strip()


# Optimal RAG: demo_sources (exclude self-oracle) + references + SKILL.md
_RAG_CORPUS = None


def _load_rag_corpus():
    """Load demo scripts (primary) + references (supplementary) as RAG corpus."""
    scripts = {}  # path -> text (demo scripts)
    refs = {}     # name -> text (reference docs)

    # Load demo scripts from both benchmark dirs for maximum coverage
    for bench_dir in ["benchmark", "benchmark_extended"]:
        demo_root = ROOT / "benchmarks" / bench_dir / "demo_sources"
        if demo_root.exists():
            for path in demo_root.rglob("*.txt"):
                rel = str(path.relative_to(demo_root))
                scripts[rel] = path.read_text(encoding="utf-8-sig")[:3000]

    # Load reference docs
    ref_dir = ROOT / "references"
    if ref_dir.exists():
        for path in sorted(ref_dir.glob("*.md")):
            refs[path.name] = path.read_text(encoding="utf-8-sig")[:3000]
    skill_path = ROOT / "SKILL.md"
    if skill_path.exists():
        refs["SKILL.md"] = skill_path.read_text(encoding="utf-8-sig")[:3000]

    return scripts, refs


def rag_prompt(instruction: str, source_demo: str, client: LLMClient) -> str:
    global _RAG_CORPUS
    if _RAG_CORPUS is None:
        _RAG_CORPUS = _load_rag_corpus()
    scripts, refs = _RAG_CORPUS

    keywords = set(instruction.lower().split())
    # Score demo scripts by keyword overlap, EXCLUDE self-oracle
    scored_scripts = []
    for path, content in scripts.items():
        norm_path = path.replace("\\", "/").lower()
        norm_oracle = source_demo.replace("\\", "/").lower()
        # Only skip if path matches exactly (same file from same demo directory)
        if norm_path == norm_oracle:
            continue  # exclude self-oracle
        content_lower = content.lower()
        score = sum(1 for kw in keywords if len(kw) > 3 and kw in content_lower)
        scored_scripts.append((score, path, content))
    scored_scripts.sort(reverse=True)

    # Score reference docs
    scored_refs = []
    for name, content in refs.items():
        content_lower = content.lower()
        score = sum(1 for kw in keywords if len(kw) > 3 and kw in content_lower)
        scored_refs.append((score, name, content))
    scored_refs.sort(reverse=True)

    # Build context: top 3 demo scripts + top 2 reference docs
    context_parts = []
    for _, path, content in scored_scripts[:3]:
        context_parts.append(f"--- demo: {path} ---\n{content[:2000]}")
    for _, name, content in scored_refs[:2]:
        context_parts.append(f"--- doc: {name} ---\n{content[:1500]}")
    rag_context = "\n\n".join(context_parts)

    prompt = f"""Generate a valid AFSIM 2.9.0 scenario script for the following requirement:

{instruction}

Reference examples and documentation:
```
{rag_context[:6000]}
```

{_RULES}

{_GUARDRAILS}

Return ONLY the complete AFSIM script as plain text. No markdown, no explanation."""
    resp = client.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=8192)
    return strip_code_fences(resp.content).strip()


def run_one(task: dict, client: LLMClient, mode: str, out_dir: Path) -> dict:
    tid = task["id"]
    instruction = task.get("instruction", task.get("input", ""))
    run_dir = out_dir / tid
    run_dir.mkdir(parents=True, exist_ok=True)
    script_path = run_dir / "generated_script.txt"

    try:
        if mode == "direct":
            raw = direct_prompt(instruction, client)
        else:
            raw = rag_prompt(instruction, task.get("source_demo", ""), client)

        script_text = postprocess_script(raw + "\n")
        script_path.write_text(script_text, encoding="utf-8")
        static = analyze_script_text(script_text, script_label=str(script_path))

        # Run mission.exe
        rc, stdout, stderr = run_mission(str(script_path), options=["-es", "-fio"])
        mission_pass = rc == 0 and "FATAL:" not in stdout and "FATAL:" not in stderr

        return {
            "id": tid,
            "mode": mode,
            "syntax_correct": static["syntax_correct"],
            "static_pass": static["static_pass"],
            "static_errors": static["static_error_ids"],
            "mission_status": "PASS" if mission_pass else "FAIL",
            "return_code": rc,
            "generated_script": str(script_path.relative_to(ROOT)),
        }
    except Exception as e:
        script_path.write_text("", encoding="utf-8")
        return {
            "id": tid, "mode": mode,
            "syntax_correct": False, "static_pass": False,
            "static_errors": ["RUN_ERROR"],
            "mission_status": "FAIL", "return_code": 1,
            "generated_script": str(script_path.relative_to(ROOT)),
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["direct", "rag"], required=True)
    parser.add_argument("--benchmark", default="benchmarks/benchmark_extended/type_a_instruction_to_script.jsonl")
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--max-workers", type=int, default=27)
    args = parser.parse_args()

    jsonl_path = ROOT / args.benchmark
    tasks = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    print(f"Loaded {len(tasks)} tasks from {jsonl_path}")

    client = LLMClient.from_env(model=args.model)
    out_dir = ROOT / f"baseline_{args.mode}_bv2"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {pool.submit(run_one, t, client, args.mode, out_dir): t["id"] for t in tasks}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            status = r["mission_status"]
            print(f"  {r['id']}: {status} (syntax={r['syntax_correct']} static={r['static_pass']})")

    results.sort(key=lambda x: x["id"])

    total = len(results)
    mission_pass = sum(1 for r in results if r["mission_status"] == "PASS")
    syntax_ok = sum(1 for r in results if r["syntax_correct"])
    static_ok = sum(1 for r in results if r["static_pass"])

    summary = {
        "mode": args.mode, "model": args.model, "total": total,
        "mission_success_rate": round(mission_pass / total, 4),
        "syntax_correct_rate": round(syntax_ok / total, 4),
        "static_pass_rate": round(static_ok / total, 4),
        "mission_pass": mission_pass, "results": results,
    }

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== {args.mode.upper()} ===")
    print(f"Total: {total} | Mission PASS: {mission_pass}/{total} ({summary['mission_success_rate']:.1%})")
    print(f"Syntax: {syntax_ok}/{total} ({summary['syntax_correct_rate']:.1%}) | Static: {static_ok}/{total} ({summary['static_pass_rate']:.1%})")
    print(f"Results saved to {summary_path}")


if __name__ == "__main__":
    main()
