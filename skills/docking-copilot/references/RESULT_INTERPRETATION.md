# 结果解读（RESULT INTERPRETATION）

> **首要声明**：Vina `affinity`（kcal/mol）是**经验打分函数与构象搜索的结果**，
> 不等于实验结合自由能、Kd、Ki、IC50，也不能推出任何药效结论。
> 本报告所有"比较"都是**批次内展示性相对指标**。

## 1. 输出字段怎么读

### result.json / reports/result.md

| 字段 | 含义 | 注意 |
| --- | --- | --- |
| `best_affinity_kcal_mol` | 全部 pose 中最优（最负）的打分 | 更负 ≠ 更强结合力；只有**同批同条件**下排序有意义 |
| `poses[].affinity_kcal_mol` | 每个 pose 的打分 | 多个 pose 分数接近（<1 kcal/mol）时存在构象不确定性 |
| `poses[].rmsd_lb / rmsd_ub` | Vina 内部对最优 pose 的 RMSD 下/上界估计 | 是搜索过程的自参照量，**不是**对晶体构象的 RMSD |
| `ligand_efficiency` | `-best_affinity / heavy_atom_count`（kcal/mol/重原子） | 辅助指标，惩罚大分子，不能单独决策 |
| `descriptors` | MolWt、LogP、TPSA、HBD、HBA、rotatable_bonds、heavy_atom_count | RDKit 计算，仅用于画像与雷达图 |
| `preparation_warnings` | 准备阶段警告（如 MMFF→UFF 回退） | 有警告的分子结果可信度下降，需人工复核 |

### pose 解读要点

- **分数接近的 pose 不可区分**：top-1 与 top-2 差 < 1 kcal/mol 时，
  排序不稳定，应视为同一水平；
- pose 文件 `poses/<ligand_id>/pose_NNN.pdbqt`（另有 `.pdb` 转写）可直接用于可视化。

## 2. 可比条件（什么时候才能比较）

**只有同时满足以下条件**，批次内的相对排序才有展示意义：

1. 同一受体（同一 PDB、同一链选择与清洗策略 → `receptor_sha256` 一致）；
2. 同一对接盒（同 mode/center/size）；
3. 同一 Vina 参数与 seed；
4. 同一配体准备流程。

`ComparisonContext.consistent` 字段与 `comparison.csv` 中的
`context` 记录了这些条件；跨任务、跨受体的分数**一律不可比**。

## 3. 雷达图归一化公式（全部、与代码一致）

雷达图标题固定：**Relative Docking & Developability Profile**。
所有维度统一到 **[0, 1] 且"越大越好"**（方向统一规则：affinity 越负越好，
归一化后翻转为越大越好；描述符采用理想区间/上限的分段线性函数）。
公式实现于 `backend/app/services/comparison_service.py`，
每次比较结果会把完整公式写入 `normalization_method` 字段（机器可查）。

### 3.1 relative_affinity（批次内相对打分）

\[
\text{relative\_affinity} = \frac{a_{worst} - a_i}{a_{worst} - a_{best}} \in [0,1]
\]

其中 \(a_i\) 为配体 i 的 best_affinity（kcal/mol，越负越好），
\(a_{best}, a_{worst}\) 为批内最优/最差。最优者得 1，最差者得 0。
批次只有 1 个成功配体时记 1.0。

### 3.2 ligand_efficiency 与 ligand_efficiency_rank_norm

\[
\text{ligand\_efficiency} = \frac{-a_{best}}{\text{heavy\_atom\_count}}
\quad (\text{kcal/mol per heavy atom，辅助指标})
\]

`ligand_efficiency_rank_norm`：批内按 ligand_efficiency 排名的秩归一化
（0–1，越大越好），避免不同体系间绝对值不可比的问题。

### 3.3 pose_consistency（pose 区分度）

\[
\text{pose\_score\_gap} = a_{pose2} - a_{pose1} \quad (\text{kcal/mol})
\]
\[
\text{pose\_consistency} = \min(1,\ \max(0,\ \text{pose\_score\_gap}))
\]

即 top-2 与 top-1 能量差 ≥ 1.0 kcal/mol 记 1.0（区分度良好），
线性降到 0（top-2 几乎并列，构象不确定性高）。

### 3.4 类药性 fit（分段线性 ramp，理想区间内 = 1.0）

统一形式 `_ramp_descending`：value ≤ ideal_max → 1.0；
线性下降到 soft_max 处为 0；超出取 0。

| 维度 | 公式 | 理想区（=1.0） | 软上限（=0） |
| --- | --- | --- | --- |
| `molwt_fit` | `_ramp_descending(MolWt, 500, 600)` | ≤ 500 g/mol | 600 |
| `tpsa_fit` | `_ramp_descending(TPSA, 140, 180)` | ≤ 140 Å² | 180 |
| `flexibility_fit` | `_ramp_descending(rotatable_bonds, 7, 12)` | ≤ 7 | 12 |

`logp_fit` 采用窗口型 `_ramp_window`：

\[
\text{logp\_fit} = 1.0 \text{ 当 } -1 \le \text{LogP} \le 5;
\]
向 soft 边界 -3 与 7 线性降到 0，区间外按
\((x - (-3))/((-1)-(-3))\) 与 \((7-x)/(7-5)\) 计算。

这些区间是常见的类药性展示参考值（类似 Lipinski/Veber 思路），
**只用于展示画像，不是活性判据**。

### 3.5 preparation_quality

\[
\text{preparation\_quality} = \max(0,\ 1 - 0.1 \times \text{num\_preparation\_warnings})
\]

每条准备警告（如 MMFF→UFF 回退、未收敛）扣 0.1。

### 3.6 composite_display_score（仅展示）

\[
\text{composite} = 0.4\,\text{relative\_affinity} + 0.2\,\text{pose\_consistency}
+ 0.2\,\text{ligand\_efficiency\_rank\_norm} + 0.2\,\text{preparation\_quality}
\]

仅在批次内 ≥ 2 个成功配体时计算。**严禁**将其用作药效预测、
候选化合物取舍的唯一依据或对外结论。

## 4. 解读流程建议

1. 先看 `status` 与 `preparation_warnings`：有警告的结果先降级看待；
2. 批内排序看 `relative_affinity`，但 < 1 kcal/mol 的差距视为不可区分；
3. 检查 `pose_consistency`：接近 0 的分子 pose 归属不可靠；
4. 用雷达图做"对接 + 类药性"联合画像时，明确它是展示性指标；
5. 任何进入实验决策的结论，回到 §可比条件 复核前提是否成立。
