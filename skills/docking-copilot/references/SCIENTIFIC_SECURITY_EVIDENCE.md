# 科学边界、安全、评测证据与完成矩阵

## 18. Scientific Limitations

与 `docs/SCIENTIFIC_LIMITATIONS.md` 及每次运行 `outputs/<job_id>/reports/result.md` 中的
固定限制声明一致：

1. **打分不是自由能，更不是药效**：Vina affinity 是经验打分函数与构象搜索
   的结果；不能换算 Kd/Ki/IC50；分数排序 ≠ 活性排序；
2. **静态刚性受体**：不考虑诱导契合、侧链重排、主链运动；默认去水，
   无显式溶剂效应；
3. **质子化与互变异构**：`protonation_policy=tool_default`，无 pH 显式建模；
   组氨酸互变异构、局部 pKa 偏移未处理；
4. **box 选择偏差**：真实结合位点不在 box 内时"最优 pose"无意义；
   示例盒中心取受体几何中心（见 `examples/data/DATA_PROVENANCE.md`），
   仅为流程演示，不代表真实结合位点；
5. **采样与 pose 不确定性**：启发式搜索；分数接近（<1 kcal/mol）的 pose
   不可区分；`rmsd_lb/ub` 为自参照量；
6. **分数跨体系不可比**：受体/链选择/box/质子化/参数任一不同即不可比；
7. **示例受体的已知警告**：样例受体准备触发 Meeko `--allow_bad_res` 受控
   回退（18 个未匹配模板的残基被移除）并存在缺失残基缺口
   （A:609->636、A:785->791），这些都以 warning 形式记录在每次结果中，
   用于演示警告机制，也说明该示例体系不代表高质量晶体结构；
8. **失败案例的 mock 说明**：`CONFORMER_GENERATION_FAILED` 与 `NO_POSE`
   两个案例在测试中经 mock 触发（真实场景难以稳定构造），已在其
   `expected.json.notes` 中如实标注，其余 11 个案例全部真实触发；
9. **不替代 MD、FEP 与实验**；本工具输出仅用于假设生成、候选排序与教学；
10. **不用于医疗建议**。

**领域知识与数据来源声明（赛规：不提供专业领域知识库或标准答案）**：
本 Skill 不依赖任何官方提供的领域知识库或标准答案；解释模板（result.md
固定措辞）与科学限制文案由选手基于公开文献与领域经验自主整理，主要
知识来源为 AutoDock Vina（https://autodock-vina.readthedocs.io）与 RDKit
（https://www.rdkit.org/docs）的公开文档及通用计算化学教材性知识；
示例受体数据为项目自有文件（见 `examples/data/DATA_PROVENANCE.md`），
数据收集与内容创作均由选手自主完成。

## 19. Security and Privacy

实现：`backend/app/utils/files.py`、`backend/app/utils/security.py`、
`backend/app/config.py`；完整说明 `docs/SECURITY.md`。

- **本地运行**：API 默认仅监听 `127.0.0.1`；不上传任何数据到外部服务；
- **文件限制**：上传 ≤ 20 MB；产物只写 `outputs/<job_id>/`；
  files 端点仅允许白名单扩展名（`ALLOWED_FILE_EXTENSIONS`，
  `backend/app/api/artifacts.py`）；
- **路径限制**：所有用户路径经 `safe_resolve` 限制在项目根内，
  穿越/符号链接逃逸拒绝（失败案例 `ARTIFACT_ACCESS_DENIED`）；
- **禁止 shell injection**：Vina/Meeko CLI 全部用参数列表调用，
  无 `shell=True` 拼接用户输入；
- **日志不记录敏感信息**：manifest 仅含版本/哈希/参数；错误响应不含堆栈；
- **清理任务产物**：`DELETE /api/jobs/{job_id}` 删除 job 目录；
  `make clean` 清理 Python 缓存；outputs/ 不入 git（`.gitignore`）。

## 20. Evaluation Evidence

| 证据 | 路径 | 验证命令 |
| --- | --- | --- |
| pytest：109 个用例全部通过 | `backend/tests/`（9 个测试文件） | `make test` |
| 环境自检：12 PASS / 0 WARNING / 0 FAIL | `reports/environment_check.json` / `.md` | `make check` |
| 示例成功：乙醇 -2.776 kcal/mol + INVALID_SMILES 结构化错误 | `reports/example_run.json`、`examples/expected_outputs/result_summary.json` | `make example` |
| 失败案例：13 个目录，逐案例被测试断言 | `examples/failure_cases/`、`backend/tests/test_failures.py` | `make test` |
| 可复现报告：REPRODUCIBILITY_PASS | `reports/reproducibility_report.json` / `.md` | `make reproducibility` |
| Schema 校验：4 个 JSON Schema 与 Pydantic 同源导出 | `schemas/*.schema.json`、`backend/tests/test_schemas.py` | `make schemas` |
| DAG 一致性测试 | `backend/tests/test_dag.py` | `make test` |
| 前端 build/lint 零错误 | `frontend/package.json`（`npm run build` / `npm run lint`） | `cd frontend && npm run build` |
| 提交前质检 | `reports/pre_submission_check.json` / `.md` | `python scripts/pre_submission_check.py` |

## 21. Quick Evaluation for Automated Judge

最短评审路径（无需打开网页、无需联网、无需 API Key）：

