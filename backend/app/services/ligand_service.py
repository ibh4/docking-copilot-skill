"""小分子准备服务：SMILES 校验 → AddHs → ETKDGv3 多构象 → 力场优化选优
→ 描述符 → SDF/PDB/PDBQT/SVG/metadata 产物。

约束（提示词 3）：
- PDBQT 必须经 Meeko（Python API 优先，CLI 回退），禁止字符串手工拼 PDBQT；
- MMFF 不可用时受控回退 UFF 并记录 warning，禁止静默修复；
- 所有失败抛出携带 ErrorCode 的 LigandError，由 runner 转 StructuredError。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import meeko
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, Draw

from app.schemas import ErrorCode, LigandPreparation, LigandResult, LigandSpec
from app.services.descriptor_service import compute_descriptors

RDLogger.DisableLog("rdApp.*")

try:  # RDKit 新版将 MMFFSanitizeMol 放在 rdForceFieldHelpers
    from rdkit.Chem.rdForceFieldHelpers import MMFFSanitizeMol as _mmff_sanitize
except ImportError:  # pragma: no cover —— 旧版兜底
    _mmff_sanitize = getattr(AllChem, "MMFFSanitizeMol", None)

#: 重原子数上限（虚拟筛选小分子尺度）
MAX_HEAVY_ATOMS = 100

#: 允许元素白名单（有机药物化学常见）
ALLOWED_ELEMENTS = {
    "H", "B", "C", "N", "O", "F", "Si", "P", "S", "Cl", "Br", "I",
}


class LigandError(Exception):
    """分子准备阶段的受控错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        suggested_actions: list[str] | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.suggested_actions = suggested_actions or []
        self.recoverable = recoverable


def _find_meeko_cli(basename: str) -> Path | None:
    """探测 Meeko CLI（conda-forge 版带 .py 后缀，pip 版不带）。"""
    for candidate in (basename, f"{basename}.py"):
        found = shutil.which(candidate)
        if found:
            return Path(found)
    return None


# ---------------------------------------------------------------------------
# 校验与构象生成（纯函数）
# ---------------------------------------------------------------------------


def validate_smiles(smiles: str | None) -> tuple[Chem.Mol, list[str]]:
    """校验 SMILES 并返回 (mol, warnings)。失败抛 LigandError。"""
    warnings: list[str] = []
    if not smiles or not smiles.strip():
        raise LigandError(
            ErrorCode.INVALID_SMILES,
            "SMILES is empty",
            suggested_actions=["provide a non-empty SMILES string"],
        )
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise LigandError(
            ErrorCode.INVALID_SMILES,
            f"RDKit failed to parse SMILES: {smiles!r}",
            details={"smiles": smiles},
            suggested_actions=["check SMILES syntax"],
        )
    frags = Chem.GetMolFrags(mol, asMols=True)
    if len(frags) > 1:
        raise LigandError(
            ErrorCode.MULTI_FRAGMENT_LIGAND,
            f"SMILES contains {len(frags)} disconnected fragments "
            "(salt/mixture/complex); only single-molecule docking is supported",
            details={"num_fragments": len(frags)},
            suggested_actions=["keep the largest fragment or split the input"],
        )
    heavy = mol.GetNumHeavyAtoms()
    if heavy == 0:
        raise LigandError(ErrorCode.INVALID_SMILES, "molecule has no heavy atoms")
    if heavy > MAX_HEAVY_ATOMS:
        raise LigandError(
            ErrorCode.LIGAND_TOO_LARGE,
            f"heavy atom count {heavy} exceeds limit {MAX_HEAVY_ATOMS}",
            details={"heavy_atom_count": heavy, "limit": MAX_HEAVY_ATOMS},
        )
    unsupported = sorted(
        {a.GetSymbol() for a in mol.GetAtoms() if a.GetSymbol() not in ALLOWED_ELEMENTS}
    )
    if unsupported:
        raise LigandError(
            ErrorCode.UNSUPPORTED_ELEMENT,
            f"unsupported element(s): {', '.join(unsupported)}",
            details={"elements": unsupported, "allowed": sorted(ALLOWED_ELEMENTS)},
        )
    if Chem.FindPotentialStereo(mol):
        warnings.append(
            "undefined stereochemistry detected; docking uses one "
            "unspecified stereoisomer"
        )
    return mol, warnings


def generate_conformers(
    mol_h: Chem.Mol, num_conformers: int, seed: int
) -> Chem.Mol:
    """ETKDGv3 多构象嵌入（确定性 seed）。失败抛 CONFORMER_GENERATION_FAILED。"""
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    params.pruneRmsThresh = 0.5
    ids = AllChem.EmbedMultipleConfs(mol_h, numConfs=num_conformers, params=params)
    if len(ids) == 0:
        raise LigandError(
            ErrorCode.CONFORMER_GENERATION_FAILED,
            f"ETKDGv3 failed to embed any of {num_conformers} conformers",
            details={"num_conformers": num_conformers, "seed": seed},
            suggested_actions=["reduce ring complexity or retry with more conformers"],
        )
    return mol_h


