"""批次内比较 API：POST /api/comparison。

基于已完成 job 的 ``reports/result.json`` 重建结果并调用
comparison_service，附加雷达图维度（radar_dimensions，0-1 归一）
与科学边界警告（scientific_warning）。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.api.deps import ApiError, JobNotFoundError, resolve_job_dir_or_404
from app.schemas import (
    ComparisonContext,
    ErrorCode,
    LigandResult,
    StructuredError,
)
from app.services import comparison_service

router = APIRouter(prefix="/api", tags=["comparison"])

#: 雷达图维度（每维归一到 [0,1]，越大越好；仅作展示性相对比较）
RADAR_DIMENSIONS = [
    "affinity",
    "ligand_efficiency",
    "pose_consistency",
    "drug_likeness",
    "preparation_quality",
]

_SCIENTIFIC_WARNING = (
    "Relative docking scores are empirical, display-only estimates computed "
    "within one batch; they are comparable only for the same receptor, box "
    "and Vina parameters, and are not absolute binding free energies, "
    "binding probabilities or any experimental/effect measure."
)


class ComparisonRequest(BaseModel):
    """比较请求体。"""

    job_id: str = Field(..., min_length=1, description="已完成（SUCCESS）的 job_id")


def _radar_entry(entry: dict) -> dict:
    """把单分子指标映射为 [0,1] 雷达维度。"""
    rel_aff = entry.get("relative_affinity")
    eff_norm = entry.get("ligand_efficiency_rank_norm")
    drug = [
        entry.get(f"{key}_fit")
        for key in ("molwt", "logp", "tpsa", "flexibility")
        if entry.get(f"{key}_fit") is not None
    ]
    return {
        "affinity": round(rel_aff, 4) if rel_aff is not None else None,
        "ligand_efficiency": round(eff_norm, 4) if eff_norm is not None else None,
        "pose_consistency": entry.get("pose_consistency"),
        "drug_likeness": round(sum(drug) / len(drug), 4) if drug else None,
        "preparation_quality": entry.get("preparation_quality"),
    }


@router.post(
    "/comparison",
    summary="批次内相对比较（含雷达图维度与科学警告）",
    responses={
        200: {
            "description": "ComparisonOutput + radar_dimensions + scientific_warning",
            "content": {
                "application/json": {
                    "example": {
                        "job_id": "20260805-120000_ethanol_demo",
                        "context": {
                            "receptor_sha256": "9f2c...",
                            "box_mode": "explicit",
                            "box_center": [18.3, 2.3, 21.4],
                            "box_size": [20.0, 20.0, 20.0],
                            "docking_parameters": {"exhaustiveness": 8},
                            "consistent": True,
                            "notes": [],
                        },
                        "ligand_ids": ["ethanol", "methanol"],
                        "metrics": {
                            "ethanol": {
                                "status": "SUCCESS",
                                "best_affinity_kcal_mol": -3.9,
                                "relative_affinity": 1.0,
                                "composite_display_score": 0.87,
                            }
                        },
                        "normalization_method": "Relative Docking Profile ...",
                        "disclaimer": "相对指标仅用于同一批次...",
                        "radar_dimensions": RADAR_DIMENSIONS,
                        "radar": {
                            "ethanol": {
                                "affinity": 1.0,
                                "ligand_efficiency": 0.8,
                                "pose_consistency": 1.0,
                                "drug_likeness": 1.0,
                                "preparation_quality": 1.0,
                            }
                        },
                        "scientific_warning": _SCIENTIFIC_WARNING,
                    }
                }
            },
        }
    },
)
def comparison(
    request: ComparisonRequest = Body(
        ..., examples=[{"job_id": "20260805-120000_demo"}]
    ),
) -> dict:
    """读取已完成 job 的结果做批次内相对比较。

    单分子批次不虚构比较分（metrics 中只有原始指标与 note）。
    """
    job_dir: Path = resolve_job_dir_or_404(request.job_id)
    job_json = job_dir / "job.json"
    if not job_json.is_file():
        raise JobNotFoundError(request.job_id)
    record = json.loads(job_json.read_text(encoding="utf-8"))
    if record.get("state") != "SUCCESS":
        raise ApiError(
            StructuredError(
                error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                stage="comparison",
                message=(
                    f"job {request.job_id} is not in SUCCESS state "
                    f"(current: {record.get('state')})"
                ),
                details={"state": record.get("state")},
                recoverable=True,
                suggested_actions=["wait for the job to finish and retry"],
            ),
            status_code=409,
        )
    result_path = job_dir / "reports" / "result.json"
    if not result_path.is_file():
        raise JobNotFoundError(request.job_id)
    output = json.loads(result_path.read_text(encoding="utf-8"))

    receptor_sha256 = None
    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        receptor_sha256 = manifest.get("receptor_sha256")

    results = [LigandResult.model_validate(r) for r in output.get("results", [])]
    box = output.get("docking_box") or {}
    context = ComparisonContext(
        receptor_sha256=receptor_sha256,
        box_mode=box.get("mode"),
        box_center=box.get("center"),
        box_size=box.get("size"),
        docking_parameters=output.get("docking_parameters") or {},
        consistent=True,
        notes=[],
    )
    comparison_output = comparison_service.compare_in_batch(
        results, context=context, job_id=request.job_id
    )
    payload = comparison_output.model_dump(mode="json")
    payload["radar_dimensions"] = RADAR_DIMENSIONS
    payload["radar"] = {
        ligand_id: _radar_entry(entry)
        for ligand_id, entry in payload["metrics"].items()
        if entry.get("status") == "SUCCESS"
    }
    warnings = [_SCIENTIFIC_WARNING]
    if output.get("warnings"):
        warnings.append(
            "job-level warnings: " + "; ".join(output["warnings"][:5])
        )
    payload["scientific_warning"] = " ".join(warnings)
    return payload
