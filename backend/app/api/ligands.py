"""小分子准备 API：POST /api/ligands/prepare（入队，立即返回 job_id）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import config
from app.api import queue
from app.api.deps import ApiError, validate_ligand_smiles
from app.schemas import (
    ErrorCode,
    LigandPreparation,
    LigandSpec,
    StructuredError,
)
from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/ligands", tags=["ligands"])


class LigandPrepareRequest(BaseModel):
    """分子准备请求体（一次最多 20 个分子）。"""

    ligands: list[LigandSpec] = Field(
        ..., min_length=1, description="待准备的小分子列表"
    )
    ligand_preparation: LigandPreparation = Field(
        default_factory=LigandPreparation, description="3D 准备参数"
    )


_PREPARE_EXAMPLE = {
    "ligands": [
        {"ligand_id": "ethanol", "smiles": "CCO", "name": "ethanol"}
    ],
    "ligand_preparation": {
        "add_hydrogens": True,
        "embed_method": "ETKDGv3",
        "num_conformers": 10,
        "optimize_force_field": "MMFF94",
        "max_iterations": 500,
        "select_conformer_by": "minimum_force_field_energy",
        "random_seed": 42,
    },
}

_CREATED_EXAMPLE = {
    "description": "已入队；后台串行执行，用 GET /api/jobs/{job_id} 轮询",
    "content": {
        "application/json": {
            "example": {
                "job_id": "20260805-120000_ligand_prepare",
                "state": "CREATED",
            }
        }
    },
}


@router.post(
    "/prepare",
    summary="入队小分子 3D 准备任务",
    status_code=200,
    responses={200: _CREATED_EXAMPLE},
)
def prepare_ligands(
    request: LigandPrepareRequest = Body(..., examples=[_PREPARE_EXAMPLE]),
) -> dict:
    """校验 + 入队后立即返回 ``{"job_id", "state": "CREATED"}``。

    产物：``outputs/<job_id>/ligands/<ligand_id>/ligand.{sdf,pdb,pdbqt}``
    与 ``ligand_2d.svg`` / ``ligand_metadata.json``。
    """
    return _submit(request)


def _submit(request: LigandPrepareRequest) -> dict:
    if len(request.ligands) > config.BATCH_MAX_LIGANDS:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="validate_input",
                message=(
                    f"too many ligands: {len(request.ligands)} > "
                    f"{config.BATCH_MAX_LIGANDS}"
                ),
                details={"limit": config.BATCH_MAX_LIGANDS},
                recoverable=True,
                suggested_actions=["split into smaller batches"],
            ),
            status_code=400,
        )
    ids = [spec.ligand_id for spec in request.ligands]
    if len(set(ids)) != len(ids):
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="validate_input",
                message="ligand_id must be unique within one job",
                details={"ligand_ids": ids},
            ),
            status_code=400,
        )
    for spec in request.ligands:
        validate_ligand_smiles(spec.smiles, spec.ligand_id)

    job_id = queue.allocate_job_id("ligand_prepare")
    queue.start_worker()
    queue.enqueue_job(
        job_id,
        "ligand_prepare",
        "ligand_prepare",
        queue.make_ligand_prepare_task(
            {
                "ligands": [s.model_dump() for s in request.ligands],
                "ligand_preparation": request.ligand_preparation.model_dump(),
            },
            job_id,
        ),
    )
    return {"job_id": job_id, "state": "CREATED"}
