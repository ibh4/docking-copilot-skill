"""集中式配置：资源上限常量与运行时常量。

所有数值依据 16GB 内存的 Apple Silicon 设备约束设定（见提示词 1 F 节）。
不要在其他模块中散落魔法数字，统一从这里引用。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

#: 项目根目录（backend/app/config.py 上溯三级）
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

#: 运行时产物输出目录；每个 job 写入独立子目录 outputs/<job_id>/
OUTPUTS_DIR: Path = Path(
    os.environ.get("DOCKSKILL_OUTPUTS_DIR", str(PROJECT_ROOT / "outputs"))
)

#: 仓库内随附的 Vina 可执行文件（fallback 用，arm64 macOS 二进制）
_VENDOR_VINA: Path = PROJECT_ROOT / "vendor" / "bin" / "vina"


def find_vina_executable() -> Path | None:
    """探测 Vina 可执行文件。

    优先级：
    1. 环境变量 ``DOCKSKILL_VINA_EXECUTABLE``（显式指定）；
    2. 当前环境 PATH 中的 ``vina``（conda-forge 安装的 CLI）；
    3. 仓库内 ``vendor/bin/vina``（随项目分发的二进制）。

    返回第一个存在且可执行的路径；均不可用时返回 None。
    """
    explicit = os.environ.get("DOCKSKILL_VINA_EXECUTABLE")
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
    on_path = shutil.which("vina")
    if on_path:
        return Path(on_path)
    if _VENDOR_VINA.is_file() and os.access(_VENDOR_VINA, os.X_OK):
        return _VENDOR_VINA
    return None


#: 探测结果（模块导入时计算一次；运行期如需刷新可重新调用函数）
VINA_EXECUTABLE: Path | None = find_vina_executable()

# ---------------------------------------------------------------------------
# 16GB 内存约束下的资源上限
# ---------------------------------------------------------------------------

#: 后端 uvicorn worker 数（固定 1，避免重复加载 RDKit/Vina）
WORKERS: int = 1

#: 同时运行的 docking 任务数
DOCK_CONCURRENCY: int = 1

#: 单次批量对接的分子数上限
BATCH_MAX_LIGANDS: int = 20

#: 单次上传文件（PDB 等）大小上限，单位 MB
UPLOAD_MAX_MB: int = 20

#: docking 单次运行超时（秒）
DOCKING_TIMEOUT_SECONDS: int = 300

# ---------------------------------------------------------------------------
# Vina 默认参数
# ---------------------------------------------------------------------------

#: 输出构象数
NUM_MODES_DEFAULT: int = 9

#: 搜索强度（合法范围 1–32）
EXHAUSTIVENESS_DEFAULT: int = 8
EXHAUSTIVENESS_MIN: int = 1
EXHAUSTIVENESS_MAX: int = 32

#: Vina 使用的 CPU 核数（默认 4，上限 8）
CPU_DEFAULT: int = 4
CPU_MAX: int = 8

#: 随机种子（默认固定以保证可复现）
VINA_SEED_DEFAULT: int = 42

# ---------------------------------------------------------------------------
# docking box 约束（单位：Å）
# ---------------------------------------------------------------------------

#: 搜索盒单边最小长度
BOX_EDGE_MIN: float = 10.0

#: 搜索盒单边最大长度
BOX_EDGE_MAX: float = 30.0

#: 搜索盒体积上限（Å³），即 30×30×30
BOX_VOLUME_MAX: float = 27000.0
