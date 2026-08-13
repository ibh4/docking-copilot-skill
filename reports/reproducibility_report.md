# 可复现性验证报告（verify_reproducibility）

- 生成时间：2026-08-05T04:32:46.036404+00:00
- 输入：`examples/inputs/single_ligand.json`（固定 seed=42）
- 分数容差：±0.01 kcal/mol
- 结果：**PASS（双跑一致）**

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| input_sha256 | PASS | bf5bdcdc03afa17b60f27ce77a90548c6a9e9fdb5b111c4cc46aa2669e7c576d vs bf5bdcdc03afa17b60f27ce77a90548c6a9e9fdb5b111c4cc46aa2669e7c576d |
| receptor_sha256 | PASS | 200f137801aebdfeeb49f25895a234eb2913c62d05d84665d96743823dd643bc vs 200f137801aebdfeeb49f25895a234eb2913c62d05d84665d96743823dd643bc |
| ligand_sha256 | PASS | {'ethanol': '7f3581328595cad6a0d5350b682b7c8dfcb57441aece37cdcf74a56de3572a2a'} vs {'ethanol': '7f3581328595cad6a0d5350b682b7c8dfcb57441aece37cdcf74a56de3572a2a'} |
| artifact_sha256_keys | PASS | 6 deterministic artifacts compared |
| artifact_sha256_values | PASS | all deterministic artifact hashes identical |
| artifact_structure | PASS | 36 files each |
| parameters_and_seed | PASS | seed=42 |
| result_ligand_ids | PASS | ['ethanol'] vs ['ethanol'] |
| affinity[ethanol] | PASS | -2.776 vs -2.776 (|diff|=0.000000 <= 0.01) |
| pose_affinities[ethanol] | PASS | 9 poses, max|diff|=0.000000 |

- run A: `20260805-043234_single_ligand_ethanol` (best=-2.776 kcal/mol)
- run B: `20260805-043240_single_ligand_ethanol` (best=-2.776 kcal/mol)

说明：`reports/result.json|result.md|comparison.csv` 含 job_id 与时间戳，属预期非确定性产物，不参与哈希比对；其余确定性产物哈希全部逐字节一致。

**科学备注**：可复现的打分不等于实验可重复的结合自由能；Vina affinity 是经验打分函数与构象搜索的结果。
