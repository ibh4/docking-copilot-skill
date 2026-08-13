# 参数指南（PARAMETER GUIDE）

所有参数的权威定义在 `backend/app/schemas.py`（Pydantic 单一事实来源），
导出副本在 `schemas/*.schema.json`（`make schemas` 重新导出）。
本文只解释"怎么选、为什么"。

## 1. 顶层输入 `DockingInput`

| 字段 | 说明 |
| --- | --- |
| `job_name` | 任务名，进入 job_id 后缀与报告标题 |
| `ligands` | 配体列表，1–20 个（`BATCH_MAX_LIGANDS=20`），每个含 `ligand_id`（批次内唯一）、`smiles`、可选 `name` |
| `ligand_preparation` | 配体准备策略（见 §2） |
| `receptor` | `source`（项目内相对路径的 PDB）+ `config`（见 §3） |
| `docking_box` | 对接盒（见 §4） |
| `docking_parameters` | Vina 参数（见 §5） |

## 2. 配体准备 `ligand_preparation`

| 参数 | 默认 | 可选值 | 说明 |
| --- | --- | --- | --- |
| `add_hydrogens` | `true` | bool | 加氢；关闭后价态不完整通常导致力场/PDBQT 失败 |
| `embed_method` | `ETKDGv3` | 仅 `ETKDGv3` | RDKit 3D 构象嵌入，固定 seed（默认 42）保证可复现 |
| `num_conformers` | `10` | int | 生成的候选构象数；柔性大的分子可上调，但线性增加准备耗时 |
| `optimize_force_field` | `MMFF94` | `MMFF94` / `UFF` | MMFF94 参数不可用时自动受控回退 UFF 并记录警告 |
| `max_iterations` | `500` | int | 力场优化最大迭代 |
| `select_conformer_by` | `minimum_force_field_energy` | 固定 | 取力场能量最低构象（**力场能量 ≠ 结合能**） |
| `random_seed` | `42` | int | 构象生成随机种子；改动会改变构象与最终分数 |

**元素限制**：仅支持 H,B,C,N,O,F,Si,P,S,Cl,Br,I（Vina 原子类型表）；
多片段分子（盐/复合物）会被拒绝（`MULTI_FRAGMENT_LIGAND`），请预先拆分为最大片段。

## 3. 受体配置 `receptor.config`

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `selected_chains` | `null`（全部链） | 只保留指定链；链不存在报 `CHAIN_NOT_FOUND`（错误信息会列出可用链） |
| `keep_waters` | `false` | 默认去水；水介导的结合研究需显式保留并自行评估 |
| `keep_cofactors` / `keep_metals` | 空列表 | 需要保留的辅因子/金属残基名（如 `ZN`、`MG`）；金属对活性位点关键时务必显式保留 |
| `remove_original_ligands` | `true` | 去除共晶配体；`reference_ligand` box 模式会在定位后按此策略移除 |
| `alternate_location_policy` | `highest_occupancy` | 交替构象取占位率最高者（`keep_all` 会产生重叠原子，不推荐） |
| `missing_residue_policy` | `warn` | 缺失残基只警告；`error` 则直接失败 |
| `protonation_policy` | `tool_default` | 工具默认质子化；**未做 pH 显式建模**（见 SCIENTIFIC_LIMITATIONS.md） |

## 4. 对接盒 `docking_box`

四种模式（`mode`）：

| 模式 | 必填字段 | 行为 |
| --- | --- | --- |
| `explicit` | `center`、`size` | 直接指定中心与边长（Å） |
| `reference_ligand` | `reference_ligand_resid`、可选 `padding_angstrom`（默认 8.0） | 以共晶参考配体质心为中心，边长 = 配体包围盒 + 2×padding |
| `residue_list` | `residue_ids`（如 `"A:42"`）、可选 `padding_angstrom` | 以指定残基包围盒 + padding 为盒 |
| `whole_receptor` | 可选 `padding_angstrom` | 整个受体包围盒 + padding；**仅用于小测试体系**，真实蛋白几乎必然 `BOX_TOO_LARGE` |

