"""JSON Schema 服务端点：直接返回仓库 schemas/*.schema.json 内容。"""

from __future__ import annotations

import json

from fastapi import APIRouter

from app import config
from app.api.deps import ApiError
from app.schemas import ErrorCode, StructuredError

router = APIRouter(prefix="/api/schema", tags=["schema"])


def _load_schema(filename: str) -> dict:
    path = config.PROJECT_ROOT / "schemas" / filename
    if not path.is_file():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="schema",
                message=f"schema file not found: {filename}",
                suggested_actions=["run 'make schemas' to regenerate"],
            ),
            status_code=404,
        )
    return json.loads(path.read_text(encoding="utf-8"))


_SCHEMA_200 = {
    "description": "JSON Schema 原文（draft 兼容 pydantic 导出）",
    "content": {
        "application/json": {
            "example": {
                "title": "DockingInput",
                "type": "object",
                "required": ["job_name", "ligands", "receptor"],
                "properties": {"job_name": {"type": "string"}},
            }
        }
    },
}
_ERROR_404 = {
    "description": "schema 文件缺失",
    "content": {
        "application/json": {
            "example": {
                "error_code": "FILE_NOT_FOUND",
                "stage": "schema",
                "message": "schema file not found: docking_input.schema.json",
                "details": {},
                "recoverable": False,
                "suggested_actions": ["run 'make schemas' to regenerate"],
            }
        }
    },
}


@router.get(
    "/input",
    summary="对接输入 JSON Schema（DockingInput）",
    responses={200: _SCHEMA_200, 404: _ERROR_404},
)
def input_schema() -> dict:
    """返回 schemas/docking_input.schema.json 原文。"""
    return _load_schema("docking_input.schema.json")


@router.get(
    "/output",
    summary="对接输出 JSON Schema（DockingOutput）",
    responses={200: _SCHEMA_200, 404: _ERROR_404},
)
def output_schema() -> dict:
    """返回 schemas/docking_output.schema.json 原文。"""
    return _load_schema("docking_output.schema.json")
