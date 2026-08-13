# 提交前质检报告（pre_submission_check）

- 生成时间: 2026-08-07T17:18:34.729298+00:00
- 结果: PASS 6 / WARNING 1 / FAIL 0
- 结论: 可以提交

| 检查 | 状态 | 详情 |
| --- | --- | --- |
| 文档路径存在性 | PASS | SKILL/README/SUBMISSION 引用的 75 个路径均存在 |
| Makefile 目标一致性 | PASS | 文档引用的 make 命令均在 Makefile 定义（目标: backend, check, clean, dag, dev, example, failure-cases, frontend, reproducibility, schemas, test, web） |
| schemas/ 与 Pydantic 一致 | PASS | 4 个 JSON Schema 与 backend/app/schemas.py 导出完全一致 |
| 失败案例与测试对应 | PASS | 13 个案例目录均含 input.json/expected.json，test_failures.py 含 14 个 test_case_* 测试 |
| 敏感信息扫描 | PASS | 扫描 174 个提交文件，未发现 /Users 路径、API key、token、密码 |
| 大文件/产物隔离 | PASS | 提交文件均 ≤1MB；node_modules/ 与 outputs/ 已在 .gitignore 排除 |
| repository_size | WARNING | 无法统计（非 git 仓库或 git 不可用） |
