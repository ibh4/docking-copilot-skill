# 失败案例（FAILURE CASES）

13 个失败案例位于 `examples/failure_cases/<code>/`，每案例含：

- `input.json` — 可被 `DockingInput.model_validate` 接受的输入（结构合法，语义触发失败）；
- `expected.json` — 期望的 `error_code` / `stage` / `recoverable` / `suggested_actions` 与备注；
- 必要时附损坏/辅助文件（如 `corrupt_ligand.pdbqt`、空 PDB）。

再生成全部案例：`make failure-cases`（`scripts/generate_failure_cases.py`）。
自动化回归：`backend/tests/test_failures.py`（逐案例真实运行 `run_job` 并断言结构化错误）。

## 案例总表

| 案例目录 | error_code | 阶段（stage） | 可恢复 | 触发条件 | 建议动作 | 对应测试 |
| --- | --- | --- | --- | --- | --- | --- |
| `INVALID_SMILES` | INVALID_SMILES | prepare_ligand | 否 | SMILES 语法非法（JSON 结构本身合法，化学合法性在准备阶段拒绝） | 检查 SMILES 语法 | `test_case_invalid_smiles` |
| `MULTI_FRAGMENT_LIGAND` | MULTI_FRAGMENT_LIGAND | prepare_ligand | 否 | 盐/混合物等多片段分子（不相连片段 > 1） | 保留最大片段或拆分输入 | `test_case_multi_fragment_ligand` |
| `UNSUPPORTED_ELEMENT` | UNSUPPORTED_ELEMENT | prepare_ligand | 否 | 含 Vina 原子类型表之外的元素（如金属配合物） | 只用 H,B,C,N,O,F,Si,P,S,Cl,Br,I | `test_case_unsupported_element` |
| `CONFORMER_GENERATION_FAILED` | CONFORMER_GENERATION_FAILED | prepare_ligand | 是 | 3D 嵌入失败（测试中经 mock 触发；真实超大刚性分子的嵌入失败难以稳定构造，已在 expected.json notes 如实说明） | 降低环复杂度或增加候选构象数 | `test_case_conformer_generation_failed` |
| `INVALID_RECEPTOR` | INVALID_RECEPTOR | analyze_receptor | 否 | 空 PDB / 无 ATOM 记录 | 提供非空且含 ATOM 记录的 PDB | `test_case_invalid_receptor` |
| `CHAIN_NOT_FOUND` | CHAIN_NOT_FOUND | prepare_receptor | 是 | `selected_chains` 指定不存在的链（样例受体仅有链 A；`details.available_chains` 列出可选链） | 从可用链中选择 | `test_case_chain_not_found` |
| `RECEPTOR_PREPARATION_FAILED` | RECEPTOR_PREPARATION_FAILED | prepare_receptor | 否 | PDB 可解析但残基全部为未知残基名（XXX），Meeko 严格模式与回退均失败 | 提供标准残基的结构有效受体 | `test_case_receptor_preparation_failed` |
| `BOX_OUTSIDE_RECEPTOR` | BOX_OUTSIDE_RECEPTOR | validate_box | 是 | explicit box 与受体包围盒无交集 | 将盒中心移向受体包围盒 | `test_case_box_outside_receptor` |
| `BOX_TOO_LARGE` | BOX_TOO_LARGE | validate_box | 是 | `whole_receptor` 模式边长超 30 Å（样例受体包围盒约 53×41×54 Å） | 减小 padding、改用 residue_list/reference_ligand | `test_case_box_too_large` |
| `VINA_FAILED` | VINA_FAILED | run_vina | 否 | 损坏的配体 PDBQT：Python API 子进程崩溃/失败后受控回退 CLI，CLI 同样失败（双适配器错误均保留在 details） | 检查 PDBQT 完整性，用 Meeko 重新生成 | `test_case_vina_failed` |
| `NO_POSE` | NO_POSE | parse_scores | 是 | 输出中无 `REMARK VINA RESULT`（真实运行中合法 box 下 Vina 总会产 pose，测试经 mock `dock_one` 复现，已在 notes 如实说明） | 检查盒位置与配体 PDBQT | `test_case_no_pose` |
| `PARTIAL_BATCH_FAILURE` | INVALID_SMILES（失败分子 broken_one 的错误） | prepare_ligand | 否（该分子） | 批量 3 分子中 1 个 SMILES 非法：**任务整体 SUCCESS**，失败分子记 FAILED 并写入其 `LigandResult.structured_error`，其余照常对接 | 在 reports/result.json 中查看逐分子 structured_error | `test_case_partial_batch_failure` |
| `ARTIFACT_ACCESS_DENIED` | INPUT_VALIDATION_FAILED | analyze_receptor | 否 | 受体路径 `../../etc/passwd` 越出项目目录，被 `safe_resolve` 拒绝（PathTraversalError），错误码统一为 INPUT_VALIDATION_FAILED | 受体路径必须位于项目目录内 | `test_case_artifact_access_denied` |

## 说明

1. **结构化错误**：所有失败统一以 `StructuredError`（error_code / stage / message /
   details / recoverable / suggested_actions）写入 `job.json` 与
   `reports/result.json`，机器可读、无自由文本歧义。
2. **可恢复（recoverable）语义**：`true` 表示用户修改输入后可直接重跑；
   `false` 表示输入本身不满足前提（但不代表永远无法处理，例如换一份合法 SMILES）。
3. **两个 mock 案例**（CONFORMER_GENERATION_FAILED、NO_POSE）在
   `expected.json.notes` 中明确标注了使用 mock 的原因，不做虚假的"真实触发"声明。
4. **批量语义**：`PARTIAL_BATCH_FAILURE` 演示"单分子失败不拖垮整批"的设计；
   前端/API 消费方应逐分子检查 `status` 而不是只看任务级 status。
5. **错误码全集**：`backend/app/schemas.py` 的 `ErrorCode` 常量类还包含
   `INVALID_BOX`、`LIGAND_TOO_LARGE`、`PDBQT_PREPARATION_FAILED`、
   `VINA_TIMEOUT`、`FILE_NOT_FOUND`、`INTERNAL_ERROR` 等，
   由 schema 约束、超时与内部保护路径覆盖，测试见 `test_failures.py` 既有断言。