def optimize_and_select(
    mol: Chem.Mol, prep: LigandPreparation, warnings: list[str]
) -> tuple[int, float, str]:
    """优化全部构象并按最低力场能量选优，仅保留最优构象。

    返回 (选中构象 id, 能量, 实际使用的力场名)。
    MMFF 参数不可用时受控回退 UFF 并记录 warning（禁止静默）。
    """
    n_conf = mol.GetNumConformers()
    force_field = prep.optimize_force_field
    energies: dict[int, float] = {}

    mmff_ok = force_field == "MMFF94"
    if mmff_ok and _mmff_sanitize is not None and _mmff_sanitize(mol) != 0:
        mmff_ok = False
    if mmff_ok and AllChem.MMFFGetMoleculeProperties(mol) is None:
        mmff_ok = False
    if force_field == "MMFF94" and not mmff_ok:
        warnings.append(
            "MMFF94 parameters unavailable for this molecule; "
            "falling back to UFF (controlled fallback)"
        )
    use_ff = "MMFF94" if mmff_ok else "UFF"

    if use_ff == "MMFF94":
        opt_results = AllChem.MMFFOptimizeMoleculeConfs(
            mol, maxIters=prep.max_iterations
        )
    else:
        opt_results = AllChem.UFFOptimizeMoleculeConfs(
            mol, maxIters=prep.max_iterations
        )
    for conf, props in zip(mol.GetConformers(), opt_results):
        if props is not None and props[1] is not None:
            energies[conf.GetId()] = float(props[1])

    if not energies:
        raise LigandError(
            ErrorCode.CONFORMER_GENERATION_FAILED,
            f"{use_ff} optimization failed for all conformers",
            details={"force_field": use_ff},
        )
    if len(energies) < n_conf:
        warnings.append(
            f"{use_ff} optimization failed to converge for "
            f"{n_conf - len(energies)} conformer(s); they were excluded"
        )

    best_id, best_energy = min(energies.items(), key=lambda item: item[1])
    keep = [c.GetId() for c in mol.GetConformers() if c.GetId() != best_id]
    for cid in keep:
        mol.RemoveConformer(cid)
    return best_id, best_energy, use_ff


# ---------------------------------------------------------------------------
# PDBQT（Meeko 唯一入口）
# ---------------------------------------------------------------------------


def validate_pdbqt(text: str) -> None:
    """校验 PDBQT 必要内容：ROOT/ENDROOT/TORSDOF 与电荷非全零。"""
    if not text or not text.strip():
        raise LigandError(
            ErrorCode.PDBQT_PREPARATION_FAILED, "PDBQT output is empty"
        )
    for token in ("ROOT", "ENDROOT", "TORSDOF"):
        if token not in text:
            raise LigandError(
                ErrorCode.PDBQT_PREPARATION_FAILED,
                f"PDBQT missing required section: {token}",
            )
    charges: list[float] = []
    for line in text.splitlines():
        if line.startswith(("ATOM", "HETATM")) and len(line) > 78:
            try:
                charges.append(float(line[70:78].strip()))
            except ValueError:
                continue
    if charges and all(abs(c) < 1e-9 for c in charges):
        raise LigandError(
            ErrorCode.PDBQT_PREPARATION_FAILED,
            "PDBQT partial charges are all zero (unexpected for Meeko output)",
        )


