"""受体准备服务：结构分析 → 按 ReceptorConfig 清洗 → Meeko 生成 receptor.pdbqt。

原则（提示词 4）：删水/删异源原子等决策必须可配置、可解释、可追踪；
原始 PDB 保留，输出清洗后 PDB、PDBQT 与准备报告（含被移除/保留实体列表）。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from Bio.PDB import PDBIO, PDBParser
from Bio.PDB.PDBExceptions import PDBConstructionException

from app.schemas import ErrorCode, ReceptorConfig

#: 水残基名
WATER_RESIDUES = {"HOH", "WAT", "DOD", "TIP3", "H2O", "OH2"}

#: 常见金属离子
METAL_IONS = {
    "ZN", "MG", "CA", "FE", "MN", "CU", "CO", "NI", "NA", "K", "HG", "CD", "PT",
}

#: 常见辅因子
COFACTORS = {
    "HEM", "NAD", "NAP", "FAD", "FMN", "ATP", "ADP", "AMP", "GTP", "SAM",
    "PLP", "COA", "HEC", "SF4", "ZN2",
}

#: 核酸残基名
NUCLEIC_RESIDUES = {
    "DA", "DT", "DC", "DG", "A", "U", "G", "C", "ADE", "URA", "GUA", "CYT",
}

#: 蛋白质骨架原子（CA-only 检测）
BACKBONE_ATOMS = {"N", "CA", "C", "O"}

#: residue_list / reference_ligand 模式的 padding 上限（Å）
MAX_PADDING = 12.0


class ReceptorError(Exception):
    """受体准备阶段的受控错误。"""

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
    for candidate in (basename, f"{basename}.py"):
        found = shutil.which(candidate)
        if found:
            return Path(found)
    return None


# ---------------------------------------------------------------------------
# 结构分析
# ---------------------------------------------------------------------------


def analyze_receptor(pdb_path: Path) -> dict:
    """解析 PDB 并产出结构报告（链/模型/altloc/缺失残基/异源实体等）。"""
    text = pdb_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ReceptorError(ErrorCode.INVALID_RECEPTOR, "PDB file is empty")

    parser = PDBParser(QUIET=True)
    try:
        structure = parser.get_structure("receptor", str(pdb_path))
    except PDBConstructionException as exc:
        raise ReceptorError(
            ErrorCode.INVALID_RECEPTOR,
            f"PDB parse failed: {exc}",
        ) from exc

    models = list(structure)
    if not models:
        raise ReceptorError(ErrorCode.INVALID_RECEPTOR, "PDB has no models")

    n_atoms = 0
    has_altloc = False
    chains: list[str] = []
    hetero_entities: list[dict] = []
    protein_residue_count = 0
    numeric_gaps: list[str] = []
    ca_only_residues = 0
    has_nucleic = False

    for model in models:
        for chain in model:
            chains.append(chain.id)
            numeric_ids: list[int] = []
            for residue in chain.get_unpacked_list():
                het_flag = residue.get_id()[0]
                resname = residue.resname.strip()
                atoms = residue.get_unpacked_list()
                if any(a.altloc not in (" ", "") for a in atoms):
                    has_altloc = True
                if het_flag == " ":
                    protein_residue_count += 1
                    numeric_ids.append(residue.get_id()[1])
                    names = {a.name for a in atoms}
                    if resname in NUCLEIC_RESIDUES:
                        has_nucleic = True
                    elif names and names <= BACKBONE_ATOMS:
                        ca_only_residues += 1
                elif het_flag == "W":
                    hetero_entities.append(
                        {"chain": chain.id, "resname": resname,
                         "resid": residue.get_id()[1], "type": "water",
                         "atom_count": len(atoms)}
                    )
                else:
                    entity_type = "other"
                    if resname in METAL_IONS:
                        entity_type = "metal"
                    elif resname in COFACTORS:
                        entity_type = "cofactor"
                    elif resname not in WATER_RESIDUES and resname not in NUCLEIC_RESIDUES:
                        entity_type = "ligand_candidate"
                    hetero_entities.append(
                        {"chain": chain.id, "resname": resname,
                         "resid": residue.get_id()[1], "type": entity_type,
                         "atom_count": len(atoms)}
                    )
            sorted_ids = sorted(numeric_ids)
            for prev, cur in zip(sorted_ids, sorted_ids[1:]):
                if cur - prev > 5:
                    numeric_gaps.append(
                        f"{chain.id}:{prev}->{cur} (gap {cur - prev - 1})"
                    )
        n_atoms += sum(1 for _ in model.get_atoms())
        break  # 只分析第一个 model（多模型在报告中提示）

    if protein_residue_count == 0 and not any(
        e["type"] == "ligand_candidate" for e in hetero_entities
    ):
        raise ReceptorError(
            ErrorCode.INVALID_RECEPTOR, "PDB contains no ATOM records"
        )

    return {
        "structure": structure,
        "num_models": len(models),
        "chains": chains,
        "atom_count": n_atoms,
        "residue_count": protein_residue_count,
        "has_altloc": has_altloc,
        "hetero_entities": hetero_entities,
        "waters": [e for e in hetero_entities if e["type"] == "water"],
        "metals": [e for e in hetero_entities if e["type"] == "metal"],
        "cofactors": [e for e in hetero_entities if e["type"] == "cofactor"],
        "detected_ligands": [
            e for e in hetero_entities if e["type"] == "ligand_candidate"
        ],
        "missing_residue_gaps": numeric_gaps,
        "ca_only_residues": ca_only_residues,
        "has_nucleic_acid": has_nucleic,
        "ca_only_backbone": protein_residue_count > 0
        and ca_only_residues == protein_residue_count,
    }


def bounding_box_from_report(report: dict) -> tuple[list[float], list[float]]:
    """从报告中第一个 model 的坐标计算受体包围盒 ((min_x..), (max_x..))。"""
    model = next(iter(report["structure"]))
    coords = np.array([a.coord for a in model.get_atoms()], dtype=float)
    return coords.min(axis=0).tolist(), coords.max(axis=0).tolist()


# ---------------------------------------------------------------------------
# 清洗
# ---------------------------------------------------------------------------


def _drop_altloc_low_occupancy(model) -> int:
    """每个残基内按原子名保留最高 occupancy 的 altloc；返回移除原子数。"""
    removed = 0
    for chain in model:
        for residue in chain.get_unpacked_list():
            groups: dict[tuple[str, str], list] = {}
            for atom in residue.get_unpacked_list():
                if atom.altloc in (" ", ""):
                    continue
                groups.setdefault((atom.name, atom.element), []).append(atom)
            for atoms in groups.values():
                keep = max(atoms, key=lambda a: (a.occupancy, -ord(a.altloc)))
                for atom in atoms:
                    if atom is not keep:
                        residue.detach_child(atom.get_id())
                        removed += 1
    return removed


def clean_receptor(
    report: dict, cfg: ReceptorConfig, out_pdb: Path
) -> tuple[dict, list[str]]:
    """按配置清洗结构并写出 clean PDB；返回 (清洗摘要, warnings)。"""
    warnings: list[str] = []
    structure = report["structure"]

    if report["num_models"] > 1:
        warnings.append(
            f"structure has {report['num_models']} models; using model 1 only"
        )
    model = structure[0]

    available = {c.id for c in model}
    selected = cfg.selected_chains
    if selected:
        missing = [c for c in selected if c not in available]
        if missing:
            raise ReceptorError(
                ErrorCode.CHAIN_NOT_FOUND,
                f"selected chain(s) not found in structure: {missing}",
                details={"available_chains": sorted(available)},
                suggested_actions=["choose from available chains"],
            )
    keep_chains = set(selected) if selected else available

    removed: dict[str, list[str]] = {
        "chains": [], "waters": [], "metals": [],
        "cofactors": [], "ligands": [], "other_hetero": [],
    }
    kept: dict[str, list[str]] = {"chains": sorted(keep_chains), "hetero": []}

    for chain in list(model):
        if chain.id not in keep_chains:
            removed["chains"].append(chain.id)
            model.detach_child(chain.id)
            continue
        for residue in list(chain.get_unpacked_list()):
            het_flag = residue.get_id()[0]
            resname = residue.resname.strip()
            label = f"{chain.id}/{resname}{residue.get_id()[1]}"
            if het_flag == " ":
                continue  # 标准残基保留
            if het_flag == "W":
                if cfg.keep_waters:
                    kept["hetero"].append(f"{label} (water)")
                else:
                    removed["waters"].append(label)
                    chain.detach_child(residue.get_id())
                continue
            if resname in METAL_IONS:
                if resname in cfg.keep_metals:
                    kept["hetero"].append(f"{label} (metal)")
                else:
                    removed["metals"].append(label)
                    chain.detach_child(residue.get_id())
                continue
            if resname in COFACTORS:
                if resname in cfg.keep_cofactors:
                    kept["hetero"].append(f"{label} (cofactor)")
                else:
                    removed["cofactors"].append(label)
                    chain.detach_child(residue.get_id())
                continue
            # 其余 HETATM：原始共晶配体或其他异源
            if cfg.remove_original_ligands:
                removed["ligands"].append(label)
            else:
                kept["hetero"].append(f"{label} (hetero)")
                continue
            chain.detach_child(residue.get_id())

    if cfg.alternate_location_policy == "highest_occupancy" and report["has_altloc"]:
        dropped = _drop_altloc_low_occupancy(model)
        if dropped:
            warnings.append(
                f"removed {dropped} lower-occupancy alternate-location atoms"
            )

    if report["missing_residue_gaps"]:
        message = (
            "possible missing residues (sequence-number gaps): "
            + "; ".join(report["missing_residue_gaps"][:10])
        )
        warnings.append(message)
        if cfg.missing_residue_policy == "error":
            raise ReceptorError(
                ErrorCode.INVALID_RECEPTOR, message, recoverable=True,
                suggested_actions=["set missing_residue_policy to 'warn'"],
            )

    if report["ca_only_backbone"]:
        warnings.append("structure appears to be C-alpha-only (backbone trace)")
    if report["has_nucleic_acid"]:
        warnings.append("nucleic acid residues detected in structure")

    remaining_atoms = sum(1 for _ in model.get_atoms())
    if remaining_atoms == 0:
        raise ReceptorError(
            ErrorCode.INVALID_RECEPTOR,
            "no atoms remain after cleaning (check chain selection)",
        )

    io = PDBIO()
    io.set_structure(model)
    io.save(str(out_pdb))
    summary = {"removed": removed, "kept": kept, "remaining_atoms": remaining_atoms}
    return summary, warnings


def write_preparation_report(
    report: dict, summary: dict, warnings: list[str], out_json: Path
) -> None:
    """写出受体准备报告 JSON（分析结果 + 被移除/保留实体 + warnings）。"""
    serializable = {
        k: v for k, v in report.items() if k != "structure"
    }
    serializable["bounding_box"] = bounding_box_from_report(report)
    serializable["cleaning"] = summary
    serializable["warnings"] = warnings
    out_json.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# receptor.pdbqt（Meeko 唯一入口）
# ---------------------------------------------------------------------------


def prepare_receptor_pdbqt(
    clean_pdb: Path, out_pdbqt: Path
) -> tuple[str, list[str]]:
    """生成 receptor.pdbqt；返回 (所用工具描述, warnings)。

    meeko 0.7+ 的 ``-i`` 依赖 ProDy，此处使用 ``--read_pdb``（RDKit 读取）。
    首次严格模式失败时受控回退 ``--allow_bad_res``（删除无法匹配模板的
    残基）并记录 warning，禁止静默；工具不可用→RECEPTOR_PREPARATION_FAILED。
    """
    warnings: list[str] = []
    cli = _find_meeko_cli("mk_prepare_receptor")
    if cli is None:
        raise ReceptorError(
            ErrorCode.RECEPTOR_PREPARATION_FAILED,
            "Meeko receptor preparation tool not available "
            "(mk_prepare_receptor / mk_prepare_receptor.py not found)",
            suggested_actions=["install meeko into the environment"],
        )
    base_command = [str(cli), "--read_pdb", str(clean_pdb), "-p", str(out_pdbqt)]

    def _run(command: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=300, check=False,
        )

    result = _run(base_command)
    if result.returncode != 0 or not out_pdbqt.is_file():
        # 受控回退：允许丢弃无法匹配模板的残基（截断/缺失结构常见）
        out_pdbqt.unlink(missing_ok=True)
        retry_command = base_command + ["--allow_bad_res"]
        retry = _run(retry_command)
        if retry.returncode == 0 and out_pdbqt.is_file():
            text = out_pdbqt.read_text(encoding="utf-8")
            if "ATOM" in text:
                warnings.append(
                    "some residues did not match meeko templates and were "
                    "removed (--allow_bad_res); see stderr log for the list"
                )
                return f"meeko cli ({cli.name})", warnings
        raise ReceptorError(
            ErrorCode.RECEPTOR_PREPARATION_FAILED,
            "mk_prepare_receptor CLI failed (strict and --allow_bad_res)",
            details={
                "returncode": retry.returncode,
                "stderr": (result.stderr + "\n" + retry.stderr)[-2000:],
            },
        )
    text = out_pdbqt.read_text(encoding="utf-8")
    if "ATOM" not in text:
        raise ReceptorError(
            ErrorCode.RECEPTOR_PREPARATION_FAILED,
            "receptor PDBQT contains no ATOM records",
        )
    return f"meeko cli ({cli.name})", warnings
