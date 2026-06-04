#!/usr/bin/env python3
"""
Task-016: AFSIM-IR schema validation helper.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "docs" / "machine" / "afsim_ir_schema_v1.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8-sig"))


def _format_path(error) -> str:
    if not error.absolute_path:
        return "$"
    return "$." + ".".join(str(item) for item in error.absolute_path)


def validate_ir(ir: dict[str, Any]) -> dict[str, Any]:
    schema = load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ir), key=lambda item: list(item.absolute_path))
    formatted = [
        {
            "path": _format_path(error),
            "message": error.message,
        }
        for error in errors
    ]
    return {
        "ok": not formatted,
        "error_count": len(formatted),
        "errors": formatted,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate AFSIM-IR JSON against afsim_ir_schema_v1.")
    parser.add_argument("ir_json", help="Path to JSON file containing raw IR or wrapper object with `ir`.")
    args = parser.parse_args()

    payload = json.loads(Path(args.ir_json).read_text(encoding="utf-8-sig"))
    ir = payload["ir"] if isinstance(payload, dict) and isinstance(payload.get("ir"), dict) else payload
    print(json.dumps(validate_ir(ir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
