"""DAG 一致性测试：节点/边必须与 runner 状态机和步骤序列一致。"""

from __future__ import annotations

import json

from app.schemas import JobState
from app.workflow.dag import build_dag, to_json_dict, to_mermaid
from app.workflow.states import TRANSITIONS

#: runner.run_job 中 record.update 出现的真实步骤顺序
RUNNER_STEP_ORDER = [
    "validate_input",
    "prepare_ligand",
    "analyze_receptor",
    "prepare_receptor",
    "validate_box",
    "configure_vina",
    "run_vina",
    "parse_scores",
    "export_poses",
    "calculate_metrics",
    "interpret",
    "generate_manifest",
    "package_artifacts",
]


def test_dag_node_ids_match_runner_steps() -> None:
    nodes, _ = build_dag()
    assert [n.id for n in nodes] == RUNNER_STEP_ORDER


def test_dag_node_states_are_valid_job_states() -> None:
    nodes, _ = build_dag()
    valid = {s.value for s in JobState}
    for node in nodes:
        assert node.state in valid, node


def test_dag_node_states_reachable_in_state_machine() -> None:
    """每个 DAG 节点标注的状态必须出现在状态机转移表的键中。"""
    nodes, _ = build_dag()
    states_in_machine = {s.value for s in TRANSITIONS}
    for node in nodes:
        assert node.state in states_in_machine, node


def test_dag_edges_are_linear_chain() -> None:
    nodes, edges = build_dag()
    expected = [
        {"source": nodes[i].id, "target": nodes[i + 1].id}
        for i in range(len(nodes) - 1)
    ]
    assert [{"source": e.source, "target": e.target} for e in edges] == expected


def test_mermaid_text_contains_all_nodes_and_failed_terminal() -> None:
    text = to_mermaid()
    assert text.startswith("graph TB")
    for step in RUNNER_STEP_ORDER:
        assert step in text
    assert "FAILED" in text


def test_json_export_structure() -> None:
    payload = to_json_dict()
    assert payload["name"]
    assert len(payload["nodes"]) == len(RUNNER_STEP_ORDER)
    assert payload["edges"][0]["source"] == RUNNER_STEP_ORDER[0]
    # JSON 可序列化
    json.dumps(payload, ensure_ascii=False)


def test_dags_artifacts_exist_and_consistent(project_root) -> None:
    """dags/ 三件套存在且节点与代码定义一致（make dag 生成）。"""
    dags_dir = project_root / "dags"
    mmd = dags_dir / "workflow.mmd"
    js = dags_dir / "workflow.json"
    svg = dags_dir / "workflow.svg"
    for path in (mmd, js, svg):
        assert path.is_file() and path.stat().st_size > 0, path
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert [n["id"] for n in payload["nodes"]] == RUNNER_STEP_ORDER
    mmd_text = mmd.read_text(encoding="utf-8")
    for step in RUNNER_STEP_ORDER:
        assert step in mmd_text
    assert "<svg" in svg.read_text(encoding="utf-8")
