# DockingCopilot Skill

<p align="center">
  <b>AI for Biomedicine · Molecular Docking · Reproducible Scientific Skill</b><br>
  从 SMILES 与蛋白受体出发，将分子 3D 构建、受体准备、参数校验、AutoDock Vina 对接、结果解释与多候选比较封装为一条可复现科研工作流。
</p>

<p align="center">
  <img alt="Track" src="https://img.shields.io/badge/Track-AI%20for%20Biomedicine-8B5CF6?style=for-the-badge">
  <img alt="Skill" src="https://img.shields.io/badge/Skill-DockingCopilot-06B6D4?style=for-the-badge">
  <img alt="Docking" src="https://img.shields.io/badge/Docking-AutoDock%20Vina-F59E0B?style=for-the-badge">
  <img alt="3D" src="https://img.shields.io/badge/3D-RDKit%20%2B%203Dmol.js-10B981?style=for-the-badge">
  <img alt="Status" src="https://img.shields.io/badge/Status-Submission%20Ready-22C55E?style=for-the-badge">
</p>
<img width="1908" height="785" alt="ff1c2608152a7156554ec02a4dc86e2" src="https://github.com/user-attachments/assets/1bfb23da-b8dc-46c9-894b-08f15abe76d2" />

> **DockingCopilot Skill** 面向虚拟筛选与分子对接科研场景，将传统分散的计算化学步骤组织为 **输入明确、参数受控、过程可追踪、失败可诊断、结果可解释、运行可复现** 的 Scientific Skill。

> [!IMPORTANT]
> **官方自动评审入口：** `skills/docking-copilot/SKILL.md`  
> `skills/` 下仅保留 `docking-copilot/`，且目录名必须与 `SKILL.md` frontmatter 中的 `name: docking-copilot` 完全一致。  
> 提交前可运行：`python skills/docking-copilot/scripts/validate_submission.py`

核心交付物：[`skills/docking-copilot/SKILL.md`](skills/docking-copilot/SKILL.md)  
提交摘要：[`SUBMISSION.md`](SUBMISSION.md)  
渐进披露参考资料：[`skills/docking-copilot/references/`](skills/docking-copilot/references/)

---

## 0. 项目一句话

**DockingCopilot Skill** 将 **SMILES + Protein PDB + Docking Configuration** 转换为一条经过校验的可复现对接流程，并输出 **3D 配体、受体结构、Docked Poses、Affinity、Ligand Efficiency、结构化解释、失败诊断、Manifest 与可下载产物**。

它不是一个“只返回一个 Vina 分数”的脚本，而是一个可以被科研人员或上层 Agent 直接复用的 **分子对接 Copilot Skill**。

---

## 1. 核心能力

| 能力 | 实现 |
|---|---|
| **Ligand 3D Preparation** | SMILES → RDKit ETKDGv3 → MMFF94 / UFF → SDF / PDB / PDBQT |
| **Receptor Preparation** | Protein PDB 分析、链选择、水/辅因子/金属策略化处理 |
| **Docking Box Validation** | explicit / reference_ligand / residue_list / whole_receptor 四种模式 |
| **Molecular Docking** | AutoDock Vina，固定 seed，可复现单分子与小批量 docking |
| **Scientific Interpretation** | affinity、pose、ligand efficiency、warning、科学边界与恢复建议 |
| **Multi-molecule Comparison** | 同条件候选排序、Relative Docking Profile、雷达图对比 |
| **Reproducibility** | Schema、Notebook、DAG、Manifest、Hash、Version、Failure Cases |
| **Interactive Demo** | FastAPI + React + 3Dmol.js + ECharts，展示完整计算产物 |

---

## 2. 端到端 Scientific Skill 架构

