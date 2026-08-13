# 可复现性（REPRODUCIBILITY）

## 1. 复现承诺的范围

在**相同输入 + 相同环境（工具版本/平台）+ 固定 seed** 下，本流程保证：

1. 输入/受体/配体哈希一致（`input_sha256` / `receptor_sha256` / `ligand_sha256`）；
2. 全部**确定性产物**逐字节一致（ligand PDBQT、受体清洗 PDB/PDBQT、pose 文件等，
   `manifest.artifact_sha256` 逐项比对）；
3. 产物目录结构一致；
4. 参数与 seed 一致；
5. 分数一致：`best_affinity` 与逐 pose affinity 容差 **±0.01 kcal/mol**。

**例外（预期非确定性产物）**：`reports/result.json`、`result.md`、`comparison.csv`
内嵌 job_id 与时间戳，不参与哈希比对。

## 2. 如何验证

```bash
make reproducibility
# 等价于：conda run -n dockskill python scripts/verify_reproducibility.py
```

脚本行为（`scripts/verify_reproducibility.py`）：

1. 以 `examples/inputs/single_ligand.json`（乙醇，seed=42）完整跑两次 `run_job`；
2. 按 §1 的 5 类检查逐项比对；
3. 写出 `reports/reproducibility_report.md` 与 `reports/reproducibility_report.json`；
4. 全部通过时打印唯一标记 **`REPRODUCIBILITY_PASS`**，否则打印
   `REPRODUCIBILITY_FAIL` 与逐项问题列表并以非零退出。

最近一次验证结果（2026-08-05）：双跑 best_affinity 均为 **-2.776 kcal/mol**，
全部确定性产物哈希一致 → PASS。

## 3. 复现的关键前提

| 前提 | 说明 |
| --- | --- |
| `seed` 固定 | `docking_parameters.seed` 与 `ligand_preparation.random_seed`（默认均 42）；改 seed 即改结果 |
| 输入逐字节一致 | 输入 JSON、受体 PDB 的哈希都记录在 manifest，任何改动可检测 |
| 工具版本一致 | manifest 记录 `vina_version` / `rdkit_version` / `meeko_version` / `python_version` / 平台；跨版本升级可能出现数值级差异 |
| 平台一致 | Vina 二进制行为随平台/编译可能有细微差异，manifest 记录架构与系统版本 |

## 4. 复现 ≠ 科学正确

可复现只说明**计算过程确定、无随机漂移**，并不说明：

- 打分接近实验结合自由能（它是经验打分，见 SCIENTIFIC_LIMITATIONS.md）；
- pose 是真实结合模式；
- 结果可以跨体系比较。

manifest.json 是复现审计的核心：每次运行都记录输入哈希、参数、
实际执行的命令/API 调用序列（`commands_or_api_calls`）与全部产物哈希。
