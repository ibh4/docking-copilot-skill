"""失败案例回归测试：examples/failure_cases/ 每个案例均有对应 pytest。

全部走真实执行路径；仅 CONFORMER_GENERATION_FAILED / NO_POSE 两处使用 mock
（真实环境中这两种失败难以稳定构造，mock 目标为单一函数，其余流程真实执行），
与各自 expected.json 的 notes 说明一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from app import config
from app.schemas import DockingInput, ErrorCode, JobState, StructuredError
from app.services import ligand_service, vina_service
from app.workflow.runner import run_job

CASES_DIR = Path(__file__).resolve().parents[2] / "examples" / "failure_cases"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "docking_input.schema.json"
)

CASE_CODES = sorted(
    p.name for p in CASES_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")
)


def _load_case(code: str) -> tuple[dict, dict, Path]:
    case_dir = CASES_DIR / code
    input_json = json.loads((case_dir / "input.json").read_text(encoding="utf-8"))
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    return input_json, expected, case_dir


def _run_case(code: str, outputs_dir: Path):
    """从案例目录加载输入并真实执行 run_job，返回 (outcome, expected)。"""
    input_json, expected, _ = _load_case(code)
    docking_input = DockingInput.model_validate(input_json)
    old = config.OUTPUTS_DIR
    config.OUTPUTS_DIR = outputs_dir
    try:
        outcome = run_job(docking_input)
    finally:
        config.OUTPUTS_DIR = old
    return outcome, expected


# ---------------------------------------------------------------------------
# 元测试：案例集本身完整性
# ---------------------------------------------------------------------------


def test_at_least_13_failure_cases_exist() -> None:
    assert len(CASE_CODES) >= 13, CASE_CODES


@pytest.mark.parametrize("code", CASE_CODES)
def test_case_files_complete_and_schema_valid(code: str) -> None:
    """每个案例必须有 input.json + expected.json，且输入通过 jsonschema。"""
    input_json, expected, case_dir = _load_case(code)
    assert (case_dir / "input.json").is_file()
    assert (case_dir / "expected.json").is_file()
    for key in ("error_code", "stage", "recoverable", "suggested_actions", "pytest"):
        assert key in expected, f"{code}: expected.json missing {key}"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=input_json, schema=schema)


# ---------------------------------------------------------------------------
# 原有回归测试（Phase 1 保留）
# ---------------------------------------------------------------------------


def test_invalid_smiles_job_fails_structured(make_docking_input, tmp_path) -> None:
    old = config.OUTPUTS_DIR
    config.OUTPUTS_DIR = tmp_path
    try:
        outcome = run_job(make_docking_input(smiles="NOT_A_SMILES(("))
    finally:
        config.OUTPUTS_DIR = old
    assert outcome.state is JobState.FAILED
    error = outcome.structured_error
    assert error is not None
    assert error.error_code == "INVALID_SMILES"
    assert error.stage == "prepare_ligand"
    # 失败路径也必须有 manifest 与 result.json（可诊断）
    assert (outcome.job_dir / "manifest.json").is_file()
    assert (outcome.job_dir / "reports" / "result.json").is_file()


def test_box_outside_receptor_fails(make_docking_input, tmp_path) -> None:
    old = config.OUTPUTS_DIR
    config.OUTPUTS_DIR = tmp_path
    try:
        outcome = run_job(
            make_docking_input(box_center=(500.0, 500.0, 500.0))
        )
    finally:
        config.OUTPUTS_DIR = old
    assert outcome.state is JobState.FAILED
    assert outcome.structured_error.error_code == "BOX_OUTSIDE_RECEPTOR"
    assert outcome.structured_error.stage == "validate_box"


def test_chain_not_found_job_fails(make_docking_input, tmp_path) -> None:
    old = config.OUTPUTS_DIR
    config.OUTPUTS_DIR = tmp_path
    try:
        docking_input = make_docking_input()
        docking_input.receptor.config.selected_chains = ["Z"]
        outcome = run_job(docking_input)
    finally:
        config.OUTPUTS_DIR = old
    assert outcome.state is JobState.FAILED
    assert outcome.structured_error.error_code == "CHAIN_NOT_FOUND"


def test_receptor_file_not_found(make_docking_input, tmp_path) -> None:
    old = config.OUTPUTS_DIR
    config.OUTPUTS_DIR = tmp_path
    try:
        outcome = run_job(
            make_docking_input(receptor_source="examples/data/does_not_exist.pdb")
        )
    finally:
        config.OUTPUTS_DIR = old
    assert outcome.state is JobState.FAILED
    assert outcome.structured_error.error_code == "FILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# 案例驱动测试（与 examples/failure_cases/<CODE>/expected.json 对齐）
# ---------------------------------------------------------------------------


def _assert_failed_with(outcome, expected: dict) -> StructuredError:
    assert outcome.state is JobState.FAILED
    error = outcome.structured_error
    assert error is not None
    assert error.error_code == expected["error_code"]
    assert error.stage == expected["stage"]
    # 失败路径必须可诊断：manifest + result.json 落盘
    assert (outcome.job_dir / "manifest.json").is_file()
    assert (outcome.job_dir / "reports" / "result.json").is_file()
    return error


def test_case_invalid_smiles(tmp_path) -> None:
    outcome, expected = _run_case("INVALID_SMILES", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_multi_fragment_ligand(tmp_path) -> None:
    outcome, expected = _run_case("MULTI_FRAGMENT_LIGAND", tmp_path)
    error = _assert_failed_with(outcome, expected)
    assert error.details.get("num_fragments", 0) >= 2


def test_case_conformer_generation_failed(tmp_path, monkeypatch) -> None:
    """mock ETKDGv3 嵌入失败（真实大刚性分子失败难以稳定构造）。"""

    def _fail(mol, num_conformers, seed):
        raise ligand_service.LigandError(
            ErrorCode.CONFORMER_GENERATION_FAILED,
            f"ETKDGv3 failed to embed any of {num_conformers} conformers",
            details={"num_conformers": num_conformers, "seed": seed},
            suggested_actions=[
                "reduce ring complexity or retry with more conformers"
            ],
        )

    monkeypatch.setattr(ligand_service, "generate_conformers", _fail)
    outcome, expected = _run_case("CONFORMER_GENERATION_FAILED", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_unsupported_element(tmp_path) -> None:
    outcome, expected = _run_case("UNSUPPORTED_ELEMENT", tmp_path)
    error = _assert_failed_with(outcome, expected)
    assert "Fe" in error.details.get("elements", [])


def test_case_invalid_receptor(tmp_path) -> None:
    outcome, expected = _run_case("INVALID_RECEPTOR", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_chain_not_found(tmp_path) -> None:
    outcome, expected = _run_case("CHAIN_NOT_FOUND", tmp_path)
    error = _assert_failed_with(outcome, expected)
    assert "A" in error.details.get("available_chains", [])


def test_case_box_outside_receptor(tmp_path) -> None:
    outcome, expected = _run_case("BOX_OUTSIDE_RECEPTOR", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_box_too_large(tmp_path) -> None:
    outcome, expected = _run_case("BOX_TOO_LARGE", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_receptor_preparation_failed(tmp_path) -> None:
    outcome, expected = _run_case("RECEPTOR_PREPARATION_FAILED", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_vina_failed(tmp_path) -> None:
    """损坏 PDBQT 直接调用 dock_one：Python API 失败后回退 CLI 同样失败。"""
    _, expected, case_dir = _load_case("VINA_FAILED")
    corrupt = case_dir / "ligand_corrupt.pdbqt"
    assert corrupt.is_file()
    receptor_stub = tmp_path / "receptor_stub.pdbqt"
    receptor_stub.write_text(corrupt.read_text(encoding="utf-8"), encoding="utf-8")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    with pytest.raises(vina_service.VinaEngineError) as exc_info:
        vina_service.dock_one(
            receptor_stub,
            corrupt,
            [18.3, 2.3, 21.4],
            [20.0, 20.0, 20.0],
            DockingInput.model_validate(
                _load_case("VINA_FAILED")[0]
            ).docking_parameters,
            logs_dir,
        )
    assert exc_info.value.code == expected["error_code"]
    # runner 中该异常映射到 run_vina 阶段
    assert expected["stage"] == "run_vina"


def test_case_no_pose(tmp_path, monkeypatch) -> None:
    """mock dock_one 返回无 REMARK VINA RESULT 的输出（box 合法时真实 Vina
    总会产出 pose，故用 mock 复现解析不到 pose 的路径）。"""
    monkeypatch.setattr(
        vina_service,
        "dock_one",
        lambda *args, **kwargs: vina_service.DockRunResult(
            output_text="no poses found\n", engine_used="vina python api"
        ),
    )
    outcome, expected = _run_case("NO_POSE", tmp_path)
    _assert_failed_with(outcome, expected)


def test_case_partial_batch_failure(tmp_path) -> None:
    outcome, expected = _run_case("PARTIAL_BATCH_FAILURE", tmp_path)
    assert outcome.state is JobState.SUCCESS
    assert outcome.output is not None
    by_id = {r.ligand_id: r for r in outcome.output.results}
    assert by_id["ethanol_ok"].status == "SUCCESS"
    assert by_id["ethanol_ok"].best_affinity_kcal_mol is not None
    broken = by_id["broken_one"]
    assert broken.status == "FAILED"
    assert broken.structured_error is not None
    assert broken.structured_error.error_code == expected["error_code"]
    assert broken.structured_error.stage == expected["stage"]
    # 任务级警告中必须提示部分失败
    assert any("failed preparation" in w for w in outcome.output.warnings)


def test_case_artifact_access_denied(tmp_path) -> None:
    outcome, expected = _run_case("ARTIFACT_ACCESS_DENIED", tmp_path)
    error = _assert_failed_with(outcome, expected)
    assert "outside" in error.message or "resolves" in error.message
