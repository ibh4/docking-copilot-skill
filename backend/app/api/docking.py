"""对接任务 API：POST /api/docking/run 与 /api/docking/batch（入队执行）。

提交前做快速预校验（非法输入直接 4xx，不产生 job）：
- 受体文件存在且可解析（safe_resolve 防穿越）；
- 每个 SMILES 可被 RDKit 解析（否则 INVALID_SMILES）；
- explicit box 与受体包围盒相交、边长/体积在 config 上限内
  （否则 BOX_OUTSIDE_RECEPTOR / BOX_TOO_LARGE / INVALID_BOX）。
"""

from __future__ import annotations

from fastapi import APIRouter, Body

from app import config
from app.api import queue
from app.api.deps import ApiError, validate_ligand_smiles
from app.schemas import DockingInput, ErrorCode, StructuredError
from app.services import box_service, receptor_service
from app.utils.files import PathTraversalError, safe_resolve
from app.utils.security import SecurityError, check_upload_size

router = APIRouter(prefix="/api/docking", tags=["docking"])

_RUN_EXAMPLE = {
    "job_name": "ethanol_demo",
    "ligands": [{"ligand_id": "ethanol", "smiles": "CCO", "name": "ethanol"}],
    "ligand_preparation": {
        "add_hydrogens": True,
        "embed_method": "ETKDGv3",
        "num_conformers": 10,
        "optimize_force_field": "MMFF94",
        "max_iterations": 500,
        "select_conformer_by": "minimum_force_field_energy",
        "random_seed": 42,
    },
    "receptor": {"source": "examples/data/sample_receptor.pdb"},
    "docking_box": {
        "mode": "explicit",
        "center": [18.3, 2.3, 21.4],
        "size": [20.0, 20.0, 20.0],
        "padding_angstrom": 8.0,
        "units": "angstrom",
    },
    "docking_parameters": {
        "scoring_function": "vina",
        "exhaustiveness": 8,
        "num_modes": 9,
        "energy_range": 3.0,
        "cpu": 4,
        "seed": 42,
    },
}

_CREATED_EXAMPLE = {
    "description": "已入队；后台串行执行，用 GET /api/jobs/{job_id} 轮询状态",
    "content": {
        "application/json": {
            "example": {
                "job_id": "20260805-120000_ethanol_demo",
                "state": "CREATED",
            }
        }
    },
}


def _pre_validate(docking_input: DockingInput) -> None:
    """提交前快速校验：受体可读、SMILES 合法、box 合法。失败抛 ApiError。"""
    try:
        receptor_path = safe_resolve(
            docking_input.receptor.source, config.PROJECT_ROOT
        )
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
    if not receptor_path.is_file():
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.FILE_NOT_FOUND,
                stage="analyze_receptor",
                message=(
                    f"receptor file not found: {docking_input.receptor.source}"
                ),
            ),
            status_code=404,
        )
    try:
        check_upload_size(receptor_path)
    except SecurityError as exc:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="analyze_receptor",
                message=str(exc),
                recoverable=True,
            ),
            status_code=413,
        ) from exc

    for spec in docking_input.ligands:
        validate_ligand_smiles(spec.smiles, spec.ligand_id)

    # explicit box 需要受体包围盒；其余模式在 job 内由 runner 校验
    try:
        report = receptor_service.analyze_receptor(receptor_path)
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
    box_report = dict(report)
    box_report["bounding_box"] = receptor_service.bounding_box_from_report(report)
    try:
        box_service.build_box(docking_input.docking_box, box_report)
    except box_service.BoxError as exc:
        raise ApiError(
            StructuredError(
                error_code=exc.code,
                stage="validate_box",
                message=str(exc),
                details=exc.details,
                recoverable=exc.recoverable,
                suggested_actions=exc.suggested_actions
                or ["adjust docking_box"],
            ),
            status_code=400,
        ) from exc


def _submit(docking_input: DockingInput) -> dict:
    if len(docking_input.ligands) > config.BATCH_MAX_LIGANDS:
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="validate_input",
                message=(
                    f"too many ligands: {len(docking_input.ligands)} > "
                    f"{config.BATCH_MAX_LIGANDS}"
                ),
                details={"limit": config.BATCH_MAX_LIGANDS},
                recoverable=True,
                suggested_actions=["split into smaller batches"],
            ),
            status_code=400,
        )
    _pre_validate(docking_input)
    job_id = queue.allocate_job_id(docking_input.job_name)
    queue.start_worker()
    queue.enqueue_job(
        job_id,
        docking_input.job_name,
        "docking",
        queue.make_docking_task(docking_input, job_id),
    )
    return {"job_id": job_id, "state": "CREATED"}


@router.post(
    "/run",
    summary="提交对接任务（入队，立即返回 job_id）",
    responses={200: _CREATED_EXAMPLE},
)
def docking_run(
    docking_input: DockingInput = Body(..., examples=[_RUN_EXAMPLE]),
) -> dict:
    """完整对接闭环：分子准备 → 受体准备 → box → Vina → 解析 → 报告 → 打包。"""
    return _submit(docking_input)


@router.post(
    "/batch",
    summary=f"批量对接（≤{config.BATCH_MAX_LIGANDS} 个分子，入队执行）",
    responses={200: _CREATED_EXAMPLE},
)
def docking_batch(
    docking_input: DockingInput = Body(..., examples=[_RUN_EXAMPLE]),
) -> dict:
    """与 /run 同一输入契约；批量上限 20 个分子。

    批次内部分子失败不会中断整个 job（逐分子受控失败，
    结果中带 per-ligand structured_error 与 PARTIAL 警告）。
    """
    return _submit(docking_input)
