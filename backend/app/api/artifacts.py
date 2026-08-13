"""job 状态与产物 API：

- GET    /api/jobs/{job_id}           → job.json（状态唯一事实来源）
- GET    /api/jobs/{job_id}/result    → reports/result.json
- GET    /api/jobs/{job_id}/artifacts → manifest artifacts 清单
- GET    /api/jobs/{job_id}/files/{relative_path:path} → 受控文件读取
- DELETE /api/jobs/{job_id}           → 清理产物目录

文件读取安全：safe_resolve 防路径穿越（非法 → 403）；白名单扩展名；
zip 直接 FileResponse 下载；不存在 → 404。
"""

from __future__ import annotations

import json
import shutil

from fastapi import APIRouter, Path as PathParam
from fastapi.responses import FileResponse, PlainTextResponse

from app.api.deps import (
    ALLOWED_FILE_EXTENSIONS,
    ApiError,
    JobNotFoundError,
    resolve_job_dir_or_404,
)
from app.schemas import ErrorCode, StructuredError
from app.utils.files import PathTraversalError, safe_resolve

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_TEXT_MEDIA_TYPES = {
    "pdb": "text/plain",
    "sdf": "text/plain",
    "pdbqt": "text/plain",
    "svg": "image/svg+xml",
    "json": "application/json",
    "csv": "text/csv",
    "md": "text/markdown",
    "txt": "text/plain",
    "log": "text/plain",
}

_JOB_EXAMPLE = {
    "description": "job.json 内容",
    "content": {
        "application/json": {
            "example": {
                "job_id": "20260805-120000_ethanol_demo",
                "job_name": "ethanol_demo",
                "state": "SUCCESS",
                "step": "package_artifacts",
                "progress": 100,
                "started_at": "2026-08-05T12:00:00+00:00",
                "finished_at": "2026-08-05T12:00:42+00:00",
                "message": "success: 1/1 ligand(s) docked",
                "artifacts": {"receptor_pdbqt": "receptor/receptor.pdbqt"},
                "structured_error": None,
            }
        }
    },
}

_NOT_FOUND_EXAMPLE = {
    "description": "job 不存在",
    "content": {
        "application/json": {
            "example": {
                "error_code": "FILE_NOT_FOUND",
                "stage": "api",
                "message": "job not found: no_such_job",
                "details": {"job_id": "no_such_job"},
                "recoverable": True,
                "suggested_actions": ["check job_id via GET /api/jobs/{job_id}"],
            }
        }
    },
}


@router.get(
    "/{job_id}",
    summary="查询 job 状态（job.json）",
    responses={200: _JOB_EXAMPLE, 404: _NOT_FOUND_EXAMPLE},
)
def get_job(job_id: str) -> dict:
    """返回 outputs/<job_id>/job.json 的实时内容。"""
    job_dir = resolve_job_dir_or_404(job_id)
    job_json = job_dir / "job.json"
    if not job_json.is_file():
        raise JobNotFoundError(job_id)
    return json.loads(job_json.read_text(encoding="utf-8"))


@router.get(
    "/{job_id}/result",
    summary="获取对接结果（reports/result.json）",
    responses={
        200: {
            "description": "DockingOutput",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "20260805-120000_ethanol_demo",
                        "job_name": "ethanol_demo",
                        "status": "SUCCESS",
                        "state": "SUCCESS",
                        "results": [
                            {
                                "ligand_id": "ethanol",
                                "status": "SUCCESS",
                                "best_affinity_kcal_mol": -3.9,
                                "poses": [
                                    {
                                        "rank": 1,
                                        "affinity_kcal_mol": -3.9,
                                        "rmsd_lb": 0.0,
                                        "rmsd_ub": 0.0,
                                        "pose_file": "poses/ethanol/pose_001.pdbqt",
                                        "pose_pdb_file": "poses/ethanol/pose_001.pdb",
                                    }
                                ],
                            }
                        ],
                        "warnings": [],
                        "structured_error": None,
                    }
                }
            },
        },
        404: _NOT_FOUND_EXAMPLE,
    },
)
def get_result(job_id: str) -> dict:
    """返回 reports/result.json（SUCCESS 与 FAILED 的 job 均存在）。"""
    job_dir = resolve_job_dir_or_404(job_id)
    result_path = job_dir / "reports" / "result.json"
    if not result_path.is_file():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="api",
                message="result.json not available yet (job not finished?)",
                details={"job_id": job_id},
                recoverable=True,
                suggested_actions=["poll GET /api/jobs/{job_id} until terminal state"],
            ),
            status_code=404,
        )
    return json.loads(result_path.read_text(encoding="utf-8"))


