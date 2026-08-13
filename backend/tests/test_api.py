"""Phase 3a API 测试（FastAPI TestClient）。

覆盖：health / version / schema / ligand prepare / receptors analyze /
docking run+轮询至 SUCCESS / result / files / comparison(radar) /
非法 SMILES / 非法 box / 不存在 job / 路径穿越 / 批量上限 / DELETE。

job 产物写入临时目录（DOCKSKILL_OUTPUTS_DIR 隔离），不污染仓库 outputs/。
真实 Vina 对接相关测试标记 pytest.mark.slow。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

# 必须在导入 app.* 之前设置，保证 config.OUTPUTS_DIR 指向临时目录
_API_TMP = Path(tempfile.mkdtemp(prefix="dockskill_api_tests_"))
os.environ["DOCKSKILL_OUTPUTS_DIR"] = str(_API_TMP)

from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402

_TERMINAL = {"SUCCESS", "FAILED", "CANCELLED"}

RECEPTOR_SOURCE = "examples/data/sample_receptor.pdb"


@pytest.fixture(scope="module")
def client():
    old_dir = config.OUTPUTS_DIR
    old_env = os.environ.get("DOCKSKILL_OUTPUTS_DIR")
    config.OUTPUTS_DIR = _API_TMP
    with TestClient(app) as test_client:
        yield test_client
    config.OUTPUTS_DIR = old_dir
    if old_env is None:
        os.environ.pop("DOCKSKILL_OUTPUTS_DIR", None)
    else:
        os.environ["DOCKSKILL_OUTPUTS_DIR"] = old_env
    shutil.rmtree(_API_TMP, ignore_errors=True)


def wait_for_terminal(client: TestClient, job_id: str, timeout: float = 600.0) -> dict:
    """轮询 job 状态直至终态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body.get("state") in _TERMINAL:
            return body
        time.sleep(1.0)
    raise AssertionError(f"job {job_id} did not reach terminal state in {timeout}s")


