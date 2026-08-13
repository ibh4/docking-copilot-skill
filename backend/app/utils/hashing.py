"""sha256 哈希工具（manifest 与可复现记录用）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK_SIZE = 1 << 20  # 1 MiB，避免大文件一次性读入内存


def sha256_bytes(data: bytes) -> str:
    """计算字节串的 sha256（十六进制小写）。"""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """流式计算文件 sha256（十六进制小写）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
