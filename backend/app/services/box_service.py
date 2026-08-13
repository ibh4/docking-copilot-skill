"""docking 搜索盒生成与校验（四模式）。

模式：explicit / reference_ligand / residue_list / whole_receptor。
所有几何量单位 Å；约束阈值引用 app.config。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from app import config
from app.schemas import DockingBox, ErrorCode


class BoxError(Exception):
    """搜索盒配置/校验的受控错误。"""

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


@dataclass
class BoxResult:
    """最终使用的搜索盒（Å）。"""

    mode: str
    center: list[float]
    size: list[float]
    volume_angstrom3: float
    units: str = "angstrom"
    warnings: list[str] = field(default_factory=list)


def _residue_matches(entity: dict, resid: str) -> bool:
    """匹配 'LIG' / 'A/1437' / 'A/LIG1437' 等残基标识。"""
    resid = resid.strip()
    if resid == entity["resname"]:
        return True
    if "/" in resid:
        chain, rest = resid.split("/", 1)
        if chain != entity["chain"]:
            return False
        if rest == str(entity["resid"]):
            return True
        return rest == f"{entity['resname']}{entity['resid']}"
    return resid == f"{entity['resname']}{entity['resid']}"


def _entity_coords(report: dict, entity: dict) -> np.ndarray:
    """从报告结构中取指定异源实体的原子坐标。"""
    model = next(iter(report["structure"]))
    chain = model[entity["chain"]]
    for residue in chain.get_unpacked_list():
        if (
            residue.resname.strip() == entity["resname"]
            and residue.get_id()[1] == entity["resid"]
        ):
            return np.array([a.coord for a in residue.get_atoms()], dtype=float)
    raise BoxError(
        ErrorCode.INVALID_BOX,
        f"residue {entity['chain']}/{entity['resname']}{entity['resid']} "
        "not found in structure",
    )


def _standard_residue_coords(report: dict, resid: str) -> np.ndarray:
    """按 'A/585' 或 '585' 取标准残基坐标。"""
    resid = resid.strip()
    chain_id: str | None = None
    if "/" in resid:
        chain_id, number = resid.split("/", 1)
    else:
        number = resid
    try:
        res_num = int(number)
    except ValueError as exc:
        raise BoxError(
            ErrorCode.INVALID_BOX, f"invalid residue id: {resid!r}"
        ) from exc
    model = next(iter(report["structure"]))
    chains = [model[chain_id]] if chain_id else list(model)
    coords: list[np.ndarray] = []
    for chain in chains:
        for residue in chain.get_unpacked_list():
            if residue.get_id()[0] == " " and residue.get_id()[1] == res_num:
                coords.append(
                    np.array([a.coord for a in residue.get_atoms()], dtype=float)
                )
    if not coords:
        raise BoxError(
            ErrorCode.INVALID_BOX,
            f"residue {resid!r} not found among standard residues",
            suggested_actions=["use format 'CHAIN/resnum', e.g. 'A/585'"],
        )
    return np.concatenate(coords)


def _check_final_box(
    center: list[float], size: list[float], warnings: list[str]
) -> float:
    """单边范围与体积上限校验；返回体积。"""
    for edge in size:
        if not math.isfinite(edge) or edge <= 0:
            raise BoxError(ErrorCode.INVALID_BOX, f"box size must be positive: {size}")
    if any(edge > config.BOX_EDGE_MAX for edge in size):
        raise BoxError(
            ErrorCode.BOX_TOO_LARGE,
            f"computed box edge exceeds {config.BOX_EDGE_MAX} A: "
            f"{[round(s, 2) for s in size]}",
            suggested_actions=[
                "reduce padding_angstrom",
                "select fewer residues",
            ],
        )
    if any(edge < config.BOX_EDGE_MIN for edge in size):
        warnings.append(
            f"computed box edge below {config.BOX_EDGE_MIN} A; "
            "search space may be too tight"
        )
    volume = float(size[0] * size[1] * size[2])
    if volume > config.BOX_VOLUME_MAX:
        raise BoxError(
            ErrorCode.BOX_TOO_LARGE,
            f"box volume {volume:.0f} A^3 exceeds limit {config.BOX_VOLUME_MAX:.0f}",
        )
    return volume


def build_box(box: DockingBox, report: dict) -> BoxResult:
    """根据模式生成并校验搜索盒。

    explicit 模式额外校验与受体包围盒的交集（完全在外→BOX_OUTSIDE_RECEPTOR）。
    """
    warnings: list[str] = []
    bb_min, bb_max = report["bounding_box"]
    bb_min = np.asarray(bb_min, dtype=float)
    bb_max = np.asarray(bb_max, dtype=float)

    if box.mode == "explicit":
        assert box.center is not None and box.size is not None
        center, size = list(box.center), list(box.size)
        lo = np.asarray(center) - np.asarray(size) / 2.0
        hi = np.asarray(center) + np.asarray(size) / 2.0
        inter = np.minimum(hi, bb_max) - np.maximum(lo, bb_min)
        if (inter <= 0).any():
            raise BoxError(
                ErrorCode.BOX_OUTSIDE_RECEPTOR,
                "explicit box does not intersect the receptor bounding box",
                details={
                    "box_center": center,
                    "receptor_bbox_min": bb_min.tolist(),
                    "receptor_bbox_max": bb_max.tolist(),
                },
                suggested_actions=[
                    "move the box center toward the receptor bounding box"
                ],
            )
        box_vol = float(size[0] * size[1] * size[2])
        overlap_vol = float(np.prod(np.clip(inter, 0.0, None)))
        if box_vol > 0 and overlap_vol / box_vol < 0.1:
            warnings.append(
                "box overlaps <10% with the receptor bounding box; "
                "it sits near the receptor edge"
            )
    elif box.mode == "reference_ligand":
        candidates = [
            e for e in report["hetero_entities"]
            if e["type"] in ("ligand_candidate", "cofactor")
            and box.reference_ligand_resid
            and _residue_matches(e, box.reference_ligand_resid)
        ]
        if not candidates:
            raise BoxError(
                ErrorCode.INVALID_BOX,
                f"reference ligand {box.reference_ligand_resid!r} not found "
                "in the analyzed structure (HETATM entities)",
                details={
                    "available": [
                        f"{e['chain']}/{e['resname']}{e['resid']}"
                        for e in report["detected_ligands"]
                    ]
                },
            )
        coords = _entity_coords(report, candidates[0])
        padding = min(box.padding_angstrom, 12.0)
        center = coords.mean(axis=0).tolist()
        size = (
            np.clip(coords.max(axis=0) - coords.min(axis=0), 0.0, None)
            + 2.0 * padding
        ).tolist()
    elif box.mode == "residue_list":
        assert box.residue_ids
        chunks = [_standard_residue_coords(report, rid) for rid in box.residue_ids]
        coords = np.concatenate(chunks)
        padding = min(box.padding_angstrom, 12.0)
        center = coords.mean(axis=0).tolist()
        size = (
            np.clip(coords.max(axis=0) - coords.min(axis=0), 0.0, None)
            + 2.0 * padding
        ).tolist()
    else:  # whole_receptor
        warnings.append(
            "whole_receptor box mode is only intended for small test systems; "
            "results may have reduced reliability due to the large search space"
        )
        padding = min(box.padding_angstrom, 12.0)
        center = ((bb_min + bb_max) / 2.0).tolist()
        size = (bb_max - bb_min + 2.0 * padding).tolist()

    volume = _check_final_box(center, size, warnings)
    return BoxResult(
        mode=box.mode,
        center=[round(c, 3) for c in center],
        size=[round(s, 3) for s in size],
        volume_angstrom3=round(volume, 1),
        warnings=warnings,
    )
