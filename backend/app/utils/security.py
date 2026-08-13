"""安全校验：上传大小、批量上限等（阈值统一引用 app.config）。"""

from __future__ import annotations

from pathlib import Path

from app import config


class SecurityError(ValueError):
    """违反资源/安全上限。"""


def check_upload_size(path: str | Path) -> int:
    """校验文件大小不超过 ``config.UPLOAD_MAX_MB``，返回字节数。"""
    size = Path(path).stat().st_size
    limit_bytes = config.UPLOAD_MAX_MB * 1024 * 1024
    if size > limit_bytes:
        raise SecurityError(
            f"file too large: {size} bytes > {config.UPLOAD_MAX_MB} MB limit"
        )
    return size


def check_batch_size(count: int) -> None:
    """校验批量分子数不超过 ``config.BATCH_MAX_LIGANDS``。"""
    if count <= 0:
        raise SecurityError("batch must contain at least one ligand")
    if count > config.BATCH_MAX_LIGANDS:
        raise SecurityError(
            f"too many ligands: {count} > {config.BATCH_MAX_LIGANDS}"
        )


def check_upload_bytes(data: bytes) -> None:
    """校验内存中上传内容大小（API 层使用）。"""
    limit_bytes = config.UPLOAD_MAX_MB * 1024 * 1024
    if len(data) > limit_bytes:
        raise SecurityError(
            f"upload too large: {len(data)} bytes > {config.UPLOAD_MAX_MB} MB limit"
        )
