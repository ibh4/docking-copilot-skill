# 最终质检报告（final_audit）

- 项目：DockingCopilot Skill（AI for Biomedicine）
- 生成时间：2026-08-05
- 依据：提示词 12「提交前仓库质检与修复」；机器可读版本见 `final_audit.json`

## 结论

**PASS 22 项 / WARNING 2 项 / FAIL 0 项 — 建议提交。**

## PASS 项（摘要）

1. `SKILL.md` 主交付物：23 节，命令/路径/字段与仓库逐项核对一致；
2. README / SUBMISSION / LICENSE / CITATION.cff 齐全；
3. environment.yml / requirements.txt / pyproject.toml 一致（Python 3.11）；
4. 4 个 JSON Schema 与 Pydantic 完全一致（`scripts/pre_submission_check.py` 实测）；
5. Notebook 已执行副本含真实输出，无绝对路径；
6. DAG 三件套与 runner/状态机一致（test_dag.py 断言）；
7. 失败案例 13 个（≥10），全部被 test_failures.py 真实运行断言；
8. 结果解释与雷达图归一化公式文档化，`normalization_method` 机器可查；
9. pytest 109/109 通过（`reports/test_report.json`）；
10. `make check` → `DOCKING_SKILL_CHECK_PASS`（12 PASS / 0 WARNING / 0 FAIL）；
11. `make example` → `RUN_EXAMPLE_PASS`（乙醇 -2.776 kcal/mol，seed=42，真实对接）；
12. `make reproducibility` → `REPRODUCIBILITY_PASS`（双跑分数与产物哈希一致）；
13. 示例数据小（156KB）、合法、有来源说明（DATA_PROVENANCE.md 含 sha256）；
14. 前端 lint（--max-warnings 0）与 build（tsc+vite）零错误；
15. 16 API 端点、串行队列、job.json 状态、统一错误 schema；
16. 路径沙箱（ARTIFACT_ACCESS_DENIED 案例真实断言）；
17. 无 shell injection（CLI 全部参数列表调用）；
18. CORS 仅 5173、仅监听 127.0.0.1、错误不泄漏堆栈;
19. 资源上限（20MB/20 分子/box/超时）均有测试；
20. Makefile 自动入口不依赖联网与 API Key；
21. reports/ 机器可读 JSON 全部合法且引用真实产物；
22. 敏感信息扫描通过（无 /Users、API key、token、密码）。

## WARNING 项

1. **两个 mock 失败案例**：`CONFORMER_GENERATION_FAILED` 与 `NO_POSE` 经 mock
   触发（真实场景难以稳定构造）；已在 `expected.json.notes`、
   `docs/FAILURE_CASES.md`、`SKILL.md` §13/§18 如实标注。其余 11 个案例全部
   真实触发。
2. **样例受体非公开数据库结构**：为课题组自有结构（来源与 sha256 见
   `examples/data/DATA_PROVENANCE.md`），准备阶段触发 Meeko `--allow_bad_res`
   受控回退（18 个残基被移除）并有缺失残基警告——均如实记录在每次运行的
   warnings 中，仅用于流程演示，不代表真实药物靶点。

## FAIL 项

无。

## 本次质检实际修复记录

- `SKILL.md` 3 处 job 内相对路径补全为 `outputs/<job_id>/reports/` 前缀；
- `scripts/check_environment.py` 输出相对化（消除环境报告中的 /Users 绝对路径）；
- notebooks 已执行副本中残留绝对路径相对化；
- `reports/example_run.json` stdout 捕获相对化；
- `outputs/` 清理至 3 个被证据引用的 job 目录；
- 删除根目录临时文件（reports_example_run.txt、pytest_full.log）。

## 仍需人工完成

1. 在 GitHub 私有仓库邀请指定评审账号（网页操作）；
2. 如需全新机器复核：`mamba env create -f environment.yml` 后依次
   `make check` / `make example` / `make test`。
