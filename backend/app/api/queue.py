"""单一后台守护线程串行任务队列（结构性并发 = 1，无 Redis/Celery/数据库）。

POST 端点只做校验 + 入队并立即返回 ``{"job_id", "state": "CREATED"}``；
job 状态完全由 ``outputs/<job_id>/job.json`` 文件承载，守护线程逐步实时更新。
任务类型：

- ``docking``：完整对接闭环（委托 :func:`app.workflow.runner.run_job`）；
- ``ligand_prepare``：仅分子 3D 准备（SMILES → SDF/PDB/PDBQT/SVG）；
- ``receptor_prepare``：仅受体清洗 + PDBQT 准备。

绝不吞错：任务函数抛出的受控异常（携带 ``code``/``details`` 等属性）
转为结构化错误写 FAILED；未受控异常兜底转 INTERNAL_ERROR 并记录日志。
"""

from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app import config
from app.schemas import DockingInput, ErrorCode, JobState, StructuredError
from app.utils.files import ensure_job_dir, make_job_id, safe_resolve
from app.utils.logging import get_logger
from app.workflow import runner
from app.workflow.states import STATE_PROGRESS

logger = get_logger("api.queue")

_QUEUE: "queue.Queue[tuple[str, str, Callable[[], None]]]" = queue.Queue()
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()

#: job.json 中允许持久化的字段（不把大型结构内容塞入状态 JSON）
_JOB_FIELDS = (
    "job_id",
    "job_name",
    "state",
    "step",
    "progress",
    "started_at",
    "finished_at",
    "message",
    "artifacts",
    "structured_error",
)

#: 状态 → 进度百分比
_PROGRESS = dict(STATE_PROGRESS)
_PROGRESS.setdefault(JobState.CANCELLED, 100)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _outputs_root() -> Path:
    """运行期解析 outputs 根目录（支持测试通过环境变量隔离）。"""
    return Path(config.OUTPUTS_DIR)


def resolve_job_dir(job_id: str) -> Path:
    """解析 ``outputs/<job_id>``（防路径穿越）。由 API GET/DELETE 端点共用。"""
    return safe_resolve(job_id, _outputs_root())


# ---------------------------------------------------------------------------
# job.json 读写（状态唯一事实来源是文件）
# ---------------------------------------------------------------------------


def create_job_record(job_id: str, job_name: str, kind: str) -> Path:
    """入队时立即创建产物目录并写初始 job.json（state=CREATED）。"""
    job_dir = ensure_job_dir(_outputs_root(), job_id)
    record = {
        "job_id": job_id,
        "job_name": job_name,
        "state": JobState.CREATED.value,
        "step": "enqueue",
        "progress": _PROGRESS[JobState.CREATED],
        "started_at": _now(),
        "finished_at": None,
        "message": f"queued ({kind})",
        "artifacts": {},
        "structured_error": None,
    }
    _write_job_json(job_dir / "job.json", record)
    return job_dir


