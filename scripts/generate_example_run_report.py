#!/usr/bin/env python3
"""生成 reports/example_run.json（由真实 run_example 输出构建）。"""
import json, sys, datetime
from pathlib import Path

root = Path(sys.argv[1])
stdout_path = Path(sys.argv[2])
rc = int(sys.argv[3])
stdout = stdout_path.read_text(encoding="utf-8", errors="ignore")
# 去除绝对路径（相对化到项目根），避免敏感信息入库
stdout = stdout.replace(str(root.resolve()) + "/", "").replace(str(root.resolve()), ".")
ok = "RUN_EXAMPLE_PASS" in stdout and rc == 0

def newest(prefix):
    dirs = sorted(p for p in (root / "outputs").glob(f"*{prefix}*") if p.is_dir())
    return dirs[-1] if dirs else None

single = newest("single_ligand_ethanol")
invalid = newest("invalid_smiles_failure_case")
result = json.loads((single / "reports" / "result.json").read_text())
manifest = json.loads((single / "manifest.json").read_text())
r = result["results"][0]
err_job = json.loads((invalid / "reports" / "result.json").read_text())
report = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "command": "make example (python scripts/run_example.py)",
    "exit_code": rc,
    "verdict": "PASS" if ok else "FAIL",
    "success_marker": "RUN_EXAMPLE_PASS",
    "examples": [
        {
            "input": "examples/inputs/single_ligand.json",
            "job_id": result["job_id"],
            "state": result["state"],
            "job_dir": str(single.relative_to(root)),
            "best_affinity_kcal_mol": r["best_affinity_kcal_mol"],
            "ligand_efficiency": r["ligand_efficiency"],
            "num_poses": len(r["poses"]),
            "artifacts_ok": all(
                (single / x).is_file()
                for x in [
                    "manifest.json", "reports/result.json", "reports/result.md",
                    "reports/comparison.csv", "bundle.zip",
                ]
            ),
            "manifest": {
                "random_seed": manifest["random_seed"],
                "vina_version": manifest["vina_version"],
                "rdkit_version": manifest["rdkit_version"],
                "meeko_version": manifest["meeko_version"],
                "runtime_seconds": manifest["runtime_seconds"],
                "num_artifacts_hashed": len(manifest.get("artifact_sha256", {})),
            },
        },
        {
            "input": "examples/inputs/invalid_smiles.json",
            "job_id": err_job["job_id"],
            "state": err_job["state"],
            "job_dir": str(invalid.relative_to(root)),
            "structured_error": err_job["structured_error"],
            "expected_error_code": "INVALID_SMILES",
            "match": err_job["structured_error"]["error_code"] == "INVALID_SMILES",
        },
    ],
    "stdout_tail": stdout[-600:],
}
out = root / "reports" / "example_run.json"
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print("example_run.json:", report["verdict"],
      r["best_affinity_kcal_mol"], report["examples"][1]["match"])
