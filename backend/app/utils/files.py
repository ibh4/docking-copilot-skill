"""文件路径与 job 目录工具：文件名净化、路径穿越防护、目录创建。"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


class PathTraversalError(ValueError):
    """路径解析结果逃逸出允许的根目录。"""


def sanitize_filename(name: str, max_length: int = 64) -> str:
    """净化文件名：去除路径分隔符与控制字符，仅保留安全字符。

    - 只保留字母、数字、``-._``；其余字符替换为 ``_``；
    - 折叠重复下划线；去除首尾 ``._``；截断至 max_length；
    - 空结果返回 ``"unnamed"``。
    """
    normalized = unicodedata.normalize("NFKD", str(name))
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", normalized)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("._")
    return cleaned or "unnamed"


def safe_resolve(path: str | Path, base: str | Path) -> Path:
    """把 ``path``（可为相对路径）解析为绝对路径，并校验位于 ``base`` 之内。

    防止 ``../`` 等路径穿越；校验失败抛出 PathTraversalError。
    """
    base_resolved = Path(base).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = base_resolved / candidate
    resolved = candidate.resolve()
    if resolved != base_resolved and base_resolved not in resolved.parents:
        raise PathTraversalError(
            f"path '{path}' resolves outside allowed base '{base_resolved}'"
        )
    return resolved


def ensure_job_dir(outputs_root: Path, job_id: str) -> Path:
    """创建 ``outputs_root/<job_id>/`` 及标准子目录并返回目录。"""
    job_dir = safe_resolve(job_id, outputs_root)
    for sub in ("ligands", "receptor", "poses", "logs", "reports"):
        (job_dir / sub).mkdir(parents=True, exist_ok=True)
    return job_dir


def make_job_id(job_name: str) -> str:
    """生成 job_id：``YYYYMMDD-HHMMSS_<净化名>``（UTC 时间）。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}_{sanitize_filename(job_name, max_length=40)}"
