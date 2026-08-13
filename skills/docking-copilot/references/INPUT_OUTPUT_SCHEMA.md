# 输入与输出 Schema 详细参考

## 6. Input Schema

- 权威定义：`backend/app/schemas.py`（Pydantic，单一事实来源）；
- 导出的 JSON Schema：`schemas/docking_input.schema.json`（`make schemas` 重新导出）；
- 单位：几何量（center/size/坐标）Å，padding Å；能量 kcal/mol；
- 合法输入示例：`examples/inputs/single_ligand.json`、`examples/inputs/multiple_ligands.json`。

### 6.1 顶层 `DockingInput`

| 字段 | 类型 | 必填 | 默认 | 范围/约束 | 单位 |
| --- | --- | --- | --- | --- | --- |
| `job_name` | string | 是 | — | 1–128 字符 | — |
| `ligands` | `LigandSpec[]` | 是 | — | 1–20 个（`BATCH_MAX_LIGANDS=20`）；`ligand_id` 批内唯一 | — |
| `ligand_preparation` | object | 否 | 见 6.2 | — | — |
| `receptor` | `ReceptorRef` | 是 | — | `source` 必须是项目目录内的相对路径（`safe_resolve` 防穿越） | — |
| `docking_box` | `DockingBox` | 否 | explicit 模式 | 见 6.4 | Å |
| `docking_parameters` | `VinaParams` | 否 | 见 6.5 | — | — |

`LigandSpec`：`ligand_id`（1–64 字符，必填）、`smiles`（1–500 字符，必填）、
`name`（可选）。

### 6.2 `ligand_preparation`

| 字段 | 默认 | 范围/可选值 | 说明 |
| --- | --- | --- | --- |
| `add_hydrogens` | `true` | bool | 加氢 |
| `embed_method` | `ETKDGv3` | 仅 `ETKDGv3` | RDKit 3D 嵌入 |
| `num_conformers` | `10` | 1–50 | 候选构象数 |
| `optimize_force_field` | `MMFF94` | `MMFF94` / `UFF` | MMFF 参数缺失时受控回退 UFF 并记录警告（§11） |
| `max_iterations` | `500` | 0–10000 | 力场优化迭代上限 |
| `select_conformer_by` | `minimum_force_field_energy` | 固定 | 力场能量最低构象（≠ 结合能） |
| `random_seed` | `42` | int | 构象生成种子 |

### 6.3 `receptor.config`（`ReceptorConfig`）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `selected_chains` | `null`（全部链） | 链不存在报 `CHAIN_NOT_FOUND`（details 列出可用链） |
| `keep_waters` | `false` | 默认去水 |
| `keep_cofactors` / `keep_metals` | `[]` | 需保留的残基名列表（如 `ZN`） |
| `remove_original_ligands` | `true` | 去除共晶配体 |
| `alternate_location_policy` | `highest_occupancy` | `highest_occupancy` / `keep_all` |
| `missing_residue_policy` | `warn` | `warn` / `error` |
| `protonation_policy` | `tool_default` | 不做 pH 显式建模（§18） |

### 6.4 `docking_box`（四模式）

| 模式 | 必填字段 | 行为 |
| --- | --- | --- |
| `explicit` | `center`（3 元 Å）、`size`（3 元 Å） | 直接指定；center 必须有限，size 为正 |
| `reference_ligand` | `reference_ligand_resid` | 以共晶配体质心为中心，边长 = 配体包围盒 + 2×padding |
| `residue_list` | `residue_ids`（如 `"A:42"`） | 指定残基包围盒 + padding |
| `whole_receptor` | — | 全受体包围盒 + padding（仅小测试体系） |

硬约束（`backend/app/config.py`）：单边 10–30 Å（`BOX_EDGE_MIN/MAX`）、
体积 ≤ 27000 Å³（`BOX_VOLUME_MAX`）、`padding_angstrom` 0–12（默认 8.0）、
box 必须与受体包围盒相交（否则 `BOX_OUTSIDE_RECEPTOR`）。

### 6.5 `docking_parameters`（`VinaParams`）

| 字段 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- |
| `scoring_function` | `vina` | 固定 | — |
| `exhaustiveness` | `8` | 1–32 | — |
| `num_modes` | `9` | 1–20 | — |
| `energy_range` | `3.0` | 0–10 | kcal/mol |
| `cpu` | `4` | 1–8（`CPU_MAX`） | — |
| `seed` | `42` | int | — |

### 6.6 JSON 示例（`examples/inputs/single_ligand.json`，逐字节可运行）

