"""输入 Schema 校验测试（与 examples/inputs 对齐 + 新增模型覆盖）。"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from app.schemas import (
    ComparisonOutput,
    DockingBox,
    DockingInput,
    DockingOutput,
    JobState,
    LigandPreparation,
    StructuredError,
    VinaParams,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = PROJECT_ROOT / "examples" / "inputs"
SCHEMAS_DIR = PROJECT_ROOT / "schemas"


def test_single_ligand_input_valid() -> None:
    data = json.loads((EXAMPLES / "single_ligand.json").read_text())
    parsed = DockingInput.model_validate(data)
    assert len(parsed.ligands) == 1
    assert parsed.docking_parameters.seed == 42
    assert parsed.docking_parameters.exhaustiveness == 8
    assert parsed.docking_parameters.num_modes == 9
    assert parsed.ligand_preparation.embed_method == "ETKDGv3"
    assert parsed.ligand_preparation.num_conformers == 10


def test_multiple_ligands_input_valid() -> None:
    data = json.loads((EXAMPLES / "multiple_ligands.json").read_text())
    parsed = DockingInput.model_validate(data)
    assert len(parsed.ligands) == 3


def test_invalid_smiles_input_structurally_valid() -> None:
    # invalid_smiles.json 的 JSON 结构本身应可通过 schema，
    # SMILES 化学合法性在 ligand 准备阶段才被拒绝。
    data = json.loads((EXAMPLES / "invalid_smiles.json").read_text())
    DockingInput.model_validate(data)


def test_box_edge_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        DockingInput.model_validate(
            {
                "job_name": "bad_box",
                "ligands": [{"ligand_id": "l1", "smiles": "CCO"}],
                "receptor": {"source": "examples/data/sample_receptor.pdb"},
                "docking_box": {
                    "center": [0.0, 0.0, 0.0],
                    "size": [40.0, 40.0, 40.0],
                },
            }
        )


def test_exhaustiveness_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        DockingInput.model_validate(
            {
                "job_name": "bad_exh",
                "ligands": [{"ligand_id": "l1", "smiles": "CCO"}],
                "receptor": {"source": "examples/data/sample_receptor.pdb"},
                "docking_parameters": {"exhaustiveness": 64},
            }
        )


def test_box_negative_size_rejected() -> None:
    with pytest.raises(ValidationError):
        DockingBox.model_validate(
            {"mode": "explicit", "center": [0, 0, 0], "size": [20, -5, 20]}
        )


def test_box_nan_center_rejected() -> None:
    with pytest.raises(ValidationError):
        DockingBox.model_validate(
            {"mode": "explicit", "center": [0, float("nan"), 0], "size": [20, 20, 20]}
        )


def test_box_modes_require_fields() -> None:
    with pytest.raises(ValidationError):
        DockingBox.model_validate({"mode": "reference_ligand"})
    with pytest.raises(ValidationError):
        DockingBox.model_validate({"mode": "residue_list"})
    with pytest.raises(ValidationError):
        DockingBox.model_validate({"mode": "explicit", "center": [0, 0, 0]})
    # whole_receptor 不需要额外字段
    DockingBox.model_validate({"mode": "whole_receptor"})
    # residue_list 提供残基即可
    DockingBox.model_validate({"mode": "residue_list", "residue_ids": ["A/585"]})


def test_duplicate_ligand_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        DockingInput.model_validate(
            {
                "job_name": "dup_ids",
                "ligands": [
                    {"ligand_id": "same", "smiles": "CCO"},
                    {"ligand_id": "same", "smiles": "CCN"},
                ],
                "receptor": {"source": "examples/data/sample_receptor.pdb"},
            }
        )


def test_job_state_has_12_states() -> None:
    assert len(JobState) == 12
    assert JobState.SUCCESS.value == "SUCCESS"


def test_vina_params_defaults() -> None:
    params = VinaParams()
    assert params.scoring_function == "vina"
    assert params.exhaustiveness == 8
    assert params.num_modes == 9
    assert params.energy_range == 3.0
    assert params.cpu == 4
    assert params.seed == 42


def test_ligand_preparation_defaults() -> None:
    prep = LigandPreparation()
    assert prep.add_hydrogens is True
    assert prep.embed_method == "ETKDGv3"
    assert prep.num_conformers == 10
    assert prep.optimize_force_field == "MMFF94"
    assert prep.max_iterations == 500
    assert prep.select_conformer_by == "minimum_force_field_energy"
    assert prep.random_seed == 42


def test_structured_error_roundtrip() -> None:
    error = StructuredError(
        error_code="INVALID_SMILES",
        stage="prepare_ligand",
        message="bad smiles",
        details={"smiles": "x"},
        recoverable=False,
        suggested_actions=["fix"],
    )
    dumped = error.model_dump()
    assert StructuredError.model_validate(dumped) == error


# ---------------------------------------------------------------------------
# JSON Schema 导出一致性与 jsonschema 校验（提示词 11 C 节）
# ---------------------------------------------------------------------------

EXPORTED_MODELS = {
    "docking_input.schema.json": DockingInput,
    "docking_output.schema.json": DockingOutput,
    "comparison_output.schema.json": ComparisonOutput,
    "error.schema.json": StructuredError,
}


def test_exported_schemas_exist_and_match_pydantic() -> None:
    """schemas/*.schema.json 必须与当前 Pydantic 模型导出完全一致。"""
    for filename, model in EXPORTED_MODELS.items():
        path = SCHEMAS_DIR / filename
        assert path.is_file(), f"missing {path}; run scripts/generate_schemas.py"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == model.model_json_schema(), (
            f"{filename} out of sync with Pydantic; "
            "run scripts/generate_schemas.py"
        )


def test_example_inputs_pass_jsonschema() -> None:
    """examples/inputs/*.json 全部通过 jsonschema 对 docking_input 的校验。"""
    schema = json.loads(
        (SCHEMAS_DIR / "docking_input.schema.json").read_text(encoding="utf-8")
    )
    inputs = sorted(EXAMPLES.glob("*.json"))
    assert inputs, "no example inputs found"
    for path in inputs:
        data = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(instance=data, schema=schema)


def test_error_schema_validates_structured_error() -> None:
    schema = json.loads(
        (SCHEMAS_DIR / "error.schema.json").read_text(encoding="utf-8")
    )
    payload = StructuredError(
        error_code="VINA_FAILED",
        stage="run_vina",
        message="boom",
    ).model_dump(mode="json")
    jsonschema.validate(instance=payload, schema=schema)