def _write_job_json(path: Path, record: dict) -> None:
    """原子写 job.json：先写同目录临时文件再 os.replace，避免读到半截 JSON。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(_dumps(record), encoding="utf-8")
    os.replace(tmp, path)


def _dumps(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def update_job(
    job_dir: Path,
    *,
    step: str | None = None,
    message: str | None = None,
    state: JobState | None = None,
    artifacts: dict | None = None,
) -> None:
    """实时更新 job.json 的 step/message/state/artifacts 字段。"""
    path = job_dir / "job.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    if state is not None and record.get("state") != state.value:
        record["state"] = state.value
        record["progress"] = _PROGRESS[state]
    if step is not None:
        record["step"] = step
    if message is not None:
        record["message"] = message
    if artifacts:
        record.setdefault("artifacts", {}).update(artifacts)
    _write_job_json(path, record)


def fail_job(job_dir: Path, error: StructuredError) -> None:
    """把 job.json 置为 FAILED 并写入结构化错误（绝不吞错）。"""
    path = job_dir / "job.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["state"] = JobState.FAILED.value
    record["progress"] = _PROGRESS[JobState.FAILED]
    record["structured_error"] = error.model_dump(mode="json")
    record["message"] = f"FAILED at {error.stage}: {error.message}"
    record["finished_at"] = _now()
    _write_job_json(path, record)


def finish_job(job_dir: Path, message: str) -> None:
    """把 job.json 置为 SUCCESS 并记录完成时间。"""
    path = job_dir / "job.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["state"] = JobState.SUCCESS.value
    record["progress"] = _PROGRESS[JobState.SUCCESS]
    record["message"] = message
    record["finished_at"] = _now()
    _write_job_json(path, record)


# ---------------------------------------------------------------------------
# 入队与守护线程
# ---------------------------------------------------------------------------


def allocate_job_id(job_name: str) -> str:
    """生成未占用的 job_id（同秒同名冲突时附加序号）。

    用 try mkdir 原子占用目录，捕获 FileExistsError 后递增序号重试，
    避免 check-then-act 竞态。
    """
    root = _outputs_root()
    counter = 0
    while True:
        job_id = make_job_id(job_name) if counter == 0 else f"{make_job_id(job_name)}-{counter}"
        try:
            (root / job_id).mkdir(parents=True)
        except FileExistsError:
            counter += 1
            continue
        return job_id


def enqueue_job(job_id: str, job_name: str, kind: str, task: Callable[[], None]) -> None:
    """创建初始 job.json 并把任务入队（由唯一守护线程串行消费）。"""
    create_job_record(job_id, job_name, kind)
    _QUEUE.put((job_id, kind, task))
    logger.info("job %s enqueued (%s); queue_size=%d", job_id, kind, _QUEUE.qsize())


def _execute(job_id: str, kind: str, task: Callable[[], None]) -> None:
    """执行单个任务；任何异常都转为 FAILED + 结构化错误写入 job.json。"""
    try:
        job_dir = resolve_job_dir(job_id)
    except Exception as exc:  # noqa: BLE001 —— job_id 非法（入队前已校验，兜底）
        logger.exception("job %s: unresolvable job dir", job_id)
        logger.error("%s", exc)
        return
    try:
        task()
    except Exception as exc:  # noqa: BLE001 —— 兜底：绝不吞错
        logger.exception("job %s (%s) crashed", job_id, kind)
        code = getattr(exc, "code", ErrorCode.INTERNAL_ERROR)
        details = getattr(exc, "details", None) or {
            "exception_type": type(exc).__name__
        }
        fail_job(
            job_dir,
            StructuredError(
                error_code=code,
                stage=kind,
                message=f"{type(exc).__name__}: {exc}",
                details=details,
                recoverable=bool(getattr(exc, "recoverable", False)),
                suggested_actions=list(
                    getattr(exc, "suggested_actions", None)
                    or ["check logs/workflow.log for details"]
                ),
            ),
        )


def _worker_loop() -> None:
    while True:
        job_id, kind, task = _QUEUE.get()
        try:
            _execute(job_id, kind, task)
        finally:
            _QUEUE.task_done()


def start_worker() -> None:
    """启动唯一后台守护线程（daemon=True，重复调用安全）。"""
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _WORKER = threading.Thread(
            target=_worker_loop, name="dockskill-job-queue", daemon=True
        )
        _WORKER.start()
        logger.info("job queue worker started (serial, concurrency=1)")


def wait_idle(timeout: float = 600.0) -> None:
    """阻塞直到队列为空（仅测试辅助使用）。"""
    _QUEUE.join()


# ---------------------------------------------------------------------------
# 任务实现
# ---------------------------------------------------------------------------


def make_docking_task(docking_input: DockingInput, job_id: str) -> Callable[[], None]:
    """完整对接闭环任务（run_job 内部自行捕获异常并写 FAILED，不向外抛）。"""

    def task() -> None:
        runner.run_job(docking_input, job_id=job_id)

    return task


def make_ligand_prepare_task(payload: dict, job_id: str) -> Callable[[], None]:
    """仅分子准备任务：逐分子执行 prepare_ligand，受控失败逐个记录不吞错。"""
    from app.schemas import LigandPreparation, LigandSpec
    from app.services import ligand_service

    specs = [LigandSpec.model_validate(item) for item in payload["ligands"]]
    prep = LigandPreparation.model_validate(payload.get("ligand_preparation") or {})

    def task() -> None:
        job_dir = resolve_job_dir(job_id)
        job_logger = get_logger("ligand_prepare", job_dir / "logs")
        update_job(
            job_dir, step="validate_input", message="validating input",
            state=JobState.VALIDATING,
        )
        update_job(
            job_dir, step="prepare_ligand", message="preparing ligands",
            state=JobState.PREPARING_LIGAND,
        )
        errors: list[StructuredError] = []
        ok = 0
        for spec in specs:
            ligand_dir = job_dir / "ligands" / spec.ligand_id
            ligand_dir.mkdir(parents=True, exist_ok=True)
            try:
                result = ligand_service.prepare_ligand(spec, prep, ligand_dir)
                ok += 1
                # 批量模式下给 artifacts 键加 ligand_id 前缀，避免同名键互相覆盖
                prefixed = {
                    f"{spec.ligand_id}/{k}": v for k, v in result.artifacts.items()
                }
                update_job(
                    job_dir, artifacts=prefixed,
                    message=f"prepared {spec.ligand_id}",
                )
                job_logger.info("ligand %s prepared", spec.ligand_id)
            except Exception as exc:  # noqa: BLE001 —— 逐分子受控失败，绝不吞错
                structured = runner._to_structured_error(exc, "prepare_ligand")
                errors.append(structured)
                job_logger.warning(
                    "ligand %s failed: [%s] %s",
                    spec.ligand_id, structured.error_code, structured.message,
                )
        if errors and ok == 0:
            fail_job(job_dir, errors[0])
            return
        if errors:
            update_job(
                job_dir,
                message=(
                    f"partial: {ok}/{len(specs)} ligand(s) prepared; "
                    f"{len(errors)} failed (see logs)"
                ),
            )
        finish_job(job_dir, f"prepared {ok}/{len(specs)} ligand(s)")

    return task


def make_receptor_prepare_task(payload: dict, job_id: str) -> Callable[[], None]:
    """仅受体准备任务：分析 → 按配置清洗 → Meeko 生成 receptor.pdbqt。"""
    from app.schemas import ReceptorConfig, ReceptorRef
    from app.services import receptor_service

    ref = ReceptorRef.model_validate(
        {
            "source": payload["source"],
            "config": payload.get("config") or {},
        }
    )

    def task() -> None:
        from app.utils.hashing import sha256_file

        job_dir = resolve_job_dir(job_id)
        job_logger = get_logger("receptor_prepare", job_dir / "logs")
        update_job(
            job_dir, step="validate_input", message="validating input",
            state=JobState.VALIDATING,
        )
        source_path = safe_resolve(ref.source, config.PROJECT_ROOT)
        if not source_path.is_file():
            fail_job(
                job_dir,
                StructuredError(
                    error_code=ErrorCode.FILE_NOT_FOUND,
                    stage="analyze_receptor",
                    message=f"receptor file not found: {source_path}",
                ),
            )
            return
        update_job(
            job_dir, step="analyze_receptor", message="analyzing receptor",
            state=JobState.PREPARING_RECEPTOR,
        )
        (job_dir / "receptor" / "receptor_original.pdb").write_bytes(
            source_path.read_bytes()
        )
        report = receptor_service.analyze_receptor(source_path)
        update_job(job_dir, step="prepare_receptor", message="cleaning receptor")
        clean_pdb = job_dir / "receptor" / "receptor_clean.pdb"
        summary, clean_warnings = receptor_service.clean_receptor(
            report, ref.config, clean_pdb
        )
        pdbqt = job_dir / "receptor" / "receptor.pdbqt"
        tool, pdbqt_warnings = receptor_service.prepare_receptor_pdbqt(
            clean_pdb, pdbqt
        )
        receptor_service.write_preparation_report(
            report, summary, clean_warnings + pdbqt_warnings,
            job_dir / "receptor" / "receptor_preparation_report.json",
        )
        update_job(
            job_dir,
            artifacts={
                "receptor_original": "receptor/receptor_original.pdb",
                "receptor_clean": "receptor/receptor_clean.pdb",
                "receptor_pdbqt": "receptor/receptor.pdbqt",
                "receptor_report": "receptor/receptor_preparation_report.json",
            },
        )
        job_logger.info(
            "receptor prepared via %s; sha256=%s", tool, sha256_file(source_path)[:12]
        )
        finish_job(
            job_dir,
            f"receptor prepared via {tool}; "
            f"remaining_atoms={summary['remaining_atoms']}",
        )

    return task
