"""受体分析与准备测试：正常受体/空 PDB/无 ATOM/链不存在/PDBQT。"""

from __future__ import annotations

import pytest

from app.schemas import ErrorCode, ReceptorConfig
from app.services.receptor_service import (
    ReceptorError,
    analyze_receptor,
    bounding_box_from_report,
    clean_receptor,
    prepare_receptor_pdbqt,
)


def test_sample_receptor_analyze(sample_receptor_path) -> None:
    report = analyze_receptor(sample_receptor_path)
    assert report["chains"] == ["A"]
    assert report["atom_count"] > 1000
    assert report["residue_count"] > 100
    assert report["num_models"] >= 1
    bb_min, bb_max = bounding_box_from_report(report)
    assert all(hi > lo for lo, hi in zip(bb_min, bb_max))


def test_sample_receptor_clean_and_pdbqt(sample_receptor_path, tmp_path) -> None:
    report = analyze_receptor(sample_receptor_path)
    clean_pdb = tmp_path / "clean.pdb"
    summary, warnings = clean_receptor(report, ReceptorConfig(), clean_pdb)
    assert clean_pdb.is_file()
    assert summary["remaining_atoms"] > 1000
    assert "removed" in summary and "kept" in summary

    pdbqt = tmp_path / "receptor.pdbqt"
    tool, pdbqt_warnings = prepare_receptor_pdbqt(clean_pdb, pdbqt)
    assert pdbqt.is_file() and pdbqt.stat().st_size > 0
    assert "ATOM" in pdbqt.read_text()
    assert tool.startswith("meeko")


def test_empty_pdb_rejected(tmp_path) -> None:
    empty = tmp_path / "empty.pdb"
    empty.write_text("")
    with pytest.raises(ReceptorError) as excinfo:
        analyze_receptor(empty)
    assert excinfo.value.code == ErrorCode.INVALID_RECEPTOR


def test_pdb_without_atom_rejected(tmp_path) -> None:
    no_atom = tmp_path / "noatom.pdb"
    no_atom.write_text("REMARK no atoms here\nEND\n")
    with pytest.raises(ReceptorError) as excinfo:
        analyze_receptor(no_atom)
    assert excinfo.value.code == ErrorCode.INVALID_RECEPTOR


def test_chain_not_found(sample_receptor_path, tmp_path) -> None:
    report = analyze_receptor(sample_receptor_path)
    config = ReceptorConfig(selected_chains=["Z"])
    with pytest.raises(ReceptorError) as excinfo:
        clean_receptor(report, config, tmp_path / "clean.pdb")
    assert excinfo.value.code == ErrorCode.CHAIN_NOT_FOUND
    assert excinfo.value.details["available_chains"] == ["A"]


def test_selected_chain_ok(sample_receptor_path, tmp_path) -> None:
    report = analyze_receptor(sample_receptor_path)
    config = ReceptorConfig(selected_chains=["A"])
    summary, _ = clean_receptor(report, config, tmp_path / "clean.pdb")
    assert summary["removed"]["chains"] == []
