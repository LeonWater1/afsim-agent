#!/usr/bin/env python3
"""
Task-016: LLM-backed natural-language to AFSIM-IR parser.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ir_schema_validator_v1 import validate_ir
from llm_client_v1 import LLMClient, extract_json_object


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "docs" / "machine" / "afsim_ir_schema_v1.json"
IR_EXAMPLES_PATH = ROOT / "docs" / "machine" / "ir_examples_v1.jsonl"
BENCHMARK_PATH = ROOT / "benchmarks" / "benchmark_v1" / "tasks.jsonl"


def load_schema_text() -> str:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))
    return json.dumps(schema, ensure_ascii=False, indent=2)


def load_benchmark_index() -> dict[str, dict[str, Any]]:
    rows = {}
    for line in BENCHMARK_PATH.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["id"]] = row
    return rows


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    ascii_tokens = set(re.findall(r"[a-z0-9_]+", lowered))
    chinese_tokens = set(re.findall(r"[\u4e00-\u9fff]{1,4}", text))
    return {token for token in ascii_tokens | chinese_tokens if token}


def load_few_shot_examples(task_input: str, limit: int = 3) -> list[dict[str, Any]]:
    benchmark_inputs = {task_id: row["input"] for task_id, row in load_benchmark_index().items()}

    request_tokens = tokenize(task_input)
    scored_examples = []
    for line in IR_EXAMPLES_PATH.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        source_task_id = row.get("source_task_id", "")
        source_input = benchmark_inputs.get(source_task_id, "")
        source_tokens = tokenize(source_input)
        overlap = len(request_tokens & source_tokens)
        examples_payload = json.dumps(row.get("ir", {}), ensure_ascii=False)
        payload_tokens = tokenize(examples_payload)
        payload_overlap = len(request_tokens & payload_tokens)
        score = overlap * 10 + payload_overlap
        example = {
            "source_task_id": source_task_id,
            "task_input": source_input,
            "ir": row.get("ir", {}),
        }
        scored_examples.append((score, source_task_id, example))

    scored_examples.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored_examples[:limit]]


def build_messages(
    task_id: str,
    user_input: str,
    schema_text: str,
    few_shot_examples: list[dict[str, Any]],
    benchmark_meta: dict[str, Any],
    feedback: list[str] | None = None,
) -> list[dict[str, str]]:
    system_prompt = """You are the Intent Parsing module of an AFSIM scenario generation agent.

Convert the user's natural-language request into one JSON object that conforms to afsim_ir_schema_v1.

Rules:
- Return JSON only. No markdown, no explanation.
- The top-level object must be the IR object itself.
- Use schema_version = "afsim_ir_v1".
- Represent uncertain platform or component types with platform_type_hint or type_hint.
- Do not invent unsupported WSF_* identifiers.
- Include scenario, sides, entities, and tasks.
- scenario.domains and entity.domain must use only: air, ground, surface, subsurface, space, cyber, mixed.
- scenario.outputs must use only renderable output blocks: event_pipe, event_output, csv_event_output.
- Do not use abstract output labels such as mission_log, log, report, or output_file in scenario.outputs.
- If the user omits exact values, choose conservative defaults that keep the scenario executable and easy to ground later.
- Use stable English ids like blue_fighter_1, escort_route, detect_target.
- Keep Chinese source meaning in scenario.description when helpful.
- Follow the structure style shown in the few-shot examples when the request resembles them.
- If benchmark metadata provides a source_hint, stay aligned with that source family and domain rather than over-interpreting one keyword in isolation.
"""
    examples_payload = json.dumps(few_shot_examples, ensure_ascii=False, indent=2)
    benchmark_payload = json.dumps(
        {
            "source_hint": benchmark_meta.get("source_hint", ""),
            "covered_components": benchmark_meta.get("covered_components", []),
            "expected_ir_focus": benchmark_meta.get("expected_ir_focus", []),
            "evaluation_focus": benchmark_meta.get("evaluation_focus", []),
            "demo_id": benchmark_meta.get("demo_id", ""),
        },
        ensure_ascii=False,
        indent=2,
    )
    user_prompt = f"""Task ID: {task_id}
Natural-language request:
{user_input}

Benchmark metadata:
{benchmark_payload}

Target schema:
{schema_text}

Few-shot reference examples:
{examples_payload}
"""
    if feedback:
        user_prompt += "\nPrevious attempt issues:\n- " + "\n- ".join(feedback) + "\nRepair the JSON and return only the corrected JSON object.\n"
    else:
        user_prompt += "\nReturn the AFSIM-IR JSON object now.\n"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_intent_with_llm(
    task_id: str,
    user_input: str,
    client: LLMClient,
    max_attempts: int = 2,
) -> dict[str, Any]:
    schema_text = load_schema_text()
    few_shot_examples = load_few_shot_examples(user_input)
    benchmark_meta = load_benchmark_index().get(task_id, {})
    feedback: list[str] = []
    attempts: list[dict[str, Any]] = []

    for attempt_index in range(1, max_attempts + 1):
        response = client.chat(
            build_messages(
                task_id,
                user_input,
                schema_text,
                few_shot_examples,
                benchmark_meta,
                feedback if feedback else None,
            ),
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        attempt_record: dict[str, Any] = {
            "attempt": attempt_index,
            "model": response.model,
            "raw_content_preview": response.content[:1200],
        }

        try:
            ir = extract_json_object(response.content)
            validation = validate_ir(ir)
            attempt_record["validation"] = validation
            attempts.append(attempt_record)
            if validation["ok"]:
                return {
                    "version": "llm_intent_parser_v1",
                    "task_id": task_id,
                    "parser_mode": "llm_schema_retry",
                    "supported": True,
                    "input": user_input,
                    "few_shot_example_count": len(few_shot_examples),
                    "attempt_count": attempt_index,
                    "attempts": attempts,
                    "ir": ir,
                }
            feedback = [f"{item['path']}: {item['message']}" for item in validation["errors"][:8]]
        except Exception as exc:
            attempt_record["validation"] = {"ok": False, "error_count": 1, "errors": [{"path": "$", "message": str(exc)}]}
            attempts.append(attempt_record)
            feedback = [str(exc)]

    raise RuntimeError(f"LLM intent parsing failed for {task_id} after {max_attempts} attempts")


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse natural language into AFSIM-IR with an LLM.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--input-text", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args()

    client = LLMClient.from_env(model=args.model)
    result = parse_intent_with_llm(args.task_id, args.input_text, client, max_attempts=args.max_attempts)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
