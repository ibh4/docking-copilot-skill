# 安全（SECURITY）

本文描述本流程在文件、输入、执行三个层面的防护；实现位于
`backend/app/utils/files.py`、`backend/app/config.py` 与各 service。

## 1. 文件访问控制（路径沙箱）

- **`safe_resolve(path, root)`**：所有用户提供的路径（受体 PDB 等）都经
  `resolve()` 规范化后校验是否位于项目根之内；`../` 路径穿越、符号链接
  逃逸一律抛出 `PathTraversalError`，统一以 `INPUT_VALIDATION_FAILED`
  结构化错误拒绝（见失败案例 `ARTIFACT_ACCESS_DENIED`）。
- **产物只写任务目录**：每次运行的全部产物写入
  `outputs/<job_id>/`，不修改输入文件，不写系统目录。
- 不存在用户输入直接拼接 shell 路径的执行路径；Vina CLI 调用使用
  参数列表形式（非 shell 字符串插值）。

## 2. 输入校验（防恶意/畸形输入）

| 防线 | 机制 |
| --- | --- |
| 结构校验 | Pydantic `DockingInput` 严格模式：字段类型、Literal 枚举、必填项 |
| JSON Schema | `schemas/*.schema.json`（与 Pydantic 同源导出）供外部系统双重校验 |
| 体积限制 | 单文件上限 20 MB（`UPLOAD_MAX_MB`），防止超大 PDB 拖垮解析 |
| 批量限制 | 配体数 ≤ 20（`BATCH_MAX_LIGANDS`），防止批量资源耗尽 |
| 元素白名单 | 配体仅允许 H,B,C,N,O,F,Si,P,S,Cl,Br,I，拒绝任意金属/未知元素 |
| box 上限 | 边长 ≤ 30 Å、体积 ≤ 27000 Å³，限制搜索空间与计算量 |

## 3. 执行隔离与资源限制

- **Vina Python API 子进程隔离**：Vina C++ 层遇到损坏 PDBQT 会直接
  `SIGABRT` 杀死进程。因此 Python API 对接在**独立子进程**中执行
  （`vina_service.py`），崩溃只影响子进程，主进程捕获后受控回退 CLI，
  仍失败则报 `VINA_FAILED`（两个适配器的错误都保留在 details）。
- **PDBQT 预校验**：`validate_pdbqt_files` 在对接前检查受体/配体
  PDBQT 的存在性、非空与必要 section（ATOM / ROOT / TORSDOF），
  快速失败且错误可诊断。
- **超时保护**：单配体对接超时 300 s（`DOCKING_TIMEOUT_SECONDS`），
  超时终止并报 `VINA_TIMEOUT`。
- **CPU 上限**：`cpu` 参数上限 8（`CPU_MAX`），防止单机资源耗尽。

## 4. 已知边界

- 本流程为**单机科研工具**，不含用户认证/多租户隔离；API 服务层
  （FastAPI）默认仅监听 `127.0.0.1`，不直接暴露公网；
- 不执行任何用户提供的可执行代码/脚本；用户输入只有 SMILES 字符串、
  JSON 参数与 PDB 文件，均经上述解析器处理；
- 输出（report/bundle.zip）不包含输入之外的系统信息；manifest 记录
  版本号用于审计，不含凭据类信息。

## 5. 故障即结构化错误

任何安全相关拒绝（路径越界、超限、畸形输入）都转化为
`StructuredError`（含 `suggested_actions`），不泄露内部堆栈细节给
最终报告，同时完整日志保留在 `outputs/<job_id>/logs/` 供排查。