def docking_payload(**overrides) -> dict:
    payload = {
        "job_name": "api_test_job",
        "ligands": [{"ligand_id": "ethanol", "smiles": "CCO"}],
        "receptor": {"source": RECEPTOR_SOURCE},
        "docking_box": {
            "mode": "explicit",
            "center": [18.3, 2.3, 21.4],
            "size": [20.0, 20.0, 20.0],
        },
        "docking_parameters": {
            "exhaustiveness": 4,
            "num_modes": 3,
            "seed": 42,
            "cpu": 4,
            "energy_range": 3.0,
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 基础端点
# ---------------------------------------------------------------------------


def test_health(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "DockingCopilot Skill"
    assert "version" in body


def test_root(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["name"] == "DockingCopilot Skill"


def test_version(client) -> None:
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("skill_version", "api_version", "vina", "rdkit", "meeko", "python"):
        assert key in body
    assert body["python"]


def test_schema_endpoints(client) -> None:
    input_schema = client.get("/api/schema/input")
    assert input_schema.status_code == 200
    assert input_schema.json()["title"] == "DockingInput"
    output_schema = client.get("/api/schema/output")
    assert output_schema.status_code == 200
    assert output_schema.json()["title"] == "DockingOutput"


def test_openapi_docs_available(client) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    for required in (
        "/health",
        "/api/version",
        "/api/schema/input",
        "/api/schema/output",
        "/api/ligands/prepare",
        "/api/receptors/analyze",
        "/api/receptors/prepare",
        "/api/docking/run",
        "/api/docking/batch",
        "/api/comparison",
        "/api/jobs/{job_id}",
        "/api/jobs/{job_id}/result",
        "/api/jobs/{job_id}/artifacts",
        "/api/jobs/{job_id}/files/{relative_path}",
    ):
        assert required in paths, required


# ---------------------------------------------------------------------------
# ligand prepare
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_ligand_prepare_submit_and_success(client) -> None:
    resp = client.post(
        "/api/ligands/prepare",
        json={
            "ligands": [{"ligand_id": "ethanol", "smiles": "CCO"}],
            "ligand_preparation": {"num_conformers": 3, "random_seed": 42},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "CREATED"
    job_id = body["job_id"]

    final = wait_for_terminal(client, job_id)
    assert final["state"] == "SUCCESS", final
    artifacts = client.get(f"/api/jobs/{job_id}/artifacts")
    assert artifacts.status_code == 200
    artifact_items = artifacts.json()["artifacts"]
    assert any("ligand.pdbqt" in str(v) for v in artifact_items.values())
    # 受控文件读取
    pdbqt = client.get(f"/api/jobs/{job_id}/files/ligands/ethanol/ligand.pdbqt")
    assert pdbqt.status_code == 200
    assert "ROOT" in pdbqt.text


def test_ligand_prepare_invalid_smiles_rejected(client) -> None:
    resp = client.post(
        "/api/ligands/prepare",
        json={"ligands": [{"ligand_id": "bad", "smiles": "NOT_A_SMILES(("}]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_SMILES"
    assert body["details"]["ligand_id"] == "bad"
    assert "suggested_actions" in body


def test_ligand_prepare_duplicate_ids_rejected(client) -> None:
    resp = client.post(
        "/api/ligands/prepare",
        json={
            "ligands": [
                {"ligand_id": "a", "smiles": "CCO"},
                {"ligand_id": "a", "smiles": "CO"},
            ]
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INPUT_VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# receptors analyze（同步）
# ---------------------------------------------------------------------------


def test_receptors_analyze_json_reference(client) -> None:
    resp = client.post(
        "/api/receptors/analyze", json={"source": RECEPTOR_SOURCE}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "chains", "residue_count", "atom_count", "hetero", "waters",
        "metals", "cofactors", "bounding_box", "warnings",
    ):
        assert key in body
    assert body["residue_count"] > 0
    assert body["atom_count"] > 0
    assert body["bounding_box"]["min"]
    assert body["bounding_box"]["max"]


def test_receptors_analyze_multipart_upload(client, project_root) -> None:
    pdb_path = project_root / RECEPTOR_SOURCE
    with pdb_path.open("rb") as fh:
        resp = client.post(
            "/api/receptors/analyze",
            files={"file": ("sample_receptor.pdb", fh, "chemical/x-pdb")},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["atom_count"] > 0


def test_receptors_analyze_invalid_content(client) -> None:
    resp = client.post(
        "/api/receptors/analyze",
        files={"file": ("bad.pdb", b"this is not a pdb file", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INVALID_RECEPTOR"


def test_receptors_analyze_missing_source(client) -> None:
    resp = client.post(
        "/api/receptors/analyze", json={"source": "examples/data/no_such.pdb"}
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "FILE_NOT_FOUND"


@pytest.mark.slow
def test_receptors_analyze_upload_too_large(client) -> None:
    big = b"ATOM      1  N   ALA A   1       0.000   0.000   0.000\n" * 470_000
    resp = client.post(
        "/api/receptors/analyze",
        files={"file": ("big.pdb", big, "chemical/x-pdb")},
    )
    assert resp.status_code == 413


def test_receptors_prepare_missing_source(client) -> None:
    resp = client.post(
        "/api/receptors/prepare", json={"source": "examples/data/no_such.pdb"}
    )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "FILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# docking run：提交前校验（快速，不产生 job）
# ---------------------------------------------------------------------------


def test_docking_run_invalid_smiles_rejected(client) -> None:
    payload = docking_payload(
        ligands=[{"ligand_id": "bad", "smiles": "NOT_A_SMILES(("}]
    )
    resp = client.post("/api/docking/run", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "INVALID_SMILES"
    assert body["stage"] == "validate_input"


def test_docking_run_box_outside_receptor_rejected(client) -> None:
    payload = docking_payload(
        docking_box={
            "mode": "explicit",
            "center": [500.0, 500.0, 500.0],
            "size": [20.0, 20.0, 20.0],
        }
    )
    resp = client.post("/api/docking/run", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "BOX_OUTSIDE_RECEPTOR"


def test_docking_run_box_too_large_rejected(client) -> None:
    payload = docking_payload(
        docking_box={
            "mode": "explicit",
            "center": [18.3, 2.3, 21.4],
            "size": [30.0, 30.0, 31.0],
        }
    )
    resp = client.post("/api/docking/run", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error_code"] in ("INPUT_VALIDATION_FAILED", "BOX_TOO_LARGE")


def test_docking_run_missing_receptor_rejected(client) -> None:
    payload = docking_payload(receptor={"source": "examples/data/no_such.pdb"})
    resp = client.post("/api/docking/run", json=payload)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "FILE_NOT_FOUND"


def test_batch_too_many_ligands_rejected(client) -> None:
    payload = docking_payload(
        ligands=[
            {"ligand_id": f"mol_{i}", "smiles": "CCO"} for i in range(21)
        ]
    )
    resp = client.post("/api/docking/batch", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "INPUT_VALIDATION_FAILED"


# ---------------------------------------------------------------------------
# 不存在的 job / 路径穿越 / 非法扩展名
# ---------------------------------------------------------------------------


def test_nonexistent_job_returns_404(client) -> None:
    for path in (
        "/api/jobs/no_such_job",
        "/api/jobs/no_such_job/result",
        "/api/jobs/no_such_job/artifacts",
        "/api/jobs/no_such_job/files/reports/result.json",
    ):
        resp = client.get(path)
        assert resp.status_code == 404, path
        assert resp.json()["error_code"] == "FILE_NOT_FOUND"
    resp = client.delete("/api/jobs/no_such_job")
    assert resp.status_code == 404


@pytest.mark.slow
def test_files_path_traversal_blocked(client, success_job_id) -> None:
    resp = client.get(
        f"/api/jobs/{success_job_id}/files/..%2F..%2F..%2Fetc%2Fpasswd"
    )
    assert resp.status_code in (403, 404)
    resp2 = client.get(
        f"/api/jobs/{success_job_id}/files/../../../etc/passwd"
    )
    assert resp2.status_code in (403, 404)


@pytest.mark.slow
def test_files_disallowed_extension_blocked(client, success_job_id) -> None:
    resp = client.get(f"/api/jobs/{success_job_id}/files/input.bin")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# docking run 端到端（真实 Vina，小参数）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def success_job_id(client):
    """模块级共享：真实对接一次（exhaustiveness=4, num_modes=3）。"""
    resp = client.post("/api/docking/run", json=docking_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "CREATED"
    job_id = body["job_id"]
    final = wait_for_terminal(client, job_id)
    assert final["state"] == "SUCCESS", final
    return job_id


@pytest.mark.slow
def test_docking_run_poll_result_files(client, success_job_id) -> None:
    job_id = success_job_id
    # 状态流转终态字段完整
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["state"] == "SUCCESS"
    assert job["progress"] == 100
    assert job["started_at"] and job["finished_at"]
    assert job["structured_error"] is None

    # result.json
    result = client.get(f"/api/jobs/{job_id}/result")
    assert result.status_code == 200
    output = result.json()
    assert output["status"] == "SUCCESS"
    ligand = output["results"][0]
    assert ligand["status"] == "SUCCESS"
    assert ligand["best_affinity_kcal_mol"] < 0
    assert len(ligand["poses"]) >= 1

    # artifacts 清单
    artifacts = client.get(f"/api/jobs/{job_id}/artifacts")
    assert artifacts.status_code == 200
    artifact_paths = artifacts.json()["artifacts"]
    assert any("result.json" in key for key in artifact_paths)
    assert artifacts.json()["bundle_zip"] == "bundle.zip"

    # 受控读取 pose pdbqt
    pose_file = ligand["poses"][0]["pose_file"]
    pose = client.get(f"/api/jobs/{job_id}/files/{pose_file}")
    assert pose.status_code == 200
    assert "ATOM" in pose.text

    # bundle.zip 直接下载
    bundle = client.get(f"/api/jobs/{job_id}/files/bundle.zip")
    assert bundle.status_code == 200
    assert bundle.headers["content-type"] == "application/zip"
    assert bundle.content[:2] == b"PK"


@pytest.mark.slow
def test_comparison_returns_radar_dimensions(client, success_job_id) -> None:
    resp = client.post("/api/comparison", json={"job_id": success_job_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == success_job_id
    assert body["radar_dimensions"]
    assert "affinity" in body["radar_dimensions"]
    assert body["normalization_method"]
    assert body["scientific_warning"]
    assert body["disclaimer"]
    assert body["context"]["box_mode"] == "explicit"
    assert "ethanol" in body["metrics"]


def test_comparison_nonexistent_job(client) -> None:
    resp = client.post("/api/comparison", json={"job_id": "no_such_job"})
    assert resp.status_code == 404


def test_comparison_not_finished_job_conflict(client) -> None:
    """非 SUCCESS 的 job（手工构造 FAILED 状态）→ 409。"""
    import json as _json

    fake_dir = config.OUTPUTS_DIR / "20000101-000000_fake_failed"
    fake_dir.mkdir(parents=True, exist_ok=True)
    (fake_dir / "job.json").write_text(
        _json.dumps({"job_id": fake_dir.name, "state": "FAILED"}),
        encoding="utf-8",
    )
    resp = client.post("/api/comparison", json={"job_id": fake_dir.name})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_delete_job_cleans_artifacts(client, success_job_id) -> None:
    resp = client.delete(f"/api/jobs/{success_job_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert client.get(f"/api/jobs/{success_job_id}").status_code == 404
    assert not (config.OUTPUTS_DIR / success_job_id).exists()
