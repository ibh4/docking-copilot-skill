#!/usr/bin/env python3
"""可复现示例运行入口（Phase 1：真实对接闭环）。

运行内容（G1 验收）：
1. examples/inputs/single_ligand.json —— 真实 AutoDock Vina 对接
   （exhaustiveness=8, cpu=4, seed=42），产物写入 outputs/<job_id>/；
2. examples/inputs/invalid_smiles.json —— 必须返回结构化错误
   error_code=INVALID_SMILES（进程退出码非零，但输出合法 JSON）。

用法：
    conda run -n dockskill python scripts/run_example.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.schemas import DockingInput  # noqa: E402
from app.workflow.runner import run_job  # noqa: E402

EXAMPLES = PROJECT_ROOT / "examples" / "inputs"


def _print_artifacts(job_dir: Path) -> None:
    for rel in (
        "manifest.json",
        "reports/result.json",
        "reports/result.md",
        "reports/comparison.csv",
        "bundle.zip",
    ):
        target = job_dir / rel
        marker = "OK" if target.is_file() and target.stat().st_size > 0 else "MISSING"
        print(f"  [{marker}] {target}")


def run_single_ligand() -> bool:
    """示例 1：单分子真实对接。"""
    data = json.loads((EXAMPLES / "single_ligand.json").read_text(encoding="utf-8"))
    docking_input = DockingInput.model_validate(data)
    outcome = run_job(docking_input)
    print(f"\n=== example: single_ligand ===")
    print(f"job_id: {outcome.job_id}")
    print(f"state:  {outcome.state.value}")
    print(f"job dir: {outcome.job_dir}")
    if outcome.state.value != "SUCCESS" or outcome.output is None:
        print(json.dumps(
            (outcome.structured_error or outcome.output.structured_error).model_dump(),
            ensure_ascii=False, indent=2,
        ))
        return False
    result = outcome.output.results[0]
    print(f"best_affinity_kcal_mol: {result.best_affinity_kcal_mol}")
    print(f"ligand_efficiency:      {result.ligand_efficiency}")
    print(f"poses: {len(result.poses)}")
    print("artifacts:")
    _print_artifacts(outcome.job_dir)
    manifest = json.loads((outcome.job_dir / "manifest.json").read_text(encoding="utf-8"))
    print(
        "manifest: "
        f"seed={manifest['random_seed']} "
        f"vina={manifest['vina_version']} "
        f"rdkit={manifest['rdkit_version']} "
        f"meeko={manifest['meeko_version']} "
        f"runtime={manifest['runtime_seconds']}s"
    )
    return True


def run_invalid_smiles() -> bool:
    """示例 2：非法 SMILES 必须返回 INVALID_SMILES 结构化错误。"""
    data = json.loads((EXAMPLES / "invalid_smiles.json").read_text(encoding="utf-8"))
    docking_input = DockingInput.model_validate(data)
    outcome = run_job(docking_input)
    error = outcome.structured_error
    payload = error.model_dump() if error else {"error": "unexpected success"}
    print(f"\n=== example: invalid_smiles ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"job dir: {outcome.job_dir}")
    return bool(error) and error.error_code == "INVALID_SMILES"


def main() -> int:
    single_ok = run_single_ligand()
    invalid_ok = run_invalid_smiles()
    print("\n=== summary ===")
    print(f"single_ligand docking:  {'PASS' if single_ok else 'FAIL'}")
    print(f"invalid_smiles error:   {'PASS' if invalid_ok else 'FAIL'}")
    if single_ok and invalid_ok:
        print("RUN_EXAMPLE_PASS")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
