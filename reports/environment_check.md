# 环境自检报告

- 生成时间: 2026-08-06T03:29:50.951335+00:00
- 平台: Darwin 25.5.0 arm64
- Python: 3.11.15
- 结果: PASS 12 / WARNING 0 / FAIL 0

| 组件 | 状态 | 详情 |
| --- | --- | --- |
| arm64 | PASS | platform.machine()=arm64 |
| Python | PASS | 3.11.15 (/opt/homebrew/Caskroom/miniforge/base/envs/dockskill/bin/python) |
| RDKit | PASS | rdkit 2025.09.5，可解析 SMILES |
| Vina | PASS | CLI: AutoDock Vina v1.2.7 (/opt/homebrew/Caskroom/miniforge/base/envs/dockskill/bin/vina); Python API 可用 |
| Meeko | PASS | meeko 0.7.1; CLI: /opt/homebrew/Caskroom/miniforge/base/envs/dockskill/bin/mk_prepare_ligand.py |
| OpenBabel | PASS | Open Babel 3.1.0 -- Nov 30 2023 -- 21:04:48 |
| FastAPI | PASS | fastapi 0.141.1 |
| Jupyter | PASS | kernelspec 'dockskill' 已注册 |
| Node | PASS | v22.22.2 |
| npm | PASS | npm 10.9.7 |
| 磁盘可写 | PASS | outputs/ 可写（仓库内相对路径：outputs） |
| 目录可创建 | PASS | 可在 outputs/ 下创建并删除 job 子目录（outputs, reports 存在） |
