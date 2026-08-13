"""报告产物落盘服务：reports/result.json 与 reports/comparison.csv。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.schemas import ComparisonOutput, DockingOutput

#: comparison.csv 中每个分子导出的列（缺失值留空）
CSV_COLUMNS = [
    "ligand_id",
    "status",
    "best_affinity_kcal_mol",
    "ligand_efficiency",
    "pose_score_gap_kcal_mol",
    "pose_consistency",
    "relative_affinity",
    "in_batch_rank",
    "composite_display_score",
    "molwt_fit",
    "logp_fit",
    "tpsa_fit",
    "flexibility_fit",
    "preparation_quality",
]


def write_result_json(output: DockingOutput, reports_dir: Path) -> Path:
    """写 reports/result.json（DockingOutput 完整序列化）。"""
    target = reports_dir / "result.json"
    target.write_text(
        json.dumps(output.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return target


def write_comparison_csv(
    comparison: ComparisonOutput, reports_dir: Path
) -> Path:
    """写 reports/comparison.csv（每行一个分子，列见 CSV_COLUMNS）。"""
    target = reports_dir / "comparison.csv"
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for ligand_id in comparison.ligand_ids:
            entry = comparison.metrics.get(ligand_id, {})
            writer.writerow(
                [ligand_id]
                + [
                    entry.get(col, "") if entry.get(col) is not None else ""
                    for col in CSV_COLUMNS[1:]
                ]
            )
    return target
