"""AutoDock Vina 对接服务：双适配器（Python API 优先，CLI 回退）。

约束（提示词 5）：
- 禁止 shell=True；CLI 使用参数数组 subprocess.run；
- stdout/stderr 落 logs/vina_stdout.log；
- 输出解析 ``REMARK VINA RESULT: <aff> <rmsd_lb> <rmsd_ub>`` + MODEL 分段；
- pose 切分 pose_NNN.pdbqt 并转 pose_NNN.pdb（Meeko/RDKit 优先，obabel 兜底）；
- 无 pose → NO_POSE；运行失败 → VINA_FAILED。

健壮性：Vina C++ 层遇到损坏 pdbqt 会直接 SIGABRT 杀死整个进程，
因此（1）调用引擎前对 pdbqt 做必要内容预校验（快速失败、可诊断）；
（2）Python API 在独立子进程中运行，崩溃只影响子进程并可受控回退 CLI。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem

from app import config
from app.schemas import ErrorCode, VinaParams
from app.utils.logging import get_logger

logger = get_logger("vina")

try:  # Python API 适配器可用性探测
    from vina import Vina as _VinaApi

    _HAS_PYTHON_API = True
except Exception:  # noqa: BLE001
    _VinaApi = None  # type: ignore[assignment]
    _HAS_PYTHON_API = False

try:
    from meeko import PDBQTMolecule
    from meeko.rdkit_mol_create import RdkitMolCreate

    _HAS_MEEKO_EXPORT = True
except Exception:  # noqa: BLE001
    _HAS_MEEKO_EXPORT = False

_VINA_RESULT_PREFIX = "REMARK VINA RESULT:"


class VinaEngineError(Exception):
    """Vina 运行阶段的受控错误。"""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict | None = None,
        suggested_actions: list[str] | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.suggested_actions = suggested_actions or []
        self.recoverable = recoverable


@dataclass
class ParsedPose:
    rank: int
    affinity_kcal_mol: float
    rmsd_lb: float
    rmsd_ub: float
    block: str


@dataclass
class DockRunResult:
    output_text: str
    engine_used: str


def engine_status() -> dict:
    """报告双适配器可用性（manifest/健康检查用）。"""
    return {
        "python_api_available": _HAS_PYTHON_API,
        "cli_available": config.VINA_EXECUTABLE is not None,
        "cli_path": str(config.VINA_EXECUTABLE) if config.VINA_EXECUTABLE else None,
    }


# ---------------------------------------------------------------------------
# pdbqt 预校验（损坏文件在调用引擎前即被拒绝，避免 C++ 层 abort）
# ---------------------------------------------------------------------------


def validate_pdbqt_files(receptor_pdbqt: Path, ligand_pdbqt: Path) -> None:
    """对接前校验 pdbqt 必要内容；不满足抛 VinaEngineError(VINA_FAILED)。

    - 受体：非空且含 ATOM 记录；
    - 配体：含 ROOT/ENDROOT/TORSDOF 且非空。
    """
    for path, role, tokens in (
        (receptor_pdbqt, "receptor", ("ATOM",)),
        (ligand_pdbqt, "ligand", ("ROOT", "ENDROOT", "TORSDOF")),
    ):
        if not path.is_file():
            raise VinaEngineError(
                ErrorCode.VINA_FAILED,
                f"{role} pdbqt not found: {path}",
                suggested_actions=["regenerate pdbqt via meeko"],
            )
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            raise VinaEngineError(
                ErrorCode.VINA_FAILED,
                f"{role} pdbqt is empty: {path}",
                suggested_actions=["regenerate pdbqt via meeko"],
            )
        missing = [t for t in tokens if t not in text]
        if missing:
            raise VinaEngineError(
                ErrorCode.VINA_FAILED,
                f"{role} pdbqt invalid ({path.name}): missing "
                f"{', '.join(missing)}",
                details={"path": str(path), "missing": missing},
                suggested_actions=[
                    "check pdbqt integrity; regenerate with meeko"
                ],
            )


# ---------------------------------------------------------------------------
# 适配器 1：Python API（独立子进程执行，崩溃隔离 + 超时守卫）
# ---------------------------------------------------------------------------

#: 子进程脚本：在干净进程中调用 Vina Python API，pose 文本写 stdout。
#: C++ 层 abort 只会杀死该子进程，主进程可受控回退 CLI。
_VINA_CHILD_CODE = """
import json, sys
args = json.loads(sys.argv[1])
from vina import Vina
v = Vina(
    sf_name=args["scoring_function"],
    cpu=args["cpu"],
    seed=args["seed"],
    verbosity=False,
    no_refine=False,
)
v.set_receptor(args["receptor"])
v.set_ligand_from_file(args["ligand"])
v.compute_vina_maps(
    center=tuple(args["center"]), box_size=tuple(args["size"])
)
v.dock(exhaustiveness=args["exhaustiveness"], n_poses=args["num_modes"])
sys.stdout.write(str(v.poses(n_poses=args["num_modes"])))
"""


def _run_python_api(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    box_center: list[float],
    box_size: list[float],
    params: VinaParams,
) -> str:
    payload = json.dumps(
        {
            "scoring_function": params.scoring_function,
            "cpu": params.cpu,
            "seed": params.seed,
            "exhaustiveness": params.exhaustiveness,
            "num_modes": params.num_modes,
            "receptor": str(receptor_pdbqt),
            "ligand": str(ligand_pdbqt),
            "center": box_center,
            "size": box_size,
        }
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _VINA_CHILD_CODE, payload],
            capture_output=True,
            text=True,
            timeout=config.DOCKING_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VinaEngineError(
            ErrorCode.VINA_TIMEOUT,
            f"Vina python api exceeded {config.DOCKING_TIMEOUT_SECONDS}s timeout",
            recoverable=True,
        ) from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(
            f"vina python api child exited rc={proc.returncode}: "
            f"{proc.stderr[-500:]}"
        )
    return proc.stdout


# ---------------------------------------------------------------------------
# 适配器 2：CLI（参数数组，禁止 shell=True）
# ---------------------------------------------------------------------------


def build_cli_command(
    executable: Path,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    out_path: Path,
    box_center: list[float],
    box_size: list[float],
    params: VinaParams,
) -> list[str]:
    """构造 CLI 参数数组（纯数据，无 shell 拼接）。"""
    return [
        str(executable),
        "--receptor", str(receptor_pdbqt),
        "--ligand", str(ligand_pdbqt),
        "--center_x", f"{box_center[0]:.3f}",
        "--center_y", f"{box_center[1]:.3f}",
        "--center_z", f"{box_center[2]:.3f}",
        "--size_x", f"{box_size[0]:.3f}",
        "--size_y", f"{box_size[1]:.3f}",
        "--size_z", f"{box_size[2]:.3f}",
        "--exhaustiveness", str(params.exhaustiveness),
        "--num_modes", str(params.num_modes),
        "--energy_range", f"{params.energy_range:.3f}",
        "--cpu", str(params.cpu),
        "--seed", str(params.seed),
        "--out", str(out_path),
    ]


def _run_cli(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    box_center: list[float],
    box_size: list[float],
    params: VinaParams,
    logs_dir: Path,
) -> str:
    if config.VINA_EXECUTABLE is None:
        raise VinaEngineError(
            ErrorCode.VINA_FAILED,
            "Vina executable not found (python api already failed)",
            suggested_actions=[
                "install autodock-vina via conda-forge",
                "or set DOCKSKILL_VINA_EXECUTABLE",
            ],
        )
    out_path = logs_dir.parent / "vina_raw_output.pdbqt"
    command = build_cli_command(
        config.VINA_EXECUTABLE, receptor_pdbqt, ligand_pdbqt,
        out_path, box_center, box_size, params,
    )
    logger.info("vina cli command: %s", " ".join(command))
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=config.DOCKING_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VinaEngineError(
            ErrorCode.VINA_TIMEOUT,
            f"Vina CLI exceeded {config.DOCKING_TIMEOUT_SECONDS}s timeout",
            details={"command": command},
        ) from exc
    stdout_log = logs_dir / "vina_stdout.log"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log.write_text(
        f"# command: {' '.join(command)}\n"
        f"# returncode: {proc.returncode}\n"
        "----- stdout -----\n"
        f"{proc.stdout}\n"
        "----- stderr -----\n"
        f"{proc.stderr}\n",
        encoding="utf-8",
    )
    if proc.returncode != 0 or not out_path.is_file():
        raise VinaEngineError(
            ErrorCode.VINA_FAILED,
            "Vina CLI returned non-zero or produced no output",
            details={
                "returncode": proc.returncode,
                "stderr": proc.stderr[-2000:],
                "stdout_log": f"logs/{stdout_log.name}",
            },
        )
    return out_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def dock_one(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    box_center: list[float],
    box_size: list[float],
    params: VinaParams,
    logs_dir: Path,
) -> DockRunResult:
    """对接单个分子：Python API 优先，异常/不可用时回退 CLI。

    返回原始输出文本与所用引擎；任何失败抛 VinaEngineError（绝不吞错）。
    """
    errors: list[str] = []
    validate_pdbqt_files(receptor_pdbqt, ligand_pdbqt)
    if _HAS_PYTHON_API:
        try:
            text = _run_python_api(
                receptor_pdbqt, ligand_pdbqt, box_center, box_size, params
            )
            return DockRunResult(output_text=text, engine_used="vina python api")
        except VinaEngineError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 记录后受控回退 CLI
            errors.append(f"python api failed: {exc}")
            logger.warning("vina python api failed, falling back to CLI: %s", exc)
    else:
        errors.append("python api not importable")
    text = _run_cli(
        receptor_pdbqt, ligand_pdbqt, box_center, box_size, params, logs_dir
    )
    return DockRunResult(output_text=text, engine_used="vina cli")


# ---------------------------------------------------------------------------
# 输出解析
# ---------------------------------------------------------------------------


def parse_vina_output(text: str) -> list[ParsedPose]:
    """解析 ``MODEL/REMARK VINA RESULT/ENDMDL`` 分段。

    无 MODEL 包装时（如单 pose），整体作为一段解析。
    """
    poses: list[ParsedPose] = []
    current: list[str] | None = None
    affinity: tuple[float, float, float] | None = None

    def flush() -> None:
        nonlocal current, affinity
        if current is not None and affinity is not None:
            poses.append(
                ParsedPose(
                    rank=len(poses) + 1,
                    affinity_kcal_mol=affinity[0],
                    rmsd_lb=affinity[1],
                    rmsd_ub=affinity[2],
                    block="\n".join(current).strip() + "\n",
                )
            )
        current, affinity = None, None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("MODEL"):
            flush()
            current = [line]
        elif stripped.startswith(_VINA_RESULT_PREFIX):
            parts = stripped[len(_VINA_RESULT_PREFIX):].split()
            if len(parts) >= 3 and current is not None:
                try:
                    affinity = (float(parts[0]), float(parts[1]), float(parts[2]))
                except ValueError:
                    affinity = None
            if current is not None:
                current.append(line)
        elif stripped.startswith("ENDMDL"):
            if current is not None:
                current.append(line)
            flush()
        elif current is not None:
            current.append(line)
    flush()

    if not poses and _VINA_RESULT_PREFIX in text:
        parts = text.split(_VINA_RESULT_PREFIX, 1)[1].split()
        if len(parts) >= 3:
            try:
                poses.append(
                    ParsedPose(
                        rank=1,
                        affinity_kcal_mol=float(parts[0]),
                        rmsd_lb=float(parts[1]),
                        rmsd_ub=float(parts[2]),
                        block=text.strip() + "\n",
                    )
                )
            except ValueError:
                pass
    return poses


# ---------------------------------------------------------------------------
# pose 导出（pdbqt → pdb）
# ---------------------------------------------------------------------------


def pose_pdbqt_to_pdb(pdbqt_text: str) -> str | None:
    """把单个 pose 的 PDBQT 文本转 PDB 文本；失败返回 None（调用方记 warning）。"""
    if _HAS_MEEKO_EXPORT:
        try:
            mol = RdkitMolCreate.from_pdbqt(PDBQTMolecule(pdbqt_text))[0]
            return Chem.MolToPDBBlock(mol)
        except Exception:  # noqa: BLE001 —— 回退 obabel
            pass
    obabel = shutil.which("obabel")
    if obabel is not None:
        try:
            proc = subprocess.run(
                [obabel, "-ipdbqt", "-", "-opdb"],
                input=pdbqt_text, capture_output=True, text=True,
                timeout=60, check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout
        except Exception:  # noqa: BLE001
            pass
    return None


def export_poses(
    ligand_id: str,
    poses: list[ParsedPose],
    poses_root: Path,
) -> tuple[list[dict], list[str]]:
    """切分 pose 写盘：poses/<ligand_id>/pose_NNN.pdbqt(.pdb)。

    返回 (pose 记录列表, warnings)。
    """
    warnings: list[str] = []
    target_dir = poses_root / ligand_id
    target_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    for pose in poses:
        pdbqt_name = f"pose_{pose.rank:03d}.pdbqt"
        (target_dir / pdbqt_name).write_text(pose.block, encoding="utf-8")
        pdb_name: str | None = None
        pdb_text = pose_pdbqt_to_pdb(pose.block)
        if pdb_text:
            pdb_name = f"pose_{pose.rank:03d}.pdb"
            (target_dir / pdb_name).write_text(pdb_text, encoding="utf-8")
        else:
            warnings.append(
                f"{ligand_id} pose {pose.rank}: pdbqt->pdb conversion "
                "unavailable; PDBQT retained"
            )
        records.append(
            {
                "rank": pose.rank,
                "affinity_kcal_mol": pose.affinity_kcal_mol,
                "rmsd_lb": pose.rmsd_lb,
                "rmsd_ub": pose.rmsd_ub,
                "pose_file": f"poses/{ligand_id}/{pdbqt_name}",
                "pose_pdb_file": (
                    f"poses/{ligand_id}/{pdb_name}" if pdb_name else None
                ),
            }
        )
    return records, warnings
