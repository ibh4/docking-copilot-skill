# 可复现性、产物、Notebook 与 Web Demo 详细参考

## 14. Reproducibility

见 `docs/REPRODUCIBILITY.md`；验证命令 `make reproducibility`
（`scripts/verify_reproducibility.py`，双跑 `examples/inputs/single_ligand.json`）。

| 机制 | 说明 |
| --- | --- |
| seed | `docking_parameters.seed` 与 `ligand_preparation.random_seed` 默认均 42 |
| package versions | manifest 记录 `vina_version` / `rdkit_version` / `meeko_version` / `python_version` / 平台 |
| hashes | `input_sha256` / `receptor_sha256` / 每配体 `ligand_sha256` 与全部产物 `artifact_sha256` |
| manifest | `outputs/<job_id>/manifest.json`：输入、参数、seed、命令/API 调用序列、产物哈希 |
| artifact bundle | `outputs/<job_id>/bundle.zip`（含 top-3 pose） |
| notebook | `notebooks/docking_skill_demo.executed.ipynb`（含全部真实输出） |
| 重复运行验证 | 最近一次（2026-08-05）：乙醇双跑 best_affinity 均为 **-2.776 kcal/mol**，全部确定性产物哈希一致 → `REPRODUCIBILITY_PASS`，报告 `reports/reproducibility_report.json` |
| 已知非确定性 | `result.json` / `result.md` / `comparison.csv` 内嵌 job_id 与时间戳，不参与哈希比对；分数容差 ±0.01 kcal/mol |

## 15. Artifacts

每次任务写入 `outputs/<job_id>/`（目录树，真实运行实测）：

```text
outputs/<job_id>/
├── input.json                 # 规范化后的输入快照
├── manifest.json              # 哈希、版本、参数、命令记录（可复现核心）
├── job.json                   # 状态机轨迹（API 轮询读取）
├── logs/workflow.log          # 逐步日志
├── ligands/<ligand_id>/       # ligand.sdf / ligand.pdb / ligand.pdbqt /
│                              # ligand_2d.svg / ligand_metadata.json / vina_output.pdbqt
├── receptor/                  # receptor_clean.pdb（清洗后受体）/ receptor.pdbqt /
│                              # receptor_original.pdb / receptor_preparation_report.json
├── poses/<ligand_id>/         # pose_NNN.pdbqt / pose_NNN.pdb（num_modes 个）
├── reports/                   # result.json / result.md / comparison.csv
└── bundle.zip                 # 全量产物打包
```

## 16. Notebook

- 路径：`notebooks/docking_skill_demo.ipynb`（可重跑源）；
  已执行副本 `notebooks/docking_skill_demo.executed.ipynb` +
  导出 `notebooks/docking_skill_demo.executed.md`；
- 输入：`examples/inputs/multiple_ligands.json`（methane / benzene / acetic_acid）
  与 `examples/data/sample_receptor.pdb`，全部相对路径；
- 执行顺序（15 步）：环境与版本 → 加载输入 → Pydantic + jsonschema 双重校验 →
  配体准备（含 2D 图）→ 受体分析 → box → `run_job` 真实对接 → top poses →
  描述符 → 批次比较 → 2D/3D 路径与雷达图 → result.md 解释 → 科学限制 →
  manifest → 产物列表；
- 预期输出：对接 SUCCESS，benzene best_affinity = -4.526 kcal/mol
  （seed=42 可复现）；全部 cell 有真实执行输出；
- 运行时长取决于硬件，不做承诺；
- 验证成功：末 cell 打印产物文件列表且无异常；`make check` 中 Jupyter
  kernelspec `dockskill` 为 PASS。

## 17. Web Demo（辅助，不属于科学结论本身）

- 一键启动（推荐）：`make web` —— 检测 8000/5173 端口，服务未启动则按与
  `make backend` / `make frontend` 相同的方式后台启动（后端带
  `PYTHONPATH=backend`，前端 stdin 重定向 `/dev/null` 防 SIGTTIN，日志写入
  `outputs/logs/`），随后 `open http://localhost:5173` 自动弹出浏览器；
  服务已在运行时只打开浏览器（幂等，不重启）；无浏览器环境退化为仅打印
  Markdown 链接，退出码仍为 0（实现：`scripts/open_demo.sh`）；
- 手动启动：两个终端分别 `make backend`（127.0.0.1:8000）与
  `make frontend`（http://localhost:5173）；首次需 `cd frontend && npm install`；
- 主要页面：输入面板（SMILES/受体/参数表单）→ 状态步进器（12 态）→
  结果表格 → 3D 视图 → 雷达图 → 失败面板；组件位于 `frontend/src/components/`
  （InputPanel / StatusHeader / WorkflowStepper / ResultTable / MoleculeList /
  Viewer3D / RadarChart / FailurePanel，共 8 个）；
- 3D：3Dmol.js 渲染 ligand / receptor / docked complex，候选分子点击切换；
- 雷达图：ECharts，五维与后端 `RADAR_DIMENSIONS` 一致，同屏展示原始数值；
- 后端约束：单一后台线程串行队列，job 状态由 `outputs/<job_id>/job.json`
  文件承载，CORS 仅允许 `http://localhost:5173` / `http://127.0.0.1:5173`，
  默认只监听 127.0.0.1（`backend/app/main.py`）；
- 前端工程：React 18 + Vite 5 + TypeScript，`npm run build`（tsc + vite）
  与 `npm run lint`（--max-warnings 0）零错误；构建产物不入 git
  （`.gitignore`）；
- Demo 仅用于展示与交互，**科学结论以 `outputs/<job_id>/reports/result.json` 与 result.md 为准**。
