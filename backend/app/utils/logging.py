"""结构化日志工具：同时输出到控制台与 job 的 logs/ 目录。"""

from __future__ import annotations

import logging as std_logging
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_logger(name: str, log_dir: Path | None = None) -> std_logging.Logger:
    """返回结构化 logger。

    - 总是带控制台 handler（INFO）；
    - 给定 ``log_dir`` 时附加文件 handler，写入 ``log_dir/<name>.log``；
    - 重复调用同名 logger 不重复添加 handler。
    """
    logger = std_logging.getLogger(f"dockskill.{name}")
    logger.setLevel(std_logging.DEBUG)
    if not logger.handlers:
        console = std_logging.StreamHandler()
        console.setLevel(std_logging.INFO)
        console.setFormatter(std_logging.Formatter(_FORMAT))
        logger.addHandler(console)
        logger.propagate = False
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        target = log_dir / f"{name}.log"
        if not any(
            isinstance(h, std_logging.FileHandler)
            and Path(h.baseFilename) == target
            for h in logger.handlers
        ):
            file_handler = std_logging.FileHandler(target, encoding="utf-8")
            file_handler.setLevel(std_logging.DEBUG)
            file_handler.setFormatter(std_logging.Formatter(_FORMAT))
            logger.addHandler(file_handler)
    return logger
