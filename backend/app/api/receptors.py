"""受体 API：同步结构分析 + 受体准备入队。

POST /api/receptors/analyze 支持两种请求形态：
- multipart/form-data：上传 PDB 文件（字段名 ``file``，限 20MB）；
- application/json：``{"source": "<项目内相对路径>"}`` 引用仓库内文件，
  例如 ``examples/data/sample_receptor.pdb``。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from pydantic import BaseModel, Field

from app import config
from app.api import queue
from app.api.deps import ApiError, UploadTooLargeError
from app.schemas import ErrorCode, ReceptorConfig, StructuredError
from app.services import receptor_service
from app.utils.files import PathTraversalError, safe_resolve, sanitize_filename
from app.utils.security import SecurityError

router = APIRouter(prefix="/api/receptors", tags=["receptors"])


class ReceptorSourceInput(BaseModel):
    """JSON 引用形态的受体输入。"""

    source: str = Field(
        ..., min_length=1, description="项目内相对路径，如 examples/data/sample_receptor.pdb"
    )
    config: ReceptorConfig = Field(default_factory=ReceptorConfig)


class ReceptorPrepareRequest(BaseModel):
    """受体准备请求体（入队执行清洗 + PDBQT）。"""

    source: str = Field(..., min_length=1)
    config: ReceptorConfig = Field(default_factory=ReceptorConfig)


_ANALYZE_EXAMPLE = {
    "description": "结构摘要",
    "content": {
        "application/json": {
            "example": {
                "chains": ["A"],
                "residue_count": 214,
                "atom_count": 1731,
                "hetero": [
                    {
                        "chain": "A",
                        "resname": "ZN",
                        "resid": 400,
                        "type": "metal",
                        "atom_count": 1,
                    }
                ],
                "waters": [],
                "metals": [],
                "cofactors": [],
                "detected_ligands": [],
                "bounding_box": {
                    "min": [2.2, -6.1, 5.3],
                    "max": [38.9, 12.4, 41.0],
                },
                "warnings": ["possible missing residues (sequence-number gaps)"],
            }
        }
    },
}

_CREATED_EXAMPLE = {
    "description": "已入队；后台串行执行，用 GET /api/jobs/{job_id} 轮询",
    "content": {
        "application/json": {
            "example": {
                "job_id": "20260805-120000_receptor_prepare",
                "state": "CREATED",
            }
        }
    },
}


def _analyze_path(pdb_path: Path) -> dict:
    """分析 PDB 文件并返回可 JSON 序列化的结构摘要。"""
    try:
        report = receptor_service.analyze_receptor(pdb_path)
        bb_min, bb_max = receptor_service.bounding_box_from_report(report)
    except receptor_service.ReceptorError as exc:
        raise ApiError(
            StructuredError(
                error_code=exc.code,
                stage="analyze_receptor",
                message=str(exc),
                details=exc.details,
                recoverable=exc.recoverable,
                suggested_actions=exc.suggested_actions
                or ["provide a valid PDB file"],
            ),
            status_code=400,
        ) from exc

    warnings: list[str] = []
    if report["num_models"] > 1:
        warnings.append(
            f"structure has {report['num_models']} models; only model 1 analyzed"
        )
    if report["has_altloc"]:
        warnings.append("alternate location atoms detected")
    if report["ca_only_backbone"]:
        warnings.append("structure appears to be C-alpha-only (backbone trace)")
    if report["has_nucleic_acid"]:
        warnings.append("nucleic acid residues detected")
    for gap in report["missing_residue_gaps"][:10]:
        warnings.append(f"possible missing residues: {gap}")

    return {
        "chains": report["chains"],
        "residue_count": report["residue_count"],
        "atom_count": report["atom_count"],
        "hetero": report["hetero_entities"],
        "waters": report["waters"],
        "metals": report["metals"],
        "cofactors": report["cofactors"],
        "detected_ligands": report["detected_ligands"],
        "bounding_box": {"min": bb_min, "max": bb_max},
        "warnings": warnings,
    }


@router.post(
    "/analyze",
    summary="同步分析受体结构（multipart 上传或 JSON 引用）",
    responses={200: _ANALYZE_EXAMPLE},
)
async def analyze_receptor(
    request: Request,
    file: UploadFile | None = File(default=None),
    source: str | None = Form(default=None),
) -> dict:
    """同步返回结构摘要：chains/residue_count/atom_count/hetero/waters/
    metals/cofactors/bounding_box/warnings。上传大小上限 20MB。"""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload = ReceptorSourceInput.model_validate(await request.json())
        except Exception as exc:  # noqa: BLE001 —— pydantic/json 错误统一 400
            return _bad_json(exc)
        try:
            pdb_path = safe_resolve(payload.source, config.PROJECT_ROOT)
        except PathTraversalError as exc:
            raise ApiError(
                StructuredError(
                    error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                    stage="analyze_receptor",
                    message=str(exc),
                    suggested_actions=["keep receptor source inside the project"],
                ),
                status_code=400,
            ) from exc
        if not pdb_path.is_file():
            raise ApiError(
                StructuredError(
                    error_code=ErrorCode.FILE_NOT_FOUND,
                    stage="analyze_receptor",
                    message=f"receptor file not found: {payload.source}",
                ),
                status_code=404,
            ) from None
        try:
            from app.utils.security import check_upload_size

            check_upload_size(pdb_path)
        except SecurityError as exc:
            raise UploadTooLargeError(
                StructuredError(
                    error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                    stage="analyze_receptor",
                    message=str(exc),
                    recoverable=True,
                    suggested_actions=["reduce the file size"],
                )
            ) from exc
        return _analyze_path(pdb_path)

    # multipart/form-data 上传路径
    if file is None or not file.filename:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="analyze_receptor",
                message="provide an uploaded PDB file or a JSON body "
                "with 'source'",
                recoverable=True,
            ),
            status_code=400,
        )
    limit = config.UPLOAD_MAX_MB * 1024 * 1024 + 1
    data = await file.read(limit)
    if len(data) > config.UPLOAD_MAX_MB * 1024 * 1024:
        raise UploadTooLargeError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="analyze_receptor",
                message=(
                    f"upload too large: > {config.UPLOAD_MAX_MB} MB limit"
                ),
                recoverable=True,
                suggested_actions=["reduce the PDB file size"],
            )
        )
    with tempfile.TemporaryDirectory(prefix="dockskill_upload_") as tmp:
        pdb_path = Path(tmp) / f"{sanitize_filename(file.filename)}.pdb"
        pdb_path.write_bytes(data)
        return _analyze_path(pdb_path)


def _bad_json(exc: Exception):
    raise ApiError(
        StructuredError(
            error_code=ErrorCode.INPUT_VALIDATION_FAILED,
            stage="analyze_receptor",
            message=f"invalid JSON body: {exc}",
        ),
        status_code=400,
    ) from exc


@router.post(
    "/prepare",
    summary="入队受体准备任务（清洗 + Meeko PDBQT）",
    responses={200: _CREATED_EXAMPLE},
)
def prepare_receptor(
    request: ReceptorPrepareRequest = Body(
        ...,
        examples=[
            {
            "source": "examples/data/sample_receptor.pdb",
            "config": {
                "selected_chains": None,
                "keep_waters": False,
                "keep_cofactors": [],
                "keep_metals": [],
                "remove_original_ligands": True,
                "alternate_location_policy": "highest_occupancy",
                "missing_residue_policy": "warn",
                "protonation_policy": "tool_default",
            },
        },
        ],
    ),
) -> dict:
    """校验 + 入队后立即返回 ``{"job_id", "state": "CREATED"}``。

    产物：``outputs/<job_id>/receptor/``（receptor_original.pdb、
    receptor_clean.pdb、receptor.pdbqt、receptor_preparation_report.json）。
    """
    try:
        pdb_path = safe_resolve(request.source, config.PROJECT_ROOT)
    except PathTraversalError as exc:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="analyze_receptor",
                message=str(exc),
                suggested_actions=["keep receptor source inside the project"],
            ),
            status_code=400,
        ) from exc
    if not pdb_path.is_file():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="analyze_receptor",
                message=f"receptor file not found: {request.source}",
            ),
            status_code=404,
        )
    from app.utils.security import check_upload_size

    try:
        check_upload_size(pdb_path)
    except SecurityError as exc:
        raise UploadTooLargeError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="analyze_receptor",
                message=str(exc),
                recoverable=True,
            )
        ) from exc

    job_id = queue.allocate_job_id("receptor_prepare")
    queue.start_worker()
    queue.enqueue_job(
        job_id,
        "receptor_prepare",
        "receptor_prepare",
        queue.make_receptor_prepare_task(
            {
                "source": request.source,
                "config": request.config.model_dump(),
            },
            job_id,
        ),
    )
    return {"job_id": job_id, "state": "CREATED"}
