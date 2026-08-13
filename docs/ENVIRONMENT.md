# 环境说明（ENVIRONMENT）

## 目标设备

- Mac mini M4（Apple Silicon arm64），macOS 26.5.2，16GB 内存
- 无 NVIDIA CUDA；AutoDock Vina 纯 CPU 运行；不启用 Rosetta 2

## Python 环境

- 环境管理器：Miniforge（conda 26.3.2）+ mamba 2.5.0，路径
  `/opt/homebrew/Caskroom/miniforge/base`
- 环境名：`dockskill`（Python 3.11.15），全部依赖来自 `conda-forge`，
  **单事务求解成功，未使用任何 pip 覆盖安装**（含 meeko，无需 fallback）。
- 复现命令：

```bash
mamba env create -f environment.yml
conda activate dockskill
```

或一键创建（与本机实测一致）：

```bash
mamba create -n dockskill -c conda-forge python=3.11 rdkit vina meeko openbabel \
  numpy pandas scipy scikit-learn matplotlib plotly networkx biopython \
  pydantic fastapi uvicorn python-multipart jinja2 pyyaml jsonschema \
  jupyterlab ipykernel pytest pytest-cov httpx rich typer
```

## 关键组件版本（2026-08-05 实测）

| 组件 | 版本 | 验证方式 |
| --- | --- | --- |
| RDKit | 2025.09.5 | 解析 CCO + 3D conformer + MMFF + SDF + 描述符 |
| Meeko | 0.7.1 | `mk_prepare_ligand.py --help`；SDF→PDBQT 实测成功 |
| AutoDock Vina | 1.2.7 | CLI `vina --version` 与 Python API `from vina import Vina` 均可用 |
| Open Babel | 3.1.1（`obabel -V` 报 3.1.0） | SDF→PDB 转换实测成功 |
| FastAPI | 0.141.1 | 最小服务 GET /health 返回 200，关闭后无僵尸进程 |
| JupyterLab | 4.6.2 | kernelspec `dockskill` 已注册 |
| Node.js | v22.22.2（原生 arm64） | 前端由后续任务初始化 |

注意：conda-forge 的 meeko 0.7.1 命令行入口带 `.py` 后缀
（`mk_prepare_ligand.py` / `mk_prepare_receptor.py`），与 pip 安装
（`mk_prepare_ligand`）不同，代码调用时两个名字都要探测。

## Jupyter kernel

```bash
python -m ipykernel install --user --name dockskill
```

`notebooks/docking_skill_demo.ipynb` 使用 `dockskill` kernel 真实执行：

```bash
conda run -n dockskill jupyter nbconvert --to notebook --execute \
  notebooks/docking_skill_demo.ipynb \
  --output docking_skill_demo.executed.ipynb
```

执行结果存为 `notebooks/docking_skill_demo.executed.ipynb`，
并导出 `notebooks/docking_skill_demo.executed.md`；notebook 内部只用
相对路径（`PROJECT_ROOT = Path.cwd().parent`），依赖 Makefile 的
`PYTHONPATH` 约定（backend/ 在路径上）。

## 自检

```bash
make check        # 或 python scripts/check_environment.py
```

输出 `reports/environment_check.json` 与 `reports/environment_check.md`；
无 FAIL 时打印唯一标记 `DOCKING_SKILL_CHECK_PASS`。

## 16GB 内存约束

资源上限集中在 `backend/app/config.py`：workers=1、对接并发 1、
批量分子 ≤20、上传 ≤20MB、box 单边 10–30 Å、体积 ≤27000 Å³、
对接超时 300s、CPU 默认 4（上限 8）。

## 备用解释器 / 二进制

- `/opt/homebrew/bin/python3.11`（3.11.15）可作 fallback 解释器。
- Vina 探测顺序：环境内 `vina` → `vendor/bin/vina`（见 config.py）。