@router.get(
    "/{job_id}/artifacts",
    summary="产物清单（manifest.json）",
    responses={
        200: {
            "description": "manifest 内容（含 artifact_sha256 相对路径 → sha256）",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "20260805-120000_ethanol_demo",
                        "status": "SUCCESS",
                        "artifacts": {
                            "input.json": "sha256:...",
                            "reports/result.json": "sha256:...",
                        },
                        "bundle_zip": "bundle.zip",
                    }
                }
            },
        },
        404: _NOT_FOUND_EXAMPLE,
    },
)
def get_artifacts(job_id: str) -> dict:
    """返回产物清单：优先 manifest.json 的 artifact_sha256；
    未生成 manifest 的任务（如 ligand_prepare）回退到 job.json 的 artifacts。"""
    job_dir = resolve_job_dir_or_404(job_id)
    bundle_zip = "bundle.zip" if (job_dir / "bundle.zip").is_file() else None
    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "job_id": job_id,
            "status": manifest.get("status"),
            "artifacts": manifest.get("artifact_sha256", {}),
            "bundle_zip": bundle_zip,
        }
    job_json = job_dir / "job.json"
    if job_json.is_file():
        record = json.loads(job_json.read_text(encoding="utf-8"))
        return {
            "job_id": job_id,
            "status": record.get("state"),
            "artifacts": record.get("artifacts", {}),
            "bundle_zip": bundle_zip,
        }
    raise ApiError(
        StructuredError(
            error_code=ErrorCode.FILE_NOT_FOUND,
            stage="api",
            message="artifacts not available yet (job not finished?)",
            details={"job_id": job_id},
            recoverable=True,
            suggested_actions=["poll GET /api/jobs/{job_id} until terminal state"],
        ),
        status_code=404,
    )


@router.get(
    "/{job_id}/files/{relative_path:path}",
    summary="受控读取 job 产物文件（白名单扩展名，防路径穿越）",
    responses={
        200: {"description": "文件内容（zip 为二进制下载，其余为文本/JSON/SVG）"},
        403: {
            "description": "路径穿越或扩展名不在白名单",
            "content": {
                "application/json": {
                    "example": {
                        "error_code": "INPUT_VALIDATION_FAILED",
                        "stage": "api",
                        "message": "path '../secret' resolves outside allowed base",
                        "details": {},
                        "recoverable": False,
                        "suggested_actions": [],
                    }
                }
            },
        },
        404: _NOT_FOUND_EXAMPLE,
    },
)
def get_file(job_id: str, relative_path: str = PathParam(..., examples=["reports/result.json"])):
    """按 job 目录相对路径读取产物；仅允许白名单扩展名。"""
    job_dir = resolve_job_dir_or_404(job_id)
    if not relative_path or not relative_path.strip():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="api",
                message="empty file path",
            ),
            status_code=404,
        )
    extension = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="api",
                message=(
                    f"file extension '.{extension}' not allowed; allowed: "
                    f"{sorted(ALLOWED_FILE_EXTENSIONS)}"
                ),
                details={"path": relative_path},
            ),
            status_code=403,
        )
    try:
        target = safe_resolve(relative_path, job_dir)
    except PathTraversalError as exc:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="api",
                message=str(exc),
                details={"path": relative_path},
                suggested_actions=["use a path inside the job directory"],
            ),
            status_code=403,
        ) from exc
    if not target.is_file():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="api",
                message=f"file not found: {relative_path}",
                details={"job_id": job_id, "path": relative_path},
            ),
            status_code=404,
        )
    if extension == "zip":
        return FileResponse(
            target, media_type="application/zip", filename=target.name
        )
    return PlainTextResponse(
        target.read_text(encoding="utf-8", errors="replace"),
        media_type=_TEXT_MEDIA_TYPES[extension],
    )


@router.delete(
    "/{job_id}",
    summary="删除 job 产物目录",
    responses={
        200: {
            "description": "已删除",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "20260805-120000_ethanol_demo",
                        "deleted": True,
                    }
                }
            },
        },
        404: _NOT_FOUND_EXAMPLE,
    },
)
def delete_job(job_id: str) -> dict:
    """递归删除 outputs/<job_id>/（不可恢复）。"""
    job_dir = resolve_job_dir_or_404(job_id)
    shutil.rmtree(job_dir)
    return {"job_id": job_id, "deleted": True}
