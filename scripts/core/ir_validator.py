#!/usr/bin/env python3
"""
Task-016 / Task-018: AFSIM-IR schema validation helper.

Supports both afsim_ir_v1 and afsim_ir_v2.  Auto-detects the schema version
from the ``schema_version`` field and loads the matching schema file.
"""
from __future__ import annotations

import argparse
import functools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_V1_PATH = ROOT / "docs" / "machine" / "afsim_ir_schema.json"
SCHEMA_V2_PATH = ROOT / "docs" / "machine" / "afsim_ir_schema_extended.json"

_VERSION_MAP: dict[str, Path] = {
    "afsim_ir_v1": SCHEMA_V1_PATH,
    "afsim_ir_v2": SCHEMA_V2_PATH,
}


@functools.lru_cache(maxsize=2)
def load_schema(version: str = "afsim_ir_v1") -> dict[str, Any]:
    path = _VERSION_MAP.get(version)
    if path is None:
        raise ValueError(
            f"Unknown schema version: {version}. Known: {list(_VERSION_MAP)}"
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _detect_version(ir: dict[str, Any]) -> str:
    version = ir.get("schema_version", "")
    if version in _VERSION_MAP:
        return version
    return "afsim_ir_v1"


def _format_path(error) -> str:
    if not error.absolute_path:
        return "$"
    return "$." + ".".join(str(item) for item in error.absolute_path)


def validate_ir(ir: dict[str, Any]) -> dict[str, Any]:
    version = _detect_version(ir)
    schema = load_schema(version)
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(ir), key=lambda item: list(item.absolute_path)
    )
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
        "schema_version": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate AFSIM-IR JSON against afsim_ir_schema (auto-detect v1/v2)."
    )
    parser.add_argument(
        "ir_json", help="Path to JSON file containing raw IR or wrapper object with `ir`."
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.ir_json).read_text(encoding="utf-8-sig"))
    ir = (
        payload["ir"]
        if isinstance(payload, dict) and isinstance(payload.get("ir"), dict)
        else payload
    )
    print(json.dumps(validate_ir(ir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