```mermaid
%%{init: {"theme": "base", "themeVariables": {
  "fontFamily": "Inter, Microsoft YaHei, sans-serif",
  "background": "#FFFFFF",
  "primaryTextColor": "#1F2937",
  "lineColor": "#94A3B8",
  "clusterBkg": "#F8FAFC",
  "clusterBorder": "#CBD5E1"
}}}%%
flowchart LR
    A[SMILES / Candidates]:::input
    B[Input Validation<br/>Schema + Rules]:::validate
    C[RDKit 3D<br/>ETKDGv3 + MMFF/UFF]:::ligand
    D[Meeko<br/>Ligand PDBQT]:::prep

    E[Protein PDB]:::protein
    F[Receptor Analysis<br/>Chain / Water / Cofactor]:::receptor
    G[Docking Box<br/>Center + Size Validation]:::box

    H[AutoDock Vina<br/>Reproducible Docking]:::vina
    I[Top Poses<br/>Affinity + RMSD]:::pose
    J[Scientific Interpretation<br/>Warnings + Limits]:::interpret
    K[Multi-Molecule Compare<br/>Radar + Ranking]:::compare
    L[Artifacts<br/>JSON + MD + ZIP + Manifest]:::artifact

    A --> B --> C --> D --> H
    E --> F --> G --> H
    H --> I --> J
    J --> K
    J --> L
    I --> L

    classDef input fill:#E0F2FE,stroke:#38BDF8,color:#0C4A6E,stroke-width:2px;
    classDef validate fill:#F3E8FF,stroke:#A855F7,color:#581C87,stroke-width:2px;
    classDef ligand fill:#DCFCE7,stroke:#22C55E,color:#14532D,stroke-width:2px;
    classDef prep fill:#CCFBF1,stroke:#14B8A6,color:#134E4A,stroke-width:2px;
    classDef protein fill:#FEF3C7,stroke:#F59E0B,color:#78350F,stroke-width:2px;
    classDef receptor fill:#FFEDD5,stroke:#FB923C,color:#7C2D12,stroke-width:2px;
    classDef box fill:#FCE7F3,stroke:#EC4899,color:#831843,stroke-width:2px;
    classDef vina fill:#EDE9FE,stroke:#8B5CF6,color:#4C1D95,stroke-width:3px;
    classDef pose fill:#DBEAFE,stroke:#3B82F6,color:#1E3A8A,stroke-width:2px;
    classDef interpret fill:#ECFCCB,stroke:#84CC16,color:#365314,stroke-width:2px;
    classDef compare fill:#CFFAFE,stroke:#06B6D4,color:#164E63,stroke-width:2px;
    classDef artifact fill:#F1F5F9,stroke:#64748B,color:#334155,stroke-width:2px;
```

> 这条链路的重点不是“把 Vina 跑起来”，而是把 **分子准备、受体准备、参数合法性、真实计算、结果解释、失败恢复与科研证据链** 组织成一个可被自动评审和二次调用的完整 Skill。

---

## 快速开始

```bash
# 1. 创建并激活环境（conda-forge，Python 3.11，macOS arm64）
mamba env create -f environment.yml
conda activate dockskill

# 2. 环境自检（成功输出 DOCKING_SKILL_CHECK_PASS）
make check

# 3. 运行示例：乙醇真实对接 + 非法 SMILES 结构化错误（输出 RUN_EXAMPLE_PASS）
make example

# 4. 运行测试（109 个用例）
make test

# 5. 可复现性双跑验证（输出 REPRODUCIBILITY_PASS）
make reproducibility
```

启动 API 与网页 Demo（两个终端）：

```bash
make backend    # FastAPI: http://127.0.0.1:8000 （仅本机监听）
make frontend   # Vite dev server: http://localhost:5173 （首次需 cd frontend && npm install）
```

## 目录结构

```text
skills/docking-copilot/SKILL.md  # 官方自动评审入口（主 Skill）
SUBMISSION.md       # 提交摘要（最短验证路径）
backend/            # app/（schemas + 9 services + workflow 状态机 + FastAPI）与 tests/（109 用例）
frontend/           # React + Vite + TypeScript + 3Dmol.js + ECharts（8 组件）
schemas/            # 4 个 JSON Schema（与 Pydantic 同源导出，make schemas）
dags/               # workflow.mmd / workflow.json / workflow.svg（make dag）
docs/               # 8 篇：WORKFLOW / PARAMETER_GUIDE / RESULT_INTERPRETATION /
                    # FAILURE_CASES / REPRODUCIBILITY / SCIENTIFIC_LIMITATIONS /
                    # SECURITY / ENVIRONMENT
examples/           # inputs/（3 个真实输入）+ failure_cases/（13 案例）+
                    # expected_outputs/ + data/（样例受体与来源说明）
notebooks/          # docking_skill_demo.ipynb + 已执行副本（.ipynb/.md）
scripts/            # check_environment / run_example / generate_schemas /
                    # generate_dag / generate_failure_cases /
                    # verify_reproducibility / pre_submission_check
reports/            # 环境自检、复现、测试、示例运行、质检等机器可读证据
outputs/            # 运行产物（gitignore，仅保留 .gitkeep）
```

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `make check` | 环境自检（`scripts/check_environment.py`），成功标记 `DOCKING_SKILL_CHECK_PASS` |
| `make example` | 可复现示例（`scripts/run_example.py`），成功标记 `RUN_EXAMPLE_PASS` |
| `make test` | pytest（`backend/tests`，109 用例） |
| `make schemas` | 重新导出 `schemas/*.schema.json` |
| `make dag` | 重新生成 DAG 三件套 |
| `make failure-cases` | 再生成 13 个失败案例 |
| `make reproducibility` | 双跑可复现验证，成功标记 `REPRODUCIBILITY_PASS` |
| `make backend` / `make frontend` / `make dev` | API / 前端 / 开发提示 |
| `make clean` | 清理 Python 缓存（不删除 outputs/） |
| `conda run -n dockskill python scripts/pre_submission_check.py` | 提交前质检 |

## 资源约束（16GB 内存设备）

后端 `workers=1`、对接并发 1、批量分子上限 20、上传上限 20MB、
box 单边 10–30 Å、对接超时 300s，详见 `backend/app/config.py`。

## 科学边界

