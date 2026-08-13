# SUBMISSION — DockingCopilot Skill


## GitHub 路径最终确认

主办方自动评审入口必须是仓库根目录下的：

```text
skills/docking-copilot/SKILL.md
```

并满足：

- `skills/` 下只有一个 Skill 目录：`docking-copilot/`；
- `SKILL.md` frontmatter 含 `name` 与 `description`；
- 目录名 `docking-copilot` 与 frontmatter `name: docking-copilot` 完全一致；
- GitHub 仓库已邀请 `synmatai-hackathon` 为 Collaborator；
- 上传后运行 `python skills/docking-copilot/scripts/validate_submission.py`，应输出 `OFFICIAL_SUBMISSION_CHECK_PASS`。

**一句话定位**：DockingCopilot Skill 将 SMILES、小分子三维构建、蛋白受体准备、
对接参数校验、AutoDock Vina 计算、结果解释和多分子比较封装为可复现科研
Skill，并提供 Schema、Notebook、DAG、失败诊断、产物追踪及网页三维可视化。

- **对应赛题**：AI4S Future ScienceSkills Hackathon — AI for Biomedicine 赛道：
  面向虚拟筛选、分子对接、自由能计算或蛋白/小分子工作流，完成配置、
  脚本生成、参数校验与结果解释。最终交付物为一个完整、可复用的 Skill 文档。
- **Skill 文档路径**：[`skills/docking-copilot/SKILL.md`](skills/docking-copilot/SKILL.md)（官方主交付物）
- **License**：MIT（`LICENSE` / `CITATION.cff`）

## 最短验证命令

官方 Linux 沙箱优先：

```bash
python -m pip install -r requirements.txt
python skills/docking-copilot/scripts/validate_submission.py   # OFFICIAL_SUBMISSION_CHECK_PASS
python skills/docking-copilot/scripts/check_runtime.py         # DOCKING_SKILL_RUNTIME_PASS
python skills/docking-copilot/scripts/run_example.py           # RUN_EXAMPLE_PASS
pytest -q backend/tests
```

Mac mini M4 本地开发仍可使用：

```bash
mamba env create -f environment.yml && conda activate dockskill
make check
make example
make test
make reproducibility
```

## 主要产物路径

| 产物 | 路径 |
| --- | --- |
| Skill 文档（主交付物） | `skills/docking-copilot/SKILL.md` |
| 输入/输出/比较/错误 JSON Schema（4 个） | `schemas/*.schema.json` |
| 工作流 DAG（mmd/json/svg，13 节点与 runner 一致） | `dags/` |
| 可复现 Notebook（含真实输出） | `notebooks/docking_skill_demo.executed.ipynb`（+ `.md` 导出） |
| 失败案例（13 个，含 expected.json） | `examples/failure_cases/` |
| 示例输入（3 个真实输入） | `examples/inputs/` |
| 真实运行结果摘要 | `examples/expected_outputs/result_summary.json` |
| 文档（8 篇） | `docs/` |
| 后端（schemas + services + 12 态状态机 + FastAPI 16 端点） | `backend/app/` |
| 测试（109 用例） | `backend/tests/` |
| 前端 Demo（React + 3Dmol.js + ECharts，8 组件） | `frontend/src/` |
| 机器可读证据 | `reports/`（environment_check / reproducibility_report / test_report / example_run / pre_submission_check / final_audit / submission_summary / requirement_matrix / automated_judge_readiness） |

## 测试结果

- pytest：**109 passed**（`make test`，含 13 个失败案例回归），证据
  `reports/test_report.json`；
- 环境自检：12 PASS / 0 WARNING / 0 FAIL（`reports/environment_check.json`）；
- Mac M4 参考示例：乙醇 best_affinity **-2.776 kcal/mol**（seed=42）、9 poses；不同 Linux 构建允许出现小幅数值差异，评测以成功状态、结构化输出与可复现记录为准；
  非法 SMILES 返回 `INVALID_SMILES` 结构化错误（`reports/example_run.json`）；
- 可复现：双跑分数一致、全部确定性产物哈希一致，
  `REPRODUCIBILITY_PASS`（`reports/reproducibility_report.json`）；
- 多分子示例真实结果：methane -0.896 / benzene -4.526 / acetic_acid -3.542
  kcal/mol（`examples/expected_outputs/result_summary.json`）；
- 前端：`npm run lint`（--max-warnings 0）与 `npm run build` 零错误。

## 已知限制（如实声明）

- docking score 为经验打分：非药效、非精确自由能、不等于 Kd/Ki/IC50，
  仅同受体/同准备/同 box/同参数下批内相对比较有意义（`skills/docking-copilot/SKILL.md` 的科学边界章节）；
- 静态刚性受体、无显式溶剂、质子化采用工具默认策略；
- 失败案例中 `CONFORMER_GENERATION_FAILED` 与 `NO_POSE` 经 mock 触发
  （真实场景难以稳定构造，已在其 expected.json notes 如实标注），
  其余 11 个案例全部真实触发；
- 样例受体准备触发 Meeko `--allow_bad_res` 受控回退（18 个未匹配模板残基
  被移除）并有缺失残基缺口警告，均如实记录在结果 warnings 中；
- 本地开发环境为 macOS arm64 + conda-forge；官方评审使用 Linux Docker（2 核 / 4 GB / 无 GPU / 900 秒）；批量上限 20 个分子，
  非高通量筛选工具。

## Demo 启动

```bash
make backend    # 终端 1：FastAPI http://127.0.0.1:8000（仅本机监听）
make frontend   # 终端 2：http://localhost:5173（首次 cd frontend && npm install）
```

Demo 仅辅助展示（3Dmol.js 三维 + ECharts 雷达图 + 候选切换），
科学结论以 `outputs/<job_id>/reports/result.json` 与 result.md 为准。

## 需求完成矩阵

见 `reports/requirement_matrix.json`（机器可读）与 `skills/docking-copilot/SKILL.md` 的自动评审证据章节；逐项含实现状态、证据路径与验证命令。

## 仓库体积声明（当前赛规：提交包 ≤50MB，单文件 ≤10MB）

- 实测（2026-08-05）：被跟踪文件 186 个共 **2.20 MB**；`du -sh .git` = **3.0 MB**
  （`git count-objects -vH`：loose 328 个对象 2.84 MiB）；
  低于当前 50MB 提交包上限。
- 本仓库**不含任何大型数据集**：最大随附数据为 `examples/data/sample_receptor.pdb`
  （单文件 < 1 MB，来源见 `examples/data/DATA_PROVENANCE.md`）；
  `outputs/` 运行产物与前端构建产物均不入 git（`.gitignore`）。
- 预案：若未来引入超过 50MB 提交包限制的数据集，将不直接入仓，而是按赛规要求
  在提交材料中注明数据集的下载方式与来源、附数据说明文档，并提供 Demo
  作品链接；当前仓库尚无在线 Demo，该预案仅在需要时启用。

## 提交前质检

`scripts/pre_submission_check.py` 输出 `reports/pre_submission_check.json/.md`：
文档路径存在性、Makefile 目标一致性、JSON Schema 与 Pydantic 一致性、
失败案例-测试对应、敏感信息扫描、大文件检查、仓库体积检查
（repository_size，阈值 45MB = 50MB 上限留 5MB 余量）。
