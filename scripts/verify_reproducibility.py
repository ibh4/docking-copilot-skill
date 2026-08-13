#!/usr/bin/env python3
"""可复现性验证（提示词 5）：同一输入固定 seed 双跑 run_job 并比对。

比对内容：
1. manifest 哈希：input_sha256 / receptor_sha256 / ligand_sha256 与确定性
   产物（ligand.pdbqt、receptor 清洗/PDBQT、pose pdbqt）的 artifact_sha256；
2. 产物目录结构（相对路径集合）一致；
3. 分数一致：best_affinity 与逐 pose affinity 容差 ±0.01 kcal/mol；
4. 参数与 seed 一致。

输出：reports/reproducibility_report.md 与 reports/reproducibility_report.json；
全部通过时打印唯一标记 REPRODUCIBILITY_PASS。

用法：
    conda run -n dockskill python scripts/verify_reproducibility.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.schemas import DockingInput  # noqa: E402
from app.workflow.runner import run_job  # noqa: E402

INPUT_JSON = PROJECT_ROOT / "examples" / "inputs" / "single_ligand.json"
REPORTS_DIR = PROJECT_ROOT / "reports"
AFFINITY_TOLERANCE = 0.01  # kcal/mol

#: manifest.artifact_sha256 中随时间戳/job_id 变化的条目（不参与哈希比对）
NON_DETERMINISTIC_ARTIFACTS = (
    "reports/result.json",
    "reports/result.md",
    "reports/comparison.csv",
)


def _relative_structure(job_dir: Path) -> set[str]:
    """job 目录内全部文件的相对路径集合（规范化结构比对）。"""
    return {
        str(p.relative_to(job_dir))
        for p in sorted(job_dir.rglob("*"))
        if p.is_file()
    }


def _deterministic_artifact_hashes(manifest: dict) -> dict:
    return {
        rel: sha
        for rel, sha in manifest.get("artifact_sha256", {}).items()
        if rel not in NON_DETERMINISTIC_ARTIFACTS
    }


def run_once(tag: str) -> dict:
    payload = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    docking_input = DockingInput.model_validate(payload)
    outcome = run_job(docking_input)
    if outcome.state.value != "SUCCESS" or outcome.output is None:
        error = outcome.structured_error
        raise SystemExit(
            f"run {tag} failed: "
            f"{error.model_dump() if error else 'unknown error'}"
        )
    manifest = json.loads(
        (outcome.job_dir / "manifest.json").read_text(encoding="utf-8")
    )
    return {
        "tag": tag,
        "job_id": outcome.job_id,
        "job_dir": outcome.job_dir,
        "manifest": manifest,
        "output": outcome.output,
        "structure": _relative_structure(outcome.job_dir),
    }


def compare(run_a: dict, run_b: dict) -> tuple[bool, dict, list[str]]:
    """返回 (是否全部通过, 详情 dict, 问题列表)。"""
    problems: list[str] = []
    details: dict = {"checks": []}

    def check(name: str, passed: bool, info: str) -> None:
        details["checks"].append(
            {"name": name, "passed": passed, "info": info}
        )
        if not passed:
            problems.append(f"{name}: {info}")

    ma, mb = run_a["manifest"], run_b["manifest"]

    # 1. 输入/受体/配体哈希
    for key in ("input_sha256", "receptor_sha256"):
        check(
            key,
            ma.get(key) == mb.get(key) and ma.get(key) is not None,
            f"{ma.get(key)} vs {mb.get(key)}",
        )
    check(
        "ligand_sha256",
        ma.get("ligand_sha256") == mb.get("ligand_sha256"),
        f"{ma.get('ligand_sha256')} vs {mb.get('ligand_sha256')}",
    )

    # 2. 确定性产物哈希
    ha = _deterministic_artifact_hashes(ma)
    hb = _deterministic_artifact_hashes(mb)
    same_keys = set(ha) == set(hb)
    check(
        "artifact_sha256_keys",
        same_keys,
        f"run_a={sorted(ha)} run_b={sorted(hb)}" if not same_keys else
        f"{len(ha)} deterministic artifacts compared",
    )
    mismatched = [k for k in ha if k in hb and ha[k] != hb[k]]
    check(
        "artifact_sha256_values",
        not mismatched,
        f"hash mismatch: {mismatched}" if mismatched else
        "all deterministic artifact hashes identical",
    )

    # 3. 产物结构
    check(
        "artifact_structure",
        run_a["structure"] == run_b["structure"],
        f"{len(run_a['structure'])} files each"
        if run_a["structure"] == run_b["structure"]
        else f"only_a={sorted(run_a['structure'] - run_b['structure'])} "
        f"only_b={sorted(run_b['structure'] - run_a['structure'])}",
    )

    # 4. 参数与 seed
    check(
        "parameters_and_seed",
        ma.get("parameters") == mb.get("parameters")
        and ma.get("random_seed") == mb.get("random_seed"),
        f"seed={ma.get('random_seed')}",
    )

    # 5. 分数容差
    results_a = {r.ligand_id: r for r in run_a["output"].results}
    results_b = {r.ligand_id: r for r in run_b["output"].results}
    check(
        "result_ligand_ids",
        set(results_a) == set(results_b),
        f"{sorted(results_a)} vs {sorted(results_b)}",
    )
    for ligand_id in results_a:
        ra, rb = results_a.get(ligand_id), results_b.get(ligand_id)
        if ra is None or rb is None:
            continue
        if ra.best_affinity_kcal_mol is None or rb.best_affinity_kcal_mol is None:
            check(
                f"affinity[{ligand_id}]",
                ra.best_affinity_kcal_mol == rb.best_affinity_kcal_mol,
                "missing affinity",
            )
            continue
        diff = abs(ra.best_affinity_kcal_mol - rb.best_affinity_kcal_mol)
        check(
            f"affinity[{ligand_id}]",
            diff <= AFFINITY_TOLERANCE,
            f"{ra.best_affinity_kcal_mol} vs {rb.best_affinity_kcal_mol} "
            f"(|diff|={diff:.6f} <= {AFFINITY_TOLERANCE})",
        )
        poses_a = [p.affinity_kcal_mol for p in ra.poses]
        poses_b = [p.affinity_kcal_mol for p in rb.poses]
        pose_ok = len(poses_a) == len(poses_b) and all(
            abs(x - y) <= AFFINITY_TOLERANCE for x, y in zip(poses_a, poses_b)
        )
        check(
            f"pose_affinities[{ligand_id}]",
            pose_ok,
            f"{len(poses_a)} poses, max|diff|="
            + (
                f"{max(abs(x - y) for x, y in zip(poses_a, poses_b)):.6f}"
                if poses_a and poses_b
                else "n/a"
            ),
        )

    return not problems, details, problems


def write_reports(
    run_a: dict, run_b: dict, passed: bool, details: dict, problems: list[str]
) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": str(INPUT_JSON.relative_to(PROJECT_ROOT)),
        "tolerance_kcal_mol": AFFINITY_TOLERANCE,
        "passed": passed,
        "run_a": {
            "job_id": run_a["job_id"],
            "best_affinity_kcal_mol": run_a["output"]
            .results[0]
            .best_affinity_kcal_mol,
        },
        "run_b": {
            "job_id": run_b["job_id"],
            "best_affinity_kcal_mol": run_b["output"]
            .results[0]
            .best_affinity_kcal_mol,
        },
        "checks": details["checks"],
        "problems": problems,
    }
    json_path = REPORTS_DIR / "reproducibility_report.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# 可复现性验证报告（verify_reproducibility）",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- 输入：`{payload['input']}`（固定 seed={run_a['manifest']['random_seed']}）",
        f"- 分数容差：±{AFFINITY_TOLERANCE} kcal/mol",
        f"- 结果：**{'PASS（双跑一致）' if passed else 'FAIL（存在不一致）'}**",
        "",
        "| 检查项 | 结果 | 说明 |",
        "| --- | --- | --- |",
    ]
    for item in details["checks"]:
        mark = "PASS" if item["passed"] else "FAIL"
        lines.append(f"| {item['name']} | {mark} | {item['info']} |")
    lines += [
        "",
        f"- run A: `{run_a['job_id']}` "
        f"(best={run_a['output'].results[0].best_affinity_kcal_mol} kcal/mol)",
        f"- run B: `{run_b['job_id']}` "
        f"(best={run_b['output'].results[0].best_affinity_kcal_mol} kcal/mol)",
        "",
        "说明：`reports/result.json|result.md|comparison.csv` 含 job_id 与时间戳，"
        "属预期非确定性产物，不参与哈希比对；其余确定性产物哈希全部逐字节一致。",
        "",
        "**科学备注**：可复现的打分不等于实验可重复的结合自由能；"
        "Vina affinity 是经验打分函数与构象搜索的结果。",
    ]
    md_path = REPORTS_DIR / "reproducibility_report.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {json_path}")
    print(f"written: {md_path}")


def main() -> int:
    print("=== reproducibility run A ===")
    run_a = run_once("A")
    print(f"job_id={run_a['job_id']} best="
          f"{run_a['output'].results[0].best_affinity_kcal_mol}")
    print("=== reproducibility run B ===")
    run_b = run_once("B")
    print(f"job_id={run_b['job_id']} best="
          f"{run_b['output'].results[0].best_affinity_kcal_mol}")
    passed, details, problems = compare(run_a, run_b)
    write_reports(run_a, run_b, passed, details, problems)
    if passed:
        print("REPRODUCIBILITY_PASS")
        return 0
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    print("REPRODUCIBILITY_FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