docking score 是经验打分，不是实验药效、不是精确结合自由能，只在
同受体/同准备/同 box/同参数下批内相对比较有意义。详见
`docs/SCIENTIFIC_LIMITATIONS.md` 与 `skills/docking-copilot/SKILL.md` 的科学边界章节。

## License

MIT，见 `LICENSE`；引用格式见 `CITATION.cff`。

---

## GitHub 项目展示

DockingCopilot Skill 面向 **AI4S Future ScienceSkills Hackathon — AI for Biomedicine / 生物医药科研软件 Copilot Skill**。项目将传统分散的分子对接步骤封装为一条可追踪科研工作流：从 SMILES 输入、小分子三维构象生成、蛋白受体准备和对接参数校验，到 AutoDock Vina 计算、Pose 解析、结果解释与多候选比较，均保留结构化输入输出与可复现产物。

### 端到端工作流

```mermaid
flowchart LR
    A[SMILES / 候选分子] --> B[输入与结构校验]
    B --> C[RDKit 3D 构象生成]
    C --> D[Meeko 配体准备]
    E[Protein PDB] --> F[受体分析与准备]
    F --> G[Docking Box 校验]
    D --> H[AutoDock Vina]
    G --> H
    H --> I[Top Poses / Affinity]
    I --> J[结构化结果解释]
    J --> K[多分子比较 / 雷达图]
    I --> L[3D Protein-Ligand Complex]
    J --> M[Manifest / Report / Artifacts]
```

### 3D 结构与结果展示

<table>
<tr>
<td width="50%"><img src="frontend/public/intro_target_3d.png" alt="Protein 3D structure visualization"/></td>
<td width="50%"><img src="frontend/public/intro_demo_workflow.png" alt="Docking workflow visualization"/></td>
</tr>
<tr>
<td align="center"><b>蛋白 / 配体三维结构展示</b></td>
<td align="center"><b>对接工作流状态与中间产物展示</b></td>
</tr>
</table>

<p align="center">
  <img src="frontend/public/intro_demo_radar.png" width="72%" alt="Multi-molecule radar comparison"/>
</p>
<p align="center"><b>多候选分子的 Relative Docking & Developability Profile 雷达图比较</b></p>

### Skill 能力与赛题交付对应

| 赛题要求 | 本项目对应产物 |
| --- | --- |
| 完整、可复用的 Skill 文档 | `skills/docking-copilot/SKILL.md` |
| 配置与参数校验 | `backend/app/schemas.py`、`backend/app/services/box_service.py` |
| 脚本 / 工作流执行 | `backend/app/workflow/`、`scripts/run_example.py` |
| 可复现 Notebook | `notebooks/docking_skill_demo.ipynb` 与已执行副本 |
| 工作流 DAG | `dags/workflow.mmd` / `.json` / `.svg` |
| 输入 / 输出 Schema | `schemas/*.schema.json` |
| 结果解释 | `docs/RESULT_INTERPRETATION.md` |
| 失败案例 | `examples/failure_cases/`、`docs/FAILURE_CASES.md` |
| 科学边界与限制 | `docs/SCIENTIFIC_LIMITATIONS.md` |
| 可复现性证据 | `reports/reproducibility_report.json` |
| 辅助网页 Demo | `frontend/` + `backend/` |

### 网页 Demo 可展示内容

- 输入单个或多个 SMILES，并查看生成的分子 3D 构象；
- 查看蛋白受体 3D 结构、对接搜索区域及 protein–ligand complex；
- 切换不同候选分子与 Top Pose，查看对应 affinity 和结构化解释；
- 对同一受体、同一 box、同一参数下的多个候选分子进行批内比较；
- 通过雷达图同时查看 Relative Affinity、Ligand Efficiency、Pose Separation 与分子性质画像；
- 下载结构化 JSON、Markdown 报告和对接产物。

> **科学说明**：网页中的相对评分和雷达图用于同条件候选之间的辅助比较。AutoDock Vina affinity 属于经验打分结果，不等同于实验药效、Kd/Ki/IC50 或精确结合自由能。

### 自动评审快速入口

建议评审优先阅读或执行：

```text
skills/docking-copilot/SKILL.md
SUBMISSION.md
schemas/
dags/
notebooks/docking_skill_demo.executed.md
examples/failure_cases/
reports/submission_summary.json
```

最短本地验证：

```bash
make check
make example
make test
```


---

## 官方黑客松 Skill 入口（2026 提交格式）

自动评审入口为 [`skills/docking-copilot/SKILL.md`](skills/docking-copilot/SKILL.md)。该文件包含合法 YAML frontmatter，并将详细资料按渐进披露方式放在 [`skills/docking-copilot/references/`](skills/docking-copilot/references/)；根目录 `requirements.txt` 面向官方 Linux Docker 沙箱（2 核 / 4 GB / 无 GPU / 900 秒）。Mac mini M4 本地开发继续使用 `environment.yml`。

提交格式自检：

```bash
python skills/docking-copilot/scripts/validate_submission.py
```

官方沙箱依赖安装与核心运行时检查：

```bash
python -m pip install -r requirements.txt
python skills/docking-copilot/scripts/check_runtime.py
```