```json
{
  "job_name": "single_ligand_ethanol",
  "ligands": [
    { "ligand_id": "ethanol", "smiles": "CCO", "name": "ethanol" }
  ],
  "ligand_preparation": {
    "add_hydrogens": true,
    "embed_method": "ETKDGv3",
    "num_conformers": 10,
    "optimize_force_field": "MMFF94",
    "max_iterations": 500,
    "select_conformer_by": "minimum_force_field_energy",
    "random_seed": 42
  },
  "receptor": { "source": "examples/data/sample_receptor.pdb" },
  "docking_box": {
    "center": [18.3, 2.3, 21.4],
    "size": [20, 20, 20],
    "units": "angstrom"
  },
  "docking_parameters": {
    "exhaustiveness": 8, "num_modes": 9, "seed": 42, "cpu": 4, "energy_range": 3.0
  }
}
```

相互依赖条件：`explicit` 模式要求 center 与 size 同时给出；
`reference_ligand` 模式要求 `reference_ligand_resid`；`residue_list` 模式要求
`residue_ids`（由 `DockingBox._check_mode_fields` model_validator 强制）。

## 7. Output Schema

- JSON Schema：`schemas/docking_output.schema.json`、
  `schemas/comparison_output.schema.json`、`schemas/error.schema.json`；
- Pydantic 定义：`backend/app/schemas.py`（`DockingOutput` / `LigandResult` /
  `Pose` / `ComparisonOutput` / `StructuredError`）；
- 真实产物示例：任意 `outputs/<job_id>/reports/result.json`，
  摘要副本见 `examples/expected_outputs/result_summary.json`（真实运行摘录，非手写）。

### 7.1 字段总览（`DockingOutput`）

| 字段 | 含义 |
| --- | --- |
| `status` / `state` | 任务结果与 12 态状态机终态（`SUCCESS` / `FAILED` / …） |
| `results[]`（`LigandResult`） | 逐分子结果：`status`、`best_affinity_kcal_mol`、`poses[]`、`ligand_efficiency`、`descriptors`、`preparation_warnings`、`warnings`、`artifacts`、`provenance`、`structured_error` |
| `poses[]`（`Pose`） | `rank`、`affinity_kcal_mol`、`rmsd_lb`/`rmsd_ub`（Å）、`pose_file`、`pose_pdb_file` |
| `descriptors` | MolWt、LogP、TPSA、HBD、HBA、rotatable_bonds、heavy_atom_count 等（RDKit） |
| `warnings` | 任务级警告（受体清洗、`--allow_bad_res` 回退等） |
| `structured_error` | 失败时的 `StructuredError`（error_code/stage/message/details/recoverable/suggested_actions） |
| `docking_box` / `docking_parameters` | 实际使用的盒与参数快照 |
| `started_at` / `finished_at` / `runtime_seconds` | 时间记录 |
| comparison | 批次内相对指标（`POST /api/comparison`，含 `normalization_method` 与 disclaimer） |
| provenance | 每分子 `provenance`：meeko 版本、PDBQT 工具、力场、Vina 引擎；manifest 记录全部哈希 |

### 7.2 JSON 示例（真实运行摘录，乙醇单分子，seed=42）

```json
{
  "job_id": "20260805-041920_single_ligand_ethanol",
  "job_name": "single_ligand_ethanol",
  "status": "SUCCESS",
  "state": "SUCCESS",
  "results": [
    {
      "ligand_id": "ethanol",
      "status": "SUCCESS",
      "best_affinity_kcal_mol": -2.776,
      "poses": [
        {
          "rank": 1,
          "affinity_kcal_mol": -2.776,
          "rmsd_lb": 0.0,
          "rmsd_ub": 0.0,
          "pose_file": "poses/ethanol/pose_001.pdbqt",
          "pose_pdb_file": "poses/ethanol/pose_001.pdb"
        }
      ],
      "ligand_efficiency": 0.9253,
      "descriptors": {
        "molecular_formula": "C2H6O",
        "heavy_atom_count": 3,
        "MolWt": 46.069,
        "LogP": -0.001,
        "TPSA": 20.23,
        "HBD": 1,
        "HBA": 1,
        "rotatable_bonds": 0
      },
      "preparation_warnings": [],
      "warnings": [],
      "artifacts": {
        "sdf": "ligands/ethanol/ligand.sdf",
        "pdb": "ligands/ethanol/ligand.pdb",
        "pdbqt": "ligands/ethanol/ligand.pdbqt"
      },
      "provenance": {
        "meeko_version": "0.7.1",
        "pdbqt_tool": "meeko python api",
        "force_field_used": "MMFF94",
        "vina_engine": "vina python api"
      },
      "structured_error": null
    }
  ],
  "structured_error": null
}
```

注意：**单分子批次**中比较类维度（雷达图 `affinity` / `ligand_efficiency`
的批内归一值）为 `null`——不存在批内参照时不虚构分数
（`backend/app/api/comparison.py`）。
