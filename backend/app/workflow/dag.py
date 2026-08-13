"""工作流 DAG：节点/边定义与 Mermaid / JSON 导出。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.schemas import JobState

#: 顺序工作流步骤（提示词 5）与对应 JobState
STEP_SEQUENCE: list[tuple[str, str, JobState]] = [
    ("validate_input", "校验输入 schema、受体路径与资源上限", JobState.VALIDATING),
    ("prepare_ligand", "SMILES 校验、3D 构象、描述符与 PDBQT（Meeko）", JobState.PREPARING_LIGAND),
    ("analyze_receptor", "Biopython 结构分析报告", JobState.PREPARING_RECEPTOR),
    ("prepare_receptor", "按配置清洗并生成 receptor.pdbqt", JobState.PREPARING_RECEPTOR),
    ("validate_box", "搜索盒生成与校验（四模式）", JobState.VALIDATING_BOX),
    ("configure_vina", "组装 Vina 参数（双适配器探测）", JobState.DOCKING),
    ("run_vina", "AutoDock Vina 对接（Python API 优先，CLI 回退）", JobState.DOCKING),
    ("parse_scores", "解析 REMARK VINA RESULT 与 MODEL 分段", JobState.PARSING),
    ("export_poses", "切分 pose 并转 PDB", JobState.PARSING),
    ("calculate_metrics", "ligand efficiency 与批次内相对指标", JobState.ANALYZING),
    ("interpret", "生成 Markdown 解释报告（固定科学措辞）", JobState.ANALYZING),
    ("generate_manifest", "组装可复现记录 manifest.json", JobState.PACKAGING),
    ("package_artifacts", "打包 bundle.zip（含 top-3 pose）", JobState.PACKAGING),
]


@dataclass(frozen=True)
class DagNode:
    id: str
    label: str
    state: str


@dataclass(frozen=True)
class DagEdge:
    source: str
    target: str


def build_dag() -> tuple[list[DagNode], list[DagEdge]]:
    """返回线性 DAG 的节点与边。"""
    nodes = [
        DagNode(id=step, label=label, state=state.value)
        for step, label, state in STEP_SEQUENCE
    ]
    edges = [
        DagEdge(source=nodes[i].id, target=nodes[i + 1].id)
        for i in range(len(nodes) - 1)
    ]
    return nodes, edges


def to_mermaid() -> str:
    """导出 Mermaid graph TB 文本（无样式；节点标签含对应 JobState）。"""
    nodes, edges = build_dag()
    lines = ["graph TB"]
    for node in nodes:
        lines.append(f'    {node.id}["{node.id} ({node.state})"]')
    for edge in edges:
        lines.append(f"    {edge.source} --> {edge.target}")
    lines.append("    FAILED[FAILED 结构化错误终态]")
    for node in nodes:
        lines.append(f"    {node.id} -.-> FAILED")
    return "\n".join(lines) + "\n"


def to_json_dict() -> dict:
    """导出 JSON 可序列化的 DAG。"""
    nodes, edges = build_dag()
    return {
        "name": "docking-copilot-skill-workflow",
        "description": "SMILES → 3D/PDBQT → 受体准备 → box → Vina → 解析 → 解释 → manifest → 打包",
        "nodes": [{"id": n.id, "label": n.label, "state": n.state} for n in nodes],
        "edges": [{"source": e.source, "target": e.target} for e in edges],
    }


def to_json_text() -> str:
    return json.dumps(to_json_dict(), ensure_ascii=False, indent=2) + "\n"