def write_pdbqt(mol_3d: Chem.Mol, out_path: Path) -> str:
    """经 Meeko 生成 PDBQT 并写盘；返回所用工具描述。"""
    pdbqt_text: str | None = None
    used_tool: str | None = None

    # 路径 1：Meeko Python API
    try:
        from meeko import MoleculePreparation, PDBQTWriterLegacy

        setups = MoleculePreparation().prepare(mol_3d)
        if not setups:
            raise RuntimeError("meeko MoleculePreparation returned no setup")
        text, is_ok, err = PDBQTWriterLegacy.write_string(setups[0])
        if not is_ok:
            raise RuntimeError(f"PDBQTWriterLegacy failed: {err}")
        pdbqt_text, used_tool = text, "meeko python api"
    except Exception as api_exc:  # noqa: BLE001 —— 受控回退 CLI，错误信息保留
        cli = _find_meeko_cli("mk_prepare_ligand")
        if cli is None:
            raise LigandError(
                ErrorCode.PDBQT_PREPARATION_FAILED,
                "Meeko unavailable: python API failed and CLI not found",
                details={"python_api_error": str(api_exc)},
            ) from api_exc
        with tempfile.TemporaryDirectory() as tmp:
            sdf_in = Path(tmp) / "ligand.sdf"
            pdbqt_out = Path(tmp) / "ligand.pdbqt"
            writer = Chem.SDWriter(str(sdf_in))
            writer.write(mol_3d)
            writer.close()
            result = subprocess.run(
                [str(cli), "-i", str(sdf_in), "-o", str(pdbqt_out)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0 or not pdbqt_out.is_file():
                raise LigandError(
                    ErrorCode.PDBQT_PREPARATION_FAILED,
                    "mk_prepare_ligand CLI failed",
                    details={
                        "python_api_error": str(api_exc),
                        "returncode": result.returncode,
                        "stderr": result.stderr[-2000:],
                    },
                ) from api_exc
            pdbqt_text = pdbqt_out.read_text(encoding="utf-8")
            used_tool = f"meeko cli ({cli.name})"

    validate_pdbqt(pdbqt_text)
    out_path.write_text(pdbqt_text, encoding="utf-8")
    return used_tool


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def prepare_ligand(
    spec: LigandSpec,
    prep: LigandPreparation,
    ligand_dir: Path,
) -> LigandResult:
    """完整准备单个分子并落盘全部产物，返回 LigandResult。

    产物：ligand.sdf / ligand.pdb / ligand.pdbqt / ligand_2d.svg /
    ligand_metadata.json。
    """
    warnings: list[str] = []
    mol, val_warnings = validate_smiles(spec.smiles)
    warnings.extend(val_warnings)

    if prep.add_hydrogens:
        mol = Chem.AddHs(mol)
        if mol is None:
            raise LigandError(
                ErrorCode.INVALID_SMILES, "failed to add explicit hydrogens"
            )

    generate_conformers(mol, prep.num_conformers, prep.random_seed)
    selected_id, energy, used_ff = optimize_and_select(mol, prep, warnings)

    # 描述符与 SMILES 在去显式氢分子上计算，保证输出标准形式
    mol_no_h = Chem.RemoveHs(Chem.Mol(mol))
    descriptors = compute_descriptors(mol_no_h)

    # 2D 图（基于无氢分子，布局更清晰）
    AllChem.Compute2DCoords(mol_no_h)
    svg = Draw.MolToImage(mol_no_h, size=(480, 360), kekulize=False)
    # RDKit MolToImage 返回 PIL Image；存 svg 用 MolToSVG（如可用）
    try:
        from rdkit.Chem.Draw import rdMolDraw2D

        drawer = rdMolDraw2D.MolDraw2DSVG(480, 360)
        drawer.DrawMolecule(mol_no_h)
        drawer.FinishDrawing()
        (ligand_dir / "ligand_2d.svg").write_text(
            drawer.GetDrawingText(), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001 —— SVG 失败不阻断，PNG 兜底
        png_path = ligand_dir / "ligand_2d.png"
        svg.save(str(png_path))
        warnings.append("2D SVG rendering unavailable; saved PNG instead")

    sdf_path = ligand_dir / "ligand.sdf"
    writer = Chem.SDWriter(str(sdf_path))
    writer.write(mol)
    writer.close()

    pdb_path = ligand_dir / "ligand.pdb"
    pdb_path.write_text(Chem.MolToPDBBlock(mol), encoding="utf-8")

    pdbqt_path = ligand_dir / "ligand.pdbqt"
    meeko_tool = write_pdbqt(mol, pdbqt_path)

    metadata = {
        "ligand_id": spec.ligand_id,
        "input_smiles": spec.smiles,
        "canonical_smiles": descriptors["canonical_smiles"],
        "isomeric_smiles": descriptors["isomeric_smiles"],
        "molecular_formula": descriptors["molecular_formula"],
        "formal_charge": descriptors["formal_charge"],
        "heavy_atom_count": descriptors["heavy_atom_count"],
        "selected_conformer_id": int(selected_id),
        "conformer_energy": energy,  # 力场能量（kcal/mol），非结合能
        "force_field_used": used_ff,
        "preparation": prep.model_dump(),
        "descriptors": descriptors,
        "preparation_warnings": warnings,
        "tools": {"meeko_version": meeko.__version__, "pdbqt_tool": meeko_tool},
    }
    (ligand_dir / "ligand_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return LigandResult(
        ligand_id=spec.ligand_id,
        status="SUCCESS",
        descriptors=descriptors,
        preparation_warnings=warnings,
        artifacts={
            "sdf": f"ligands/{spec.ligand_id}/ligand.sdf",
            "pdb": f"ligands/{spec.ligand_id}/ligand.pdb",
            "pdbqt": f"ligands/{spec.ligand_id}/ligand.pdbqt",
            "metadata": f"ligands/{spec.ligand_id}/ligand_metadata.json",
        },
        provenance={
            "meeko_version": meeko.__version__,
            "pdbqt_tool": meeko_tool,
            "force_field_used": used_ff,
            "conformer_energy": energy,
        },
    )
