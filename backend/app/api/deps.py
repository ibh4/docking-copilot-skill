"""API 层公共依赖：统一结构化错误响应、job 目录解析、快速校验辅助。

所有 4xx/5xx 响应体都遵循 schemas/error.schema.json 的 StructuredError 形状：
error_code / stage / message / details / recoverable / suggested_actions。
"""

from __future__ import annotations

import re

from fastapi.responses import JSONResponse

from app.schemas import ErrorCode, StructuredError
from app.utils.files import PathTraversalError

#: job_id 由 make_job_id 生成（时间戳_净化名，可能带冲突序号）
JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: 受控文件读取白名单扩展名
ALLOWED_FILE_EXTENSIONS = {
    "pdb", "sdf", "pdbqt", "svg", "json", "csv", "md", "txt", "log", "zip",
}


class ApiError(Exception):
    """携带 HTTP 状态码与结构化错误的 API 级异常（由全局处理器转响应）。"""

    status_code: int = 400

    def __init__(
        self,
        error: StructuredError,
        status_code: int | None = None,
    ) -> None:
        super().__init__(error.message)
        self.error = error
        if status_code is not None:
            self.status_code = status_code


class JobNotFoundError(ApiError):
    """job 不存在（404）。"""

    status_code = 404

    def __init__(self, job_id: str) -> None:
        super().__init__(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="api",
                message=f"job not found: {job_id}",
                details={"job_id": job_id},
                recoverable=True,
                suggested_actions=["check job_id via GET /api/jobs/{job_id}"],
            )
        )


class JobForbiddenError(ApiError):
    """非法 job_id 或路径穿越（403）。"""

    status_code = 403

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="api",
                message=message,
                details=details or {},
            )
        )


class UploadTooLargeError(ApiError):
    """上传超过大小上限（413）。"""

    status_code = 413

    def __init__(self, error: StructuredError) -> None:
        super().__init__(error, status_code=413)


def structured_error_response(error: StructuredError, status_code: int) -> JSONResponse:
    """把 StructuredError 序列化为统一形状的 JSON 响应。"""
    return JSONResponse(
        status_code=status_code, content=error.model_dump(mode="json")
    )


def resolve_job_dir_or_404(job_id: str):
    """解析 job 目录；格式非法/路径穿越 → 403，目录不存在 → 404。"""
    from app.api import queue

    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise JobForbiddenError(
            "invalid job_id format", details={"job_id": job_id}
        )
    try:
        job_dir = queue.resolve_job_dir(job_id)
    except PathTraversalError as exc:
        raise JobForbiddenError(str(exc), details={"job_id": job_id}) from exc
    if not job_dir.is_dir():
        raise JobNotFoundError(job_id)
    return job_dir


def validate_ligand_smiles(smiles: str, ligand_id: str) -> None:
    """提交前快速校验 SMILES；失败抛 ApiError（400，INVALID_SMILES 等）。"""
    from app.services import ligand_service

    try:
        ligand_service.validate_smiles(smiles)
    except ligand_service.LigandError as exc:
        raise ApiError(
            StructuredError(
                error_code=exc.code,
                stage="validate_input",
                message=str(exc),
                details={**(exc.details or {}), "ligand_id": ligand_id},
                recoverable=exc.recoverable,
                suggested_actions=exc.suggested_actions
                or ["check SMILES syntax"],
            ),
            status_code=400,
        ) from exc
