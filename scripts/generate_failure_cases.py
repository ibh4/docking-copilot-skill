#!/usr/bin/env python3
"""生成 examples/failure_cases/<CODE>/ 失败案例集（提示词 11 D 节）。

每个案例目录包含：
- input.json（DockingInput，结构上合法；化学/资源层面故意触发失败）；
- expected.json（预期 error_code / stage / recoverable / suggested_actions）；
- 必要的辅助输入文件（空 PDB、损坏 PDB、损坏 PDBQT 等）。

对应用例见 backend/tests/test_failures.py。重新运行本脚本可再生成全部案例。

用法：
    conda run -n dockskill python scripts/generate_failure_cases.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = PROJECT_ROOT / "examples" / "failure_cases"

BASE_INPUT: dict = {
    "job_name": "failure_case",
    "ligands": [{"ligand_id": "candidate", "smiles": "CCO"}],
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
        "units": "angstrom",
    },
    "docking_parameters": {
        "exhaustiveness": 8,
        "num_modes": 9,
        "seed": 42,
        "cpu": 4,
        "energy_range": 3.0,
    },
}

#: 损坏但 RDKit/Vina 无法使用的配体 PDBQT（触发 VINA_FAILED）
CORRUPT_LIGAND_PDBQT = """REMARK  this pdbqt is deliberately corrupted for the VINA_FAILED failure case
ATOM      1  C1  UNL X   1       0.000   0.000   0.000  1.00  0.00
BROKEN SECTION {{{ not pdbqt }}}
ENDROOT_WITHOUT_ROOT
"""

#: 可被 Biopython 解析、但 meeko 无法参数化的受体（触发 RECEPTOR_PREPARATION_FAILED）
CORRUPT_RECEPTOR_PDB = """HEADER    DELIBERATELY CORRUPT RECEPTOR FOR FAILURE CASE
ATOM      1  N   XXX A   1       1.000   1.000   1.000  1.00  0.00           N
ATOM      2  CA  XXX A   1       2.000   1.000   1.000  1.00  0.00           C
ATOM      3  C   XXX A   1       3.000   1.000   1.000  1.00  0.00           C
ATOM      4  O   XXX A   1       3.500   2.000   1.000  1.00  0.00           O
ATOM      5  N   XXX A   2       4.000   0.000   1.000  1.00  0.00           N
ATOM      6  CA  XXX A   2       5.000   0.000   1.000  1.00  0.00           C
ATOM      7  C   XXX A   2       6.000   0.000   1.000  1.00  0.00           C
ATOM      8  O   XXX A   2       6.500   1.000   1.000  1.00  0.00           O
END
"""


def _input(**overrides) -> dict:
    data = copy.deepcopy(BASE_INPUT)
    for key, value in overrides.items():
        if key == "ligand_smiles":
            data["ligands"][0]["smiles"] = value
        elif key == "ligands":
            data["ligands"] = value
        elif key == "receptor_source":
            data["receptor"]["source"] = value
        elif key == "receptor_config":
            data["receptor"]["config"] = value
        elif key == "box":
            data["docking_box"] = value
        elif key == "job_name":
            data["job_name"] = value
        else:
            raise KeyError(key)
    return data


CASES: list[dict] = [
    {
        "code": "INVALID_SMILES",
        "input": _input(job_name="failure_invalid_smiles",
                        ligand_smiles="NOT_A_SMILES(("),
        "expected": {
            "case": "INVALID_SMILES",
            "error_code": "INVALID_SMILES",
            "stage": "prepare_ligand",
            "recoverable": False,
            "suggested_actions": ["check SMILES syntax"],
            "pytest": "backend/tests/test_failures.py::test_case_invalid_smiles",
            "notes": "SMILES 化学合法性在 ligand 准备阶段才被拒绝，"
                     "输入 JSON 结构本身合法。",
        },
    },
    {
        "code": "MULTI_FRAGMENT_LIGAND",
        "input": _input(job_name="failure_multi_fragment",
                        ligand_smiles="CCO.[Na+]"),
        "expected": {
            "case": "MULTI_FRAGMENT_LIGAND",
            "error_code": "MULTI_FRAGMENT_LIGAND",
            "stage": "prepare_ligand",
            "recoverable": False,
            "suggested_actions": ["keep the largest fragment or split the input"],
            "pytest": "backend/tests/test_failures.py::test_case_multi_fragment_ligand",
            "notes": "盐/混合物/复合物（多个不相连片段）不支持单分子对接。",
        },
    },
    {
        "code": "CONFORMER_GENERATION_FAILED",
        "input": _input(job_name="failure_conformer_generation",
                        ligand_smiles="CC(=O)Oc1ccccc1C(=O)O"),
        "expected": {
            "case": "CONFORMER_GENERATION_FAILED",
            "error_code": "CONFORMER_GENERATION_FAILED",
            "stage": "prepare_ligand",
            "recoverable": True,
            "suggested_actions": [
                "reduce ring complexity or retry with more conformers"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_conformer_generation_failed",
            "notes": "input.json 的 SMILES 本身可嵌入；pytest 通过 mock "
                     "ligand_service.generate_conformers 触发嵌入失败路径"
                     "（真实超大刚性分子的嵌入失败难以稳定构造）。",
        },
    },
    {
        "code": "UNSUPPORTED_ELEMENT",
        "input": _input(job_name="failure_unsupported_element",
                        ligand_smiles="[Fe+2]"),
        "expected": {
            "case": "UNSUPPORTED_ELEMENT",
            "error_code": "UNSUPPORTED_ELEMENT",
            "stage": "prepare_ligand",
            "recoverable": False,
            "suggested_actions": [
                "use only organic elements H,B,C,N,O,F,Si,P,S,Cl,Br,I"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_unsupported_element",
            "notes": "元素白名单见 backend/app/services/ligand_service.py。",
        },
    },
    {
        "code": "INVALID_RECEPTOR",
        "input": _input(
            job_name="failure_invalid_receptor",
            receptor_source="examples/failure_cases/INVALID_RECEPTOR/receptor_empty.pdb",
        ),
        "extra_files": {"receptor_empty.pdb": ""},
        "expected": {
            "case": "INVALID_RECEPTOR",
            "error_code": "INVALID_RECEPTOR",
            "stage": "analyze_receptor",
            "recoverable": False,
            "suggested_actions": ["provide a non-empty PDB with ATOM records"],
            "pytest": "backend/tests/test_failures.py::test_case_invalid_receptor",
            "notes": "空 PDB 文件在结构分析阶段即被拒绝。",
        },
    },
    {
        "code": "CHAIN_NOT_FOUND",
        "input": _input(
            job_name="failure_chain_not_found",
            receptor_config={"selected_chains": ["Z"]},
        ),
        "expected": {
            "case": "CHAIN_NOT_FOUND",
            "error_code": "CHAIN_NOT_FOUND",
            "stage": "prepare_receptor",
            "recoverable": True,
            "suggested_actions": ["choose from available chains"],
            "pytest": "backend/tests/test_failures.py::test_case_chain_not_found",
            "notes": "样例受体只有链 A；details.available_chains 给出可选链。",
        },
    },
    {
        "code": "BOX_OUTSIDE_RECEPTOR",
        "input": _input(
            job_name="failure_box_outside_receptor",
            box={
                "mode": "explicit",
                "center": [500.0, 500.0, 500.0],
                "size": [20.0, 20.0, 20.0],
                "units": "angstrom",
            },
        ),
        "expected": {
            "case": "BOX_OUTSIDE_RECEPTOR",
            "error_code": "BOX_OUTSIDE_RECEPTOR",
            "stage": "validate_box",
            "recoverable": True,
            "suggested_actions": [
                "move the box center toward the receptor bounding box"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_box_outside_receptor",
            "notes": "盒与受体包围盒无交集即拒绝。",
        },
    },
    {
        "code": "BOX_TOO_LARGE",
        "input": _input(
            job_name="failure_box_too_large",
            box={"mode": "whole_receptor", "padding_angstrom": 8.0,
                 "units": "angstrom"},
        ),
        "expected": {
            "case": "BOX_TOO_LARGE",
            "error_code": "BOX_TOO_LARGE",
            "stage": "validate_box",
            "recoverable": True,
            "suggested_actions": [
                "reduce padding_angstrom",
                "select fewer residues",
            ],
            "pytest": "backend/tests/test_failures.py::test_case_box_too_large",
            "notes": "样例受体包围盒约 53×41×54 Å，whole_receptor 模式计算出的"
                     "边长超过单边上限 30 Å。",
        },
    },
    {
        "code": "RECEPTOR_PREPARATION_FAILED",
        "input": _input(
            job_name="failure_receptor_preparation",
            receptor_source="examples/failure_cases/RECEPTOR_PREPARATION_FAILED/receptor_corrupt.pdb",
        ),
        "extra_files": {"receptor_corrupt.pdb": CORRUPT_RECEPTOR_PDB},
        "expected": {
            "case": "RECEPTOR_PREPARATION_FAILED",
            "error_code": "RECEPTOR_PREPARATION_FAILED",
            "stage": "prepare_receptor",
            "recoverable": False,
            "suggested_actions": [
                "provide a structurally valid receptor (standard residues)"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_receptor_preparation_failed",
            "notes": "PDB 可被 Biopython 解析（含 ATOM 记录），但全部残基为"
                     "未知残基名 XXX，meeko 严格模式与 --allow_bad_res 回退均失败。",
        },
    },
    {
        "code": "VINA_FAILED",
        "input": _input(job_name="failure_vina_failed"),
        "extra_files": {
            "ligand_corrupt.pdbqt": CORRUPT_LIGAND_PDBQT,
            "dock_setup.json": {
                "description": "pytest 直接调用 vina_service.dock_one，"
                               "receptor 用真实对接产物或样例受体的 pdbqt，"
                               "ligand 用本目录 ligand_corrupt.pdbqt。",
                "ligand_pdbqt": "ligand_corrupt.pdbqt",
                "box_center": [18.3, 2.3, 21.4],
                "box_size": [20.0, 20.0, 20.0],
                "vina_params": BASE_INPUT["docking_parameters"],
            },
        },
        "expected": {
            "case": "VINA_FAILED",
            "error_code": "VINA_FAILED",
            "stage": "run_vina",
            "recoverable": False,
            "suggested_actions": [
                "check ligand pdbqt integrity; regenerate with meeko"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_vina_failed",
            "notes": "损坏的配体 PDBQT：Vina Python API 解析失败后受控回退 CLI，"
                     "CLI 同样失败 → VINA_FAILED（双适配器错误均被保留）。",
        },
    },
    {
        "code": "NO_POSE",
        "input": _input(
            job_name="failure_no_pose",
            box={
                "mode": "explicit",
                "center": [38.0, 22.0, 46.0],
                "size": [10.0, 10.0, 10.0],
                "units": "angstrom",
            },
        ),
        "expected": {
            "case": "NO_POSE",
            "error_code": "NO_POSE",
            "stage": "parse_scores",
            "recoverable": True,
            "suggested_actions": ["check box placement and ligand pdbqt"],
            "pytest": "backend/tests/test_failures.py::test_case_no_pose",
            "notes": "合法且与受体包围盒相交的 box（远离活性位点）。真实运行中 "
                     "Vina 只要 box 合法总会输出 pose，因此 pytest 通过 mock "
                     "dock_one 返回无 REMARK VINA RESULT 的输出复现 NO_POSE 路径。",
        },
    },
    {
        "code": "PARTIAL_BATCH_FAILURE",
        "input": _input(
            job_name="failure_partial_batch",
            ligands=[
                {"ligand_id": "ethanol_ok", "smiles": "CCO"},
                {"ligand_id": "broken_one", "smiles": "NOT_A_SMILES(("},
            ],
        ),
        "expected": {
            "case": "PARTIAL_BATCH_FAILURE",
            "error_code": "INVALID_SMILES",
            "stage": "prepare_ligand",
            "recoverable": False,
            "partial_batch": True,
            "job_status": "SUCCESS",
            "suggested_actions": [
                "inspect per-ligand structured_error in reports/result.json"
            ],
            "pytest": "backend/tests/test_failures.py::test_case_partial_batch_failure",
            "notes": "批量中合法分子继续对接，任务整体 SUCCESS；失败分子的"
                     "结构化错误记录在其 LigandResult.structured_error 中。"
                     "error_code/stage 指失败分子 broken_one 的错误。",
        },
    },
    {
        "code": "ARTIFACT_ACCESS_DENIED",
        "input": _input(
            job_name="failure_artifact_access_denied",
            receptor_source="../../etc/passwd",
        ),
        "expected": {
            "case": "ARTIFACT_ACCESS_DENIED",
            "error_code": "INPUT_VALIDATION_FAILED",
            "stage": "analyze_receptor",
            "recoverable": False,
            "suggested_actions": ["keep receptor source inside the project"],
            "pytest": "backend/tests/test_failures.py::test_case_artifact_access_denied",
            "notes": "受体路径必须位于项目目录内；../ 路径穿越被 safe_resolve "
                     "拒绝（PathTraversalError），错误码统一为 "
                     "INPUT_VALIDATION_FAILED。",
        },
    },
]


def write_case(case: dict) -> Path:
    case_dir = CASES_DIR / case["code"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(
        json.dumps(case["input"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (case_dir / "expected.json").write_text(
        json.dumps(case["expected"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for name, content in (case.get("extra_files") or {}).items():
        target = case_dir / name
        if isinstance(content, (dict, list)):
            target.write_text(
                json.dumps(content, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            target.write_text(content, encoding="utf-8")
    return case_dir


def main() -> int:
    for case in CASES:
        case_dir = write_case(case)
        print(f"written: {case_dir}")
    print(f"total: {len(CASES)} failure cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
