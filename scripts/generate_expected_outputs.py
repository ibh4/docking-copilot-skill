#!/usr/bin/env python3
"""生成 examples/expected_outputs/result_summary.json：
从一次真实成功的运行（outputs/ 下最新 SUCCESS job）提取结果摘要副本。
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOB_ID = "20260805-035906_multiple_ligands_demo"
JOB_DIR = PROJECT_ROOT / "outputs" / JOB_ID
OUT_PATH = PROJECT_ROOT / "examples" / "expected_outputs" / "result_summary.json"


def main() -> int:
    result = json.loads((JOB_DIR / "reports" / "result.json").read_text(encoding="utf-8"))
    manifest = json.loads((JOB_DIR / "manifest.json").read_text(encoding="utf-8"))

    summary = {
        "_note": (
            "真实运行的 result.json 摘要副本（非手写模拟数据）。"
            "job_id 与时间戳因运行而异；分数在固定 seed=42 下可复现（±0.01 kcal/mol）。"
        ),
        "source": {
            "job_id": manifest.get("job_id"),
            "input": "examples/inputs/multiple_ligands.json",
            "input_sha256": manifest.get("input_sha256"),
            "receptor_sha256": manifest.get("receptor_sha256"),
            "vina_version": manifest.get("vina_version"),
            "rdkit_version": manifest.get("rdkit_version"),
            "random_seed": manifest.get("random_seed"),
            "status": manifest.get("status"),
        },
        "results": [],
    }
    for res in result.get("results", []):
        summary["results"].append(
            {
                "ligand_id": res.get("ligand_id"),
                "status": res.get("status"),
                "best_affinity_kcal_mol": res.get("best_affinity_kcal_mol"),
                "num_poses": len(res.get("poses", [])),
                "top3_poses": [
                    {
                        "rank": p.get("rank"),
                        "affinity_kcal_mol": p.get("affinity_kcal_mol"),
                        "rmsd_lb": p.get("rmsd_lb"),
                        "rmsd_ub": p.get("rmsd_ub"),
                    }
                    for p in res.get("poses", [])[:3]
                ],
                "descriptors": res.get("descriptors"),
            }
        )

    OUT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"written: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
