# 结果解释与失败恢复详细参考

## 12. Result Interpretation

完整公式与解读规则见 `docs/RESULT_INTERPRETATION.md`
（实现：`backend/app/services/comparison_service.py`、
`backend/app/services/interpretation_service.py`）。

| 指标 | 怎么读 |
| --- | --- |
| `affinity_kcal_mol` | Vina 经验打分，越负排序越靠前；**不是自由能/药效**；只有同受体、同准备、同 box、同参数、同 seed 的批内排序有展示意义 |
| `rank` | Vina 输出顺序；top-1 与 top-2 差 < 1 kcal/mol 时视为不可区分 |
| `rmsd_lb` / `rmsd_ub` | Vina 内部对最优 pose 的自参照 RMSD 估计（Å），**不是**对晶体构象的 RMSD |
| `ligand_efficiency` | `-best_affinity / heavy_atom_count`（kcal/mol/重原子），辅助指标，惩罚大分子 |
| pose gap（`pose_score_gap`） | top-2 与 top-1 能量差；≥1.0 kcal/mol 记区分度良好 |
| relative docking profile | 雷达图五维：`affinity`、`ligand_efficiency`、`pose_consistency`、`drug_likeness`、`preparation_quality`（`backend/app/api/comparison.py` 的 `RADAR_DIMENSIONS`），全部归一到 [0,1] 且越大越好，标题固定 "Relative Docking & Developability Profile" |

雷达图归一化公式（全部、与代码一致）：

- `relative_affinity = (a_worst − a_i) / (a_worst − a_best)`，批内最优得 1；
  单分子批次的批内归一维度返回 `null`，不虚构；
- `ligand_efficiency = −a_best / heavy_atom_count`，批内秩归一化为
  `ligand_efficiency_rank_norm`；
- `pose_consistency = clip(pose_score_gap, 0, 1)`；
- 类药性 fit：`molwt_fit = ramp(MolWt, 500→600)`、`tpsa_fit = ramp(TPSA, 140→180)`、
  `flexibility_fit = ramp(rotatable_bonds, 7→12)`、
  `logp_fit = window(LogP, [-1,5], soft [-3,7])`（`drug_likeness` 为四者的组合）；
- `preparation_quality = max(0, 1 − 0.1 × num_preparation_warnings)`。

每次比较把完整公式写入 `ComparisonOutput.normalization_method`（机器可查），
并附固定 disclaimer：相对指标仅用于同批展示性排序，不是绝对结合概率、
实验自由能或药效。

**可以得出的结论**：同批条件下的展示性相对排序、pose 不确定性提示、
准备质量提示。**不能得出的结论**：任何绝对结合强度、Kd/Ki/IC50、
药效、毒性、跨体系比较（详见 §18）。

## 13. Failure Cases and Recovery

13 个失败案例位于 `examples/failure_cases/<CODE>/`（每案例含 `input.json` +
`expected.json`）；自动化回归在 `backend/tests/test_failures.py` 中逐案例
真实运行 `run_job` 并断言结构化错误；再生成命令 `make failure-cases`。
总表与 `docs/FAILURE_CASES.md` 一致：

| 错误代码 | 触发条件 | 检测阶段 | 可恢复 | 建议操作 | 对应测试 |
| --- | --- | --- | --- | --- | --- |
| `INVALID_SMILES` | SMILES 语法非法 | prepare_ligand | 否 | 检查 SMILES 语法 | `test_case_invalid_smiles` |
| `MULTI_FRAGMENT_LIGAND` | 盐/混合物等多片段分子 | prepare_ligand | 否 | 保留最大片段或拆分输入 | `test_case_multi_fragment_ligand` |
| `UNSUPPORTED_ELEMENT` | Vina 原子类型表之外的元素 | prepare_ligand | 否 | 只用 H,B,C,N,O,F,Si,P,S,Cl,Br,I | `test_case_unsupported_element` |
| `CONFORMER_GENERATION_FAILED` | 3D 嵌入失败（测试经 mock 触发，已在 expected.json notes 如实标注） | prepare_ligand | 是 | 降低环复杂度或增加候选构象数 | `test_case_conformer_generation_failed` |
| `INVALID_RECEPTOR` | 空 PDB / 无 ATOM 记录 | analyze_receptor | 否 | 提供非空且含 ATOM 记录的 PDB | `test_case_invalid_receptor` |
| `CHAIN_NOT_FOUND` | `selected_chains` 指定不存在的链 | prepare_receptor | 是 | 从 `details.available_chains` 中选择 | `test_case_chain_not_found` |
| `RECEPTOR_PREPARATION_FAILED` | 残基全部未知（XXX），Meeko 严格与回退均失败 | prepare_receptor | 否 | 提供标准残基的有效受体 | `test_case_receptor_preparation_failed` |
| `BOX_OUTSIDE_RECEPTOR` | box 与受体包围盒无交集 | validate_box | 是 | 将盒中心移向受体包围盒 | `test_case_box_outside_receptor` |
| `BOX_TOO_LARGE` | 边长 > 30 Å 或体积超限 | validate_box | 是 | 减小 padding、改用 residue_list/reference_ligand | `test_case_box_too_large` |
| `VINA_FAILED` | 损坏的配体 PDBQT；API 子进程失败后回退 CLI 仍失败 | run_vina | 否 | 检查 PDBQT 完整性，用 Meeko 重新生成 | `test_case_vina_failed` |
| `NO_POSE` | 输出中无 `REMARK VINA RESULT`（mock `dock_one` 复现，notes 已说明） | parse_scores | 是 | 检查盒位置与配体 PDBQT | `test_case_no_pose` |
| `PARTIAL_BATCH_FAILURE` | 批量中 1 个分子 SMILES 非法：整批 SUCCESS，失败分子记 FAILED | prepare_ligand | 否（该分子） | 逐分子查看 `structured_error` | `test_case_partial_batch_failure` |
| `ARTIFACT_ACCESS_DENIED`（错误码 `INPUT_VALIDATION_FAILED`） | 受体路径 `../../etc/passwd` 越出项目目录 | analyze_receptor | 否 | 受体路径必须位于项目目录内 | `test_case_artifact_access_denied` |

错误码全集定义于 `backend/app/schemas.py` 的 `ErrorCode`，另含
`INVALID_BOX`、`LIGAND_TOO_LARGE`、`PDBQT_PREPARATION_FAILED`、`VINA_TIMEOUT`、
`FILE_NOT_FOUND`、`INTERNAL_ERROR`，由 schema 约束、超时与内部保护路径覆盖。
