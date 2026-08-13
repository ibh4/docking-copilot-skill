"""结果解释服务：生成 Markdown 报告。

固定科学措辞（提示词 5）：
- Vina affinity 是经验打分与构象搜索结果，不是实验结合自由能、Kd、Ki、
  IC50 或药效；
- 更负通常表示在当前设置下更有利；
- 只有同受体、同准备流程、同 box、同参数下的分数才可相对比较；
- 多 pose 分数接近提示构象不确定性；
- ligand_efficiency = -best_affinity / heavy_atom_count，仅作辅助指标。
"""

from __future__ import annotations

LIMITATIONS_SECTION = """## 结果解释与局限性（固定措辞）

- AutoDock Vina 的 affinity 是**经验打分函数与构象搜索的结果**，
  不能直接等同于实验结合自由能、Kd、Ki、IC50 或任何药效结论。
- 在当前参数设置下，分数**更负通常表示更有利**，但这是相对趋势而非绝对量。
- 不同受体、不同准备流程、不同 box、不同质子化状态或不同参数之间的分数
  **不可横向比较**；最可靠的比较是在相同受体、相同准备流程、相同 box 与
  相同参数下比较候选分子。
- 若同一分子的多个 pose 分数接近，提示**构象不确定性**较高，
  最优 pose 不一定代表真实结合模式。
- ligand_efficiency = -best_affinity / heavy_atom_count，仅作为
  **辅助排序指标**，不能替代实验验证。
- 若结果依赖超大搜索盒或过低 exhaustiveness，可靠性风险增加。
"""


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def build_result_markdown(
    job_id: str,
    job_name: str,
    results: list[dict],
    box: dict,
    parameters: dict,
    comparison: dict | None,
    warnings: list[str],
) -> str:
    """组装 reports/result.md。results 为 LigandResult.model_dump() 列表。"""
    lines: list[str] = []
    lines.append(f"# DockingCopilot Skill 对接结果：{job_name}")
    lines.append("")
    lines.append(f"- job_id: `{job_id}`")
    lines.append(f"- 状态：{'包含失败分子' if any(r['status'] == 'FAILED' for r in results) else 'SUCCESS'}")
    lines.append(
        f"- 搜索盒：mode={box.get('mode')}, center={box.get('center')} Å, "
        f"size={box.get('size')} Å"
    )
    lines.append(
        f"- Vina 参数：exhaustiveness={parameters.get('exhaustiveness')}, "
        f"num_modes={parameters.get('num_modes')}, "
        f"energy_range={parameters.get('energy_range')} kcal/mol, "
        f"cpu={parameters.get('cpu')}, seed={parameters.get('seed')}"
    )
    lines.append("")
    lines.append("## 分子结果")
    lines.append("")
    lines.append(
        "| ligand | status | best affinity (kcal/mol) | ligand efficiency | poses |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    for res in results:
        lines.append(
            f"| {res['ligand_id']} | {res['status']} | "
            f"{_fmt(res.get('best_affinity_kcal_mol'))} | "
            f"{_fmt(res.get('ligand_efficiency'), 4)} | "
            f"{len(res.get('poses', []))} |"
        )
    lines.append("")

    for res in results:
        lines.append(f"### {res['ligand_id']}")
        if res["status"] == "FAILED":
            err = res.get("structured_error") or {}
            lines.append(f"- 失败：[{err.get('error_code')}] {err.get('message')}")
            lines.append("")
            continue
        desc = res.get("descriptors", {})
        lines.append(
            f"- descriptors: MolWt={_fmt(desc.get('MolWt'), 1)} g/mol, "
            f"LogP={_fmt(desc.get('LogP'))}, TPSA={_fmt(desc.get('TPSA'), 1)} Å², "
            f"HBD={desc.get('HBD')}, HBA={desc.get('HBA')}, "
            f"rotatable_bonds={desc.get('rotatable_bonds')}"
        )
        poses = res.get("poses", [])
        if len(poses) >= 2:
            gap = poses[1]["affinity_kcal_mol"] - poses[0]["affinity_kcal_mol"]
            if gap < 0.5:
                lines.append(
                    f"- top-2 pose 能量差 {gap:.3f} kcal/mol < 0.5："
                    "构象不确定性较高，最优 pose 不应被过度解读。"
                )
        if res.get("preparation_warnings"):
            lines.append(
                "- 准备阶段警告：" + "; ".join(res["preparation_warnings"])
            )
        lines.append("")

    if comparison and comparison.get("metrics"):
        lines.append("## 批次内相对比较（展示性指标）")
        lines.append("")
        lines.append(comparison.get("normalization_method", ""))
        lines.append("")

    if warnings:
        lines.append("## 任务级警告")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append(LIMITATIONS_SECTION)
    return "\n".join(lines)
