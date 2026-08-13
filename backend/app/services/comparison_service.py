"""批次内相对比较服务（展示性相对指标，公式透明）。

原则（提示词 5）：
- 不捏造绝对"对接能力"；所有综合分数标注为 Relative Docking Profile；
- 公式写入返回的 normalization_method 字段；
- 单分子时不虚构比较分，只给原始指标。
"""

from __future__ import annotations

from app.schemas import ComparisonContext, ComparisonOutput

#: 目标区间（分段函数拐点）
MOLWT_IDEAL_MAX = 500.0   # g/mol
MOLWT_SOFT_MAX = 600.0
LOGP_IDEAL_MIN, LOGP_IDEAL_MAX = -1.0, 5.0
LOGP_SOFT_MIN, LOGP_SOFT_MAX = -3.0, 7.0
TPSA_IDEAL_MAX = 140.0    # Å²
TPSA_SOFT_MAX = 180.0
ROTBOND_IDEAL_MAX = 7
ROTBOND_SOFT_MAX = 12

NORMALIZATION_METHOD = (
    "Relative Docking Profile (display-only, in-batch): "
    "relative_affinity = (worst_affinity - affinity) / (worst_affinity - "
    "best_affinity) in [0,1], higher = more favorable (affinity in kcal/mol, "
    "more negative is better); "
    "ligand_efficiency = -best_affinity / heavy_atom_count (kcal/mol per heavy "
    "atom, auxiliary only); "
    "pose_score_gap = pose2.affinity - pose1.affinity (kcal/mol; >=1.0 gives "
    "pose_consistency 1.0, linearly down to 0 at 0.0); "
    "molwt_fit = 1.0 if MolWt<=500, linearly to 0 at 600 (g/mol); "
    "logp_fit = 1.0 within [-1,5], linearly to 0 at -3/7; "
    "tpsa_fit = 1.0 if TPSA<=140, linearly to 0 at 180 (A^2); "
    "flexibility_fit = 1.0 if rotatable_bonds<=7, linearly to 0 at 12; "
    "preparation_quality = max(0, 1 - 0.1 * num_preparation_warnings); "
    "composite_display_score = 0.4*relative_affinity + 0.2*pose_consistency + "
    "0.2*ligand_efficiency_rank_norm + 0.2*preparation_quality, "
    "only computed for batches with >=2 successful ligands."
)


def _ramp_descending(value: float, ideal_max: float, soft_max: float) -> float:
    """value<=ideal_max → 1.0；线性降到 soft_max 处为 0。"""
    if value <= ideal_max:
        return 1.0
    if value >= soft_max:
        return 0.0
    return (soft_max - value) / (soft_max - ideal_max)


def _ramp_window(value: float, lo: float, hi: float, soft_lo: float, soft_hi: float) -> float:
    """[lo,hi] 内为 1.0，向 soft_lo/soft_hi 线性降到 0。"""
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return max(0.0, (value - soft_lo) / (lo - soft_lo)) if value > soft_lo else 0.0
    return max(0.0, (soft_hi - value) / (soft_hi - hi)) if value < soft_hi else 0.0


def molwt_fit(molwt: float) -> float:
    return _ramp_descending(molwt, MOLWT_IDEAL_MAX, MOLWT_SOFT_MAX)


def logp_fit(logp: float) -> float:
    return _ramp_window(logp, LOGP_IDEAL_MIN, LOGP_IDEAL_MAX, LOGP_SOFT_MIN, LOGP_SOFT_MAX)


def tpsa_fit(tpsa: float) -> float:
    return _ramp_descending(tpsa, TPSA_IDEAL_MAX, TPSA_SOFT_MAX)


def flexibility_fit(rotatable_bonds: int) -> float:
    return _ramp_descending(float(rotatable_bonds), ROTBOND_IDEAL_MAX, ROTBOND_SOFT_MAX)


def pose_consistency(pose_score_gap: float) -> float:
    """top-2 pose 能量差 >=1.0 kcal/mol 视为区分度良好。"""
    return min(1.0, max(0.0, pose_score_gap))


def compare_in_batch(
    results: list,
    context: ComparisonContext | None = None,
    job_id: str = "",
) -> ComparisonOutput:
    """results 为 LigandResult 列表（可含 FAILED，仅 SUCCESS 参与比较）。"""
    context = context or ComparisonContext()
    succeeded = [
        r for r in results
        if r.status == "SUCCESS" and r.best_affinity_kcal_mol is not None
    ]
    metrics: dict[str, dict] = {}
    for res in results:
        desc = res.descriptors or {}
        entry: dict = {
            "status": res.status,
            "best_affinity_kcal_mol": res.best_affinity_kcal_mol,
            "ligand_efficiency": res.ligand_efficiency,
        }
        if res.status == "SUCCESS":
            poses = res.poses
            gap = (
                poses[1].affinity_kcal_mol - poses[0].affinity_kcal_mol
                if len(poses) >= 2
                else None
            )
            entry.update(
                {
                    "pose_score_gap_kcal_mol": gap,
                    "pose_consistency": (
                        pose_consistency(gap) if gap is not None else 1.0
                    ),
                    "molwt_fit": molwt_fit(desc.get("MolWt", 0.0)),
                    "logp_fit": logp_fit(desc.get("LogP", 0.0)),
                    "tpsa_fit": tpsa_fit(desc.get("TPSA", 0.0)),
                    "flexibility_fit": flexibility_fit(
                        desc.get("rotatable_bonds", 0)
                    ),
                    "preparation_quality": max(
                        0.0, 1.0 - 0.1 * len(res.preparation_warnings)
                    ),
                }
            )
        metrics[res.ligand_id] = entry

    # 批次级归一化（>=2 个成功分子才有相对排序；单分子不虚构比较分）
    if len(succeeded) >= 2:
        affinities = [r.best_affinity_kcal_mol for r in succeeded]
        best, worst = min(affinities), max(affinities)
        span = (worst - best) or 1.0
        efficiencies = [r.ligand_efficiency or 0.0 for r in succeeded]
        eff_best, eff_worst = max(efficiencies), min(efficiencies)
        eff_span = (eff_best - eff_worst) or 1.0
        ranked = sorted(
            succeeded, key=lambda r: (r.best_affinity_kcal_mol or 0.0)
        )
        rank_of = {r.ligand_id: i + 1 for i, r in enumerate(ranked)}
        for res in succeeded:
            entry = metrics[res.ligand_id]
            rel_aff = (worst - (res.best_affinity_kcal_mol or 0.0)) / span
            eff_norm = ((res.ligand_efficiency or 0.0) - eff_worst) / eff_span
            composite = (
                0.4 * rel_aff
                + 0.2 * entry["pose_consistency"]
                + 0.2 * eff_norm
                + 0.2 * entry["preparation_quality"]
            )
            entry.update(
                {
                    "relative_affinity": round(rel_aff, 4),
                    "ligand_efficiency_rank_norm": round(eff_norm, 4),
                    "in_batch_rank": rank_of[res.ligand_id],
                    "composite_display_score": round(composite, 4),
                }
            )
    elif len(succeeded) == 1:
        metrics[succeeded[0].ligand_id]["note"] = (
            "single successful ligand: no in-batch comparison score computed"
        )

    return ComparisonOutput(
        job_id=job_id,
        context=context,
        ligand_ids=[r.ligand_id for r in results],
        metrics=metrics,
        normalization_method=NORMALIZATION_METHOD,
    )
