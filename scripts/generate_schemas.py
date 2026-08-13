#!/usr/bin/env python3
"""导出 JSON Schema（schemas/*.schema.json）。

导出 docking_input / docking_output / comparison_output / error 四个 schema，
与 backend/app/schemas.py 的 Pydantic 模型保持同步。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.schemas import (  # noqa: E402
    ComparisonOutput,
    DockingInput,
    DockingOutput,
    StructuredError,
)

SCHEMAS_DIR = PROJECT_ROOT / "schemas"

EXPORTS = {
    "docking_input.schema.json": DockingInput,
    "docking_output.schema.json": DockingOutput,
    "comparison_output.schema.json": ComparisonOutput,
    "error.schema.json": StructuredError,
}


def main() -> int:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, model in EXPORTS.items():
        out = SCHEMAS_DIR / filename
        out.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