**硬约束**（`config.py`）：

- 单边长：10 Å ≤ edge ≤ 30 Å（`BOX_EDGE_MIN` / `BOX_EDGE_MAX`）
- 体积 ≤ 27000 Å³（`BOX_VOLUME_MAX`，即 30³）
- box 必须覆盖/相交受体包围盒，否则 `BOX_OUTSIDE_RECEPTOR`
- 超限报 `BOX_TOO_LARGE` / `INVALID_BOX`，均为可恢复错误（调小即可重跑）

**经验**：活性位点明确的场景优先 `reference_ligand`（有共晶配体时）或
`residue_list`，盒边长 20–25 Å 通常足够；盒子过大浪费搜索空间并稀释
exhaustiveness 的有效采样密度。

## 5. Vina 参数 `docking_parameters`

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `scoring_function` | `vina` | 固定 | Vina 经验打分函数 |
| `exhaustiveness` | `8` | 1–32 | 构象搜索强度；翻倍约翻倍耗时。筛选期 8 足够，精修单分子可到 16–32 |
| `num_modes` | `9` | int | 返回 pose 数上限 |
| `energy_range` | `3.0` | kcal/mol | 与最优 pose 的最大能量差，过滤无关 pose |
| `cpu` | `4` | ≤ 8（`CPU_MAX`） | 并行线程数 |
| `seed` | `42` | int | **可复现性关键**：固定 seed 时同输入同环境双跑分数一致（±0.01 kcal/mol，见 REPRODUCIBILITY.md） |

单配体对接超时 300 s（`DOCKING_TIMEOUT_SECONDS`），超时记 `VINA_TIMEOUT`。
该 300 s 是本项目自设的**单分子保护性安全超时**；官方沙箱单任务总上限为
**900 秒**。正式评测环境只有 2 核，因此建议输入中显式设置 `cpu=2`，并优先
保持默认 `exhaustiveness=8`，避免过度并发或高搜索强度占满预算。

## 6. 运行时长预算（官方沙箱单任务 900 秒）

官方评审统一沙箱为 **2 核 / 4 GB / 无 GPU**，单任务最大运行时长 **900 秒**。
本项目应按“单个官方任务在 900 秒内完成”设计，而不是依赖长时间后台计算。

| 场景 | 典型耗时（本地实测参考） | 官方评测建议 |
| --- | --- | --- |
| 单分子，`exhaustiveness=8`、`num_modes=9` | 秒级 | `cpu=2`，直接运行 |
| 小批量候选 | 秒级~分钟级 | 串行或受限执行，控制总量 |
| 高 `exhaustiveness`（如 32） | 约随搜索强度增加 | 仅在任务确有必要且预算允许时使用 |
| 运行时网络资源获取 | 不稳定 | 不作为必要路径，优先使用任务提供或仓库内数据 |

要点：

1. `DOCKING_TIMEOUT_SECONDS=300` 是单分子保护性超时，非平台总预算；
2. 官方任务总预算 900 秒，因此不应假设可以把 20 个分子全部运行到各自 300 秒上限；
3. 2 核环境建议 `cpu=2`；代码本地默认值保留不变，以避免改变原有算法/业务逻辑；
4. Web Demo、Node 构建和前端可视化不是官方科学任务的必要执行步骤。

## 7. 常见参数误区

1. **改 seed ≠ 更好的答案**：不同 seed 得到不同构象搜索轨迹，
   分数差异反映搜索不确定性，不是"更准"。
2. **exhaustiveness 不是越大越科学**：它只增加采样量，不改善打分函数本身。
3. **分数跨任务不可比**：不同受体/box/质子化/参数下，
   affinity 数值没有任何可比性（见 RESULT_INTERPRETATION.md §可比条件）。
