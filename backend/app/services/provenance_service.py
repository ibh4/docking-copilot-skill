"""可复现记录服务：环境版本采集与 manifest.json 组装。"""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _vina_version() -> str | None:
    """优先 Python API 获取版本，失败则尝试 CLI。"""
    try:
        from vina import Vina

        return str(Vina.version.split()[1])
    except Exception:  # noqa: BLE001
        pass
    from app import config

    if config.VINA_EXECUTABLE is not None:
        try:
            proc = subprocess.run(
                [str(config.VINA_EXECUTABLE), "--version"],
                capture_output=True, text=True, timeout=30, check=False,
            )
            text = (proc.stdout + proc.stderr).strip()
            if text:
                return text.splitlines()[0]
        except Exception:  # noqa: BLE001
            pass
    return None


def environment_versions() -> dict:
    """采集 manifest 所需的全部版本信息。"""
    try:
        import rdkit

        rdkit_version: str | None = rdkit.__version__
    except Exception:  # noqa: BLE001
        rdkit_version = None
    try:
        import meeko

        meeko_version: str | None = meeko.__version__
    except Exception:  # noqa: BLE001
        meeko_version = None
    return {
        "vina_version": _vina_version(),
        "rdkit_version": rdkit_version,
        "meeko_version": meeko_version,
        "python_version": sys.version.split()[0],
        "macos_version": " ".join(x for x in platform.mac_ver()[0:1]) or None,
        "architecture": platform.machine(),
    }


def build_manifest(
    *,
    job_id: str,
    job_name: str,
    input_sha256: str | None,
    receptor_sha256: str | None,
    ligand_sha256: dict,
    parameters: dict,
    seed: int,
    commands_or_api_calls: list[str],
    started_at: str,
    finished_at: str | None,
    status: str,
    warnings: list[str],
    errors: list[dict],
    artifact_sha256: dict,
    extra: dict | None = None,
) -> dict:
    """组装 manifest.json 内容（提示词 5 字段全集）。"""
    start = datetime.fromisoformat(started_at) if started_at else None
    end = datetime.fromisoformat(finished_at) if finished_at else None
    runtime = (
        round((end - start).total_seconds(), 3)
        if start is not None and end is not None
        else None
    )
    manifest = {
        "job_id": job_id,
        "job_name": job_name,
        "input_sha256": input_sha256,
        "receptor_sha256": receptor_sha256,
        "ligand_sha256": ligand_sha256,
        **environment_versions(),
        "parameters": parameters,
        "random_seed": seed,
        "commands_or_api_calls": commands_or_api_calls,
        "start_time": started_at,
        "end_time": finished_at,
        "runtime_seconds": runtime,
        "status": status,
        "warnings": warnings,
        "errors": errors,
        "artifact_sha256": artifact_sha256,
    }
    if extra:
        manifest.update(extra)
    return manifest


def hash_artifacts(job_dir: Path, relative_paths: list[str]) -> dict:
    """计算产物文件 sha256（相对路径 → 哈希）。"""
    from app.utils.hashing import sha256_file

    hashes: dict[str, str] = {}
    for rel in relative_paths:
        target = job_dir / rel
        if target.is_file():
            hashes[rel] = sha256_file(target)
    return hashes
