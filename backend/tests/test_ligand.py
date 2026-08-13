"""小分子准备测试：正常分子/多片段/非法 SMILES/UFF 回退/元素白名单等。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas import ErrorCode, LigandPreparation, LigandSpec
from app.services.ligand_service import (
    MAX_HEAVY_ATOMS,
    LigandError,
    prepare_ligand,
    validate_smiles,
)

PREP = LigandPreparation(num_conformers=3, random_seed=42)


def test_valid_ethanol_full_pipeline(tmp_path: Path) -> None:
    result = prepare_ligand(
        LigandSpec(ligand_id="ethanol", smiles="CCO"), PREP, tmp_path
    )
    assert result.status == "SUCCESS"
    assert result.descriptors["heavy_atom_count"] == 3
    assert result.descriptors["isomeric_smiles"] == "CCO"
    for filename in (
        "ligand.sdf", "ligand.pdb", "ligand.pdbqt", "ligand_metadata.json",
    ):
        assert (tmp_path / filename).is_file(), filename
    pdbqt = (tmp_path / "ligand.pdbqt").read_text()
    assert "ROOT" in pdbqt and "ENDROOT" in pdbqt and "TORSDOF" in pdbqt
    assert result.provenance["pdbqt_tool"].startswith("meeko")


def test_chiral_molecule_keeps_stereo(tmp_path: Path) -> None:
    result = prepare_ligand(
        LigandSpec(ligand_id="chiral", smiles="C[C@H](N)O"), PREP, tmp_path
    )
    assert "@" in result.descriptors["isomeric_smiles"]


def test_multi_fragment_rejected() -> None:
    with pytest.raises(LigandError) as excinfo:
        validate_smiles("CCO.CC(=O)[O-].[Na+]")
    assert excinfo.value.code == ErrorCode.MULTI_FRAGMENT_LIGAND


def test_invalid_smiles_rejected() -> None:
    with pytest.raises(LigandError) as excinfo:
        validate_smiles("NOT_A_SMILES((")
    assert excinfo.value.code == ErrorCode.INVALID_SMILES


def test_empty_smiles_rejected() -> None:
    with pytest.raises(LigandError) as excinfo:
        validate_smiles("   ")
    assert excinfo.value.code == ErrorCode.INVALID_SMILES


def test_unsupported_element_rejected() -> None:
    with pytest.raises(LigandError) as excinfo:
        validate_smiles("[Pt](Cl)(Cl)(N)(N)C")  # 含铂配合物片段
    assert excinfo.value.code == ErrorCode.UNSUPPORTED_ELEMENT


def test_oversized_molecule_rejected() -> None:
    # 超过重原子数上限的长链
    big = "C" * (MAX_HEAVY_ATOMS + 5)
    with pytest.raises(LigandError) as excinfo:
        validate_smiles(big)
    assert excinfo.value.code == ErrorCode.LIGAND_TOO_LARGE


def test_uff_fallback_recorded(tmp_path: Path) -> None:
    """硼杂苯无 MMFF 参数 → 受控回退 UFF 且记录 warning（禁止静默）。"""
    result = prepare_ligand(
        LigandSpec(ligand_id="borabenzene", smiles="[B]1CCCCC1"), PREP, tmp_path
    )
    assert result.status == "SUCCESS"
    assert result.provenance["force_field_used"] == "UFF"
    assert any("UFF" in w for w in result.preparation_warnings)


def test_undefined_stereo_warning() -> None:
    mol, warnings = validate_smiles("C(F)(Cl)Br")
    assert mol is not None
    assert any("stereo" in w for w in warnings)


def test_conformer_generation_failure(monkeypatch) -> None:
    """构象嵌入失败 → CONFORMER_GENERATION_FAILED。"""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    from app.services import ligand_service

    monkeypatch.setattr(AllChem, "EmbedMultipleConfs", lambda *a, **k: [])
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    with pytest.raises(LigandError) as excinfo:
        ligand_service.generate_conformers(mol, 10, 42)
    assert excinfo.value.code == ErrorCode.CONFORMER_GENERATION_FAILED
