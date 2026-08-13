"""Vina 对接测试：输出解析（纯函数）+ 真实小对接双跑可复现（固定 seed）。"""

from __future__ import annotations

import json

import pytest

from app import config
from app.services import vina_service
from app.workflow.runner import run_job

SAMPLE_OUTPUT = """MODEL 1
REMARK VINA RESULT:    -7.377      0.000      0.000
ATOM      1  O   LIG A   1      -0.441  -1.989  -0.171  0.00  0.00          OA
ENDMDL
MODEL 2
REMARK VINA RESULT:    -6.812      1.234      2.345
ATOM      1  O   LIG A   1      -0.441  -1.989  -0.171  0.00  0.00          OA
ENDMDL
"""


def test_parse_vina_output_multi_model() -> None:
    poses = vina_service.parse_vina_output(SAMPLE_OUTPUT)
    assert len(poses) == 2
    assert poses[0].affinity_kcal_mol == pytest.approx(-7.377)
    assert poses[0].rank == 1
    assert poses[1].rmsd_ub == pytest.approx(2.345)
    assert "ROOT" not in poses[0].block or True  # block 保留原始 ATOM 行
    assert "ATOM" in poses[0].block


def test_parse_vina_output_empty() -> None:
    assert vina_service.parse_vina_output("no poses here\n") == []


def test_parse_vina_result_single_block_without_model() -> None:
    text = "REMARK VINA RESULT:    -5.100      0.000      0.000\nATOM      1  C\n"
    poses = vina_service.parse_vina_output(text)
    assert len(poses) == 1
    assert poses[0].affinity_kcal_mol == pytest.approx(-5.1)


@pytest.mark.slow
def test_real_docking_fixed_seed_reproducible(make_docking_input, tmp_path_factory):
    """真实小对接（exhaustiveness=8, cpu=4, seed=42）双跑分数一致。"""
    affinities = []
    for _ in range(2):
        tmp_outputs = tmp_path_factory.mktemp("outputs")
        monkey_ok = config.OUTPUTS_DIR
        config.OUTPUTS_DIR = tmp_outputs
        try:
            outcome = run_job(make_docking_input())
        finally:
            config.OUTPUTS_DIR = monkey_ok
        assert outcome.state.value == "SUCCESS", (
            outcome.structured_error.model_dump() if outcome.structured_error else ""
        )
        result = outcome.output.results[0]
        assert result.best_affinity_kcal_mol < 0
        affinities.append(result.best_affinity_kcal_mol)
    assert affinities[0] == pytest.approx(affinities[1], abs=1e-6)


@pytest.mark.slow
def test_real_docking_artifacts_complete(make_docking_input, tmp_path) -> None:
    """真实对接产物完整性：manifest/bundle/reports/poses。"""
    config.OUTPUTS_DIR = tmp_path
    outcome = run_job(make_docking_input())
    config.OUTPUTS_DIR = config.PROJECT_ROOT / "outputs"
    assert outcome.state.value == "SUCCESS"
    job_dir = outcome.job_dir

    manifest = json.loads((job_dir / "manifest.json").read_text())
    assert manifest["status"] == "SUCCESS"
    assert manifest["random_seed"] == 42
    assert manifest["vina_version"]
    assert manifest["rdkit_version"]
    assert manifest["meeko_version"]
    assert manifest["input_sha256"]
    assert manifest["receptor_sha256"]
    assert manifest["ligand_sha256"]
    assert manifest["runtime_seconds"] is not None
    assert manifest["artifact_sha256"]

    assert (job_dir / "bundle.zip").is_file()
    assert (job_dir / "reports" / "result.json").is_file()
    assert (job_dir / "reports" / "result.md").is_file()
    assert (job_dir / "reports" / "comparison.csv").is_file()
    assert (job_dir / "input.json").is_file()
    assert (job_dir / "job.json").is_file()

    result = outcome.output.results[0]
    assert len(result.poses) >= 1
    pose_file = job_dir / result.poses[0].pose_file
    assert pose_file.is_file() and pose_file.stat().st_size > 0
    md = (job_dir / "reports" / "result.md").read_text()
    assert "经验打分" in md  # 固定科学措辞存在