```bash
make check       # 预期最后一行: DOCKING_SKILL_CHECK_PASS（退出码 0）
make example     # 预期最后输出: RUN_EXAMPLE_PASS（退出码 0）
make test        # 预期: 109 passed（退出码 0）
```

| 命令 | 预期成功标记 | 说明 |
| --- | --- | --- |
| `make check` | stdout 含唯一标记 `DOCKING_SKILL_CHECK_PASS` | 同时写出 `reports/environment_check.json` |
| `make example` | stdout 含唯一标记 `RUN_EXAMPLE_PASS` | 乙醇真实对接（约数秒）+ 非法 SMILES 返回结构化错误 JSON |
| `make test` | pytest 摘要 `109 passed` | 含 13 个失败案例回归 |

补充（可选）：`make reproducibility` → `REPRODUCIBILITY_PASS`。
无 `make` 时的等价 Python 命令见 §9。

## 22. Completion Matrix

| 赛题要求 | 实现状态 | 证据路径 | 验证命令 |
| --- | --- | --- | --- |
| 配置、脚本生成、参数校验 | 完成 | `backend/app/schemas.py`、`backend/app/config.py`、`docs/PARAMETER_GUIDE.md` | `make test`（test_schemas.py） |
| 结果解释 | 完成 | `docs/RESULT_INTERPRETATION.md`、`backend/app/services/interpretation_service.py` | `make example`（result.md） |
| 可复现 notebook | 完成 | `notebooks/docking_skill_demo.executed.ipynb` | §16 |
| 工作流 DAG | 完成 | `dags/workflow.mmd` / `.json` / `.svg`、`backend/tests/test_dag.py` | `make dag` |
| 输入/输出 schema | 完成 | `schemas/*.schema.json`（4 个） | `make schemas` |
| 失败案例（≥10） | 完成（13 个） | `examples/failure_cases/`、`backend/tests/test_failures.py` | `make failure-cases` |
| 真实可复现 docking 示例 | 完成 | `scripts/run_example.py`、`reports/reproducibility_report.json` | `make example` / `make reproducibility` |
| 测试与证据 | 完成（109 用例） | `backend/tests/`、`reports/test_report.json` | `make test` |
| ligand 3D/receptor 3D/complex 3D 网页查看 | 完成 | `frontend/src/components/Viewer3D.tsx` | `make frontend` |
| 点击候选分子切换 pose/分析 | 完成 | `frontend/src/components/MoleculeList.tsx` | 同上 |
| 雷达图比较（方向正确、同批可比） | 完成 | `backend/app/services/comparison_service.py`、`frontend/src/components/RadarChart.tsx` | `make test`（test_comparison.py） |
| 下载 JSON/MD/CSV/结构文件/bundle | 完成 | `backend/app/api/artifacts.py`（白名单扩展名） | `make test`（test_api.py） |
| 16GB 资源约束 | 完成 | `backend/app/config.py` | `make check` |
| Scientific Limitations | 完成 | `docs/SCIENTIFIC_LIMITATIONS.md`、SKILL.md §18 | — |
| 安全（路径沙箱/无 shell injection） | 完成 | `docs/SECURITY.md`、失败案例 ARTIFACT_ACCESS_DENIED | `make test` |
| 自动评审入口 | 完成 | Makefile（check/example/test/schemas） | §21 |

## 23. Citation and Acknowledgement

本 Skill 构建于以下开源工具之上；使用本 Skill 发表成果时请按各工具
自身要求引用：

| 工具 | 用途 | 引用 | 许可证 |
| --- | --- | --- | --- |
| RDKit | SMILES 解析、3D 构象、力场、描述符 | RDKit: Open-source cheminformatics, https://www.rdkit.org （2025.09.5） | BSD-3-Clause |
| AutoDock Vina | 分子对接与经验打分 | Eberhardt J. et al. AutoDock Vina 1.2.0. J. Chem. Inf. Model. 2021, 61, 8, 3631–3641（1.2.7） | Apache-2.0 |
| Meeko | PDBQT 准备（配体/受体） | Forli S. et al. Computational protein–ligand docking and virtual drug screening with the AutoDock suite. Drug Discov. Today 2016（0.7.1） | LGPL |
| Open Babel | PDBQT→PDB 转写 | O'Boyle N.M. et al. Open Babel: An open chemical toolbox. J. Cheminform. 2011, 3, 33（3.1.1） | GPL-2.0 |
| Biopython | 受体结构分析 | Cock P.J.A. et al. Biopython: freely available Python tools for computational molecular biology. Bioinformatics 2009（1.87） | BSD-style |
| 3Dmol.js | 前端 3D 可视化 | Rego N., Koes D. 3Dmol.js. Bioinformatics 2015, 31, 8, 1322–1324 | BSD |
| Apache ECharts | 雷达图/图表 | Apache ECharts, https://echarts.apache.org | Apache-2.0 |
| FastAPI / Pydantic | API 与 schema | https://fastapi.tiangolo.com / https://docs.pydantic.dev | MIT |

本 Skill 自身许可：MIT（见 `LICENSE`）；引用格式见 `CITATION.cff`。

---

*本文档由仓库真实代码与运行证据逐项核对生成；任何声称的功能均可通过
§22 的验证命令复现。docking score 为经验打分，仅同批可比，不构成药效或
自由能结论。*
