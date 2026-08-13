"""批次内相对比较测试：分段函数、单分子不虚构比较分、公式透明。"""

from __future__ import annotations

import pytest

from app.schemas import LigandResult, Pose
from app.services.comparison_service import (
    compare_in_batch,
    flexibility_fit,
    logp_fit,
    molwt_fit,
    pose_consistency,
    tpsa_fit,
)


def _success_result(
    ligand_id: str, affinity: float, heavy: int = 10, warnings: int = 0
) -> LigandResult:
    return LigandResult(
        ligand_id=ligand_id,
        status="SUCCESS",
        best_affinity_kcal_mol=affinity,
        ligand_efficiency=round(-affinity / heavy, 4),
        poses=[
            Pose(rank=1, affinity_kcal_mol=affinity, rmsd_lb=0.0, rmsd_ub=0.0,
                 pose_file=f"poses/{ligand_id}/pose_001.pdbqt"),
            Pose(rank=2, affinity_kcal_mol=affinity + 1.5, rmsd_lb=1.0, rmsd_ub=2.0,
                 pose_file=f"poses/{ligand_id}/pose_002.pdbqt"),
        ],
        descriptors={"MolWt": 300.0, "LogP": 2.0, "TPSA": 60.0,
                     "rotatable_bonds": 3, "heavy_atom_count": heavy},
        preparation_warnings=["w"] * warnings,
    )


def test_piecewise_fits() -> None:
    assert molwt_fit(300.0) == 1.0
    assert molwt_fit(600.0) == 0.0
    assert molwt_fit(550.0) == pytest.approx(0.5)
    assert logp_fit(2.0) == 1.0
    assert logp_fit(-5.0) == 0.0
    assert logp_fit(6.0) == pytest.approx(0.5)
    assert tpsa_fit(100.0) == 1.0
    assert tpsa_fit(180.0) == 0.0
    assert flexibility_fit(3) == 1.0
    assert flexibility_fit(12) == 0.0
    assert pose_consistency(1.5) == 1.0
    assert pose_consistency(0.25) == pytest.approx(0.25)


def test_batch_relative_metrics_two_ligands() -> None:
    results = [_success_result("a", -8.0), _success_result("b", -6.0)]
    output = compare_in_batch(results, job_id="job1")
    assert output.metrics["a"]["relative_affinity"] == pytest.approx(1.0)
    assert output.metrics["b"]["relative_affinity"] == pytest.approx(0.0)
    assert output.metrics["a"]["in_batch_rank"] == 1
    assert output.metrics["b"]["in_batch_rank"] == 2
    assert output.metrics["a"]["pose_score_gap_kcal_mol"] == pytest.approx(1.5)
    # 公式必须写入 normalization_method
    assert "relative_affinity" in output.normalization_method
    assert "ligand_efficiency" in output.normalization_method


def test_single_ligand_no_fabricated_comparison() -> None:
    output = compare_in_batch([_success_result("solo", -7.5)], job_id="job2")
    entry = output.metrics["solo"]
    assert "composite_display_score" not in entry
    assert "in_batch_rank" not in entry
    assert entry["best_affinity_kcal_mol"] == pytest.approx(-7.5)
    assert "note" in entry  # 明确说明未做比较


def test_failed_ligand_only_raw_status() -> None:
    failed = LigandResult(ligand_id="bad", status="FAILED")
    output = compare_in_batch([failed, _success_result("ok", -7.0)])
    assert output.metrics["bad"]["status"] == "FAILED"
    assert "molwt_fit" not in output.metrics["bad"]


def test_preparation_quality_deduction() -> None:
    warned = _success_result("w", -7.0, warnings=3)
    output = compare_in_batch([warned, _success_result("clean", -6.5)])
    assert output.metrics["w"]["preparation_quality"] == pytest.approx(0.7)
    assert output.metrics["clean"]["preparation_quality"] == pytest.approx(1.0)
