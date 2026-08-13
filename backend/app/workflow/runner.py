"""工作流执行器：顺序执行 DAG 各 step，持续更新 job.json，绝不吞错。

产物目录结构（提示词 5）：
outputs/<job_id>/
├── input.json, manifest.json, job.json
├── logs/
├── ligands/<ligand_id>/
├── receptor/
├── poses/<ligand_id>/
├── reports/{result.json,result.md,comparison.csv}
└── bundle.zip
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.schemas import (
    ComparisonContext,
    DockingInput,
    DockingOutput,
    ErrorCode,
    JobState,
    LigandResult,
    Pose,
    StructuredError,
)
from app.services import (
    box_service,
    comparison_service,
    interpretation_service,
    ligand_service,
    provenance_service,
    receptor_service,
    report_service,
    vina_service,
)
from app.utils.files import ensure_job_dir, make_job_id, safe_resolve
from app.utils.hashing import sha256_file
from app.utils.logging import get_logger
from app.utils.security import check_batch_size, check_upload_size
from app.workflow.states import STATE_PROGRESS, assert_transition

#: 服务层受控异常类型 → (默认阶段) 映射由调用方给出；此处统一捕获
_CONTROLLED_EXCEPTIONS = (
    ligand_service.LigandError,
    receptor_service.ReceptorError,
    box_service.BoxError,
    vina_service.VinaEngineError,
)


@dataclass
class RunOutcome:
    """run_job 的返回值。"""

    job_id: str
    job_dir: Path
    state: JobState
    output: DockingOutput | None = None
    structured_error: StructuredError | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_structured_error(exc: Exception, stage: str) -> StructuredError:
    """把任意异常转成 StructuredError（保留原始信息，绝不吞错）。"""
    if isinstance(exc, _CONTROLLED_EXCEPTIONS):
        return StructuredError(
            error_code=exc.code,
            stage=stage,
            message=str(exc),
            details=exc.details,
            recoverable=exc.recoverable,
            suggested_actions=exc.suggested_actions,
        )
    return StructuredError(
        error_code=ErrorCode.INTERNAL_ERROR,
        stage=stage,
        message=f"{type(exc).__name__}: {exc}",
        details={"exception_type": type(exc).__name__},
        suggested_actions=["check logs/workflow.log for details"],
    )


class _JobRecord:
    """job.json 的持久化状态。"""

    def __init__(self, job_dir: Path, job_id: str, job_name: str) -> None:
        self.path = job_dir / "job.json"
        self.state = JobState.CREATED
        self.data: dict = {
            "job_id": job_id,
            "job_name": job_name,
            "state": JobState.CREATED.value,
            "step": None,
            "progress": STATE_PROGRESS[JobState.CREATED],
            "started_at": _now(),
            "finished_at": None,
            "message": "created",
            "artifacts": {},
            "structured_error": None,
        }
        self.flush()

    def transition(self, target: JobState) -> None:
        assert_transition(self.state, target)
        self.state = target
        self.data["state"] = target.value
        self.data["progress"] = STATE_PROGRESS[target]

    def update(
        self,
        step: str | None = None,
        message: str | None = None,
        state: JobState | None = None,
        artifacts: dict | None = None,
    ) -> None:
        if state is not None and state is not self.state:
            self.transition(state)
        if step is not None:
            self.data["step"] = step
        if message is not None:
            self.data["message"] = message
        if artifacts:
            self.data["artifacts"].update(artifacts)
        self.flush()

    def fail(self, error: StructuredError) -> None:
        self.data["structured_error"] = error.model_dump(mode="json")
        self.data["state"] = JobState.FAILED.value
        self.data["progress"] = STATE_PROGRESS[JobState.FAILED]
        self.data["message"] = f"FAILED at {error.stage}: {error.message}"
        self.data["finished_at"] = _now()
        self.state = JobState.FAILED
        self.flush()

    def finish(self, message: str) -> None:
        self.data["message"] = message
        self.data["finished_at"] = _now()
        self.flush()

    def flush(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def run_job(docking_input: DockingInput, job_id: str | None = None) -> RunOutcome:
    """执行完整对接闭环。任何异常都会转 StructuredError 并写 FAILED。

    ``job_id`` 可选：API 层入队时预分配 job_id 以便提交后立即返回；
    未提供时按 job_name + UTC 时间戳生成。
    """
    job_id = job_id or make_job_id(docking_input.job_name)
    job_dir = ensure_job_dir(config.OUTPUTS_DIR, job_id)
    logger = get_logger("workflow", job_dir / "logs")
    record = _JobRecord(job_dir, job_id, docking_input.job_name)
    logger.info("job %s created in %s", job_id, job_dir)

    (job_dir / "input.json").write_text(
        docking_input.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    job_warnings: list[str] = []
    api_calls: list[str] = []
    results: list[LigandResult] = []
    box_dict: dict = {}
    engine_used: str | None = None
    receptor_hash: str | None = None
    receptor_path: Path | None = None
    comparison_dump: dict | None = None

    def fail(structured: StructuredError) -> RunOutcome:
        logger.error(
            "job %s FAILED at %s: [%s] %s",
            job_id, structured.stage, structured.error_code, structured.message,
        )
        record.fail(structured)
        finished = _now()
        output = DockingOutput(
            job_id=job_id,
            job_name=docking_input.job_name,
            status="FAILED",
            state=JobState.FAILED,
            results=results,
            docking_box=box_dict,
            docking_parameters=docking_input.docking_parameters.model_dump(),
            warnings=job_warnings,
            structured_error=structured,
            started_at=record.data["started_at"],
            finished_at=finished,
        )
        report_service.write_result_json(output, job_dir / "reports")
        _write_manifest(
            job_dir, job_id, docking_input, receptor_hash, results,
            structured, finished, logger, api_calls, job_warnings,
        )
        return RunOutcome(
            job_id=job_id, job_dir=job_dir, state=JobState.FAILED,
            output=output, structured_error=structured,
        )

    try:
        # -- validate_input -------------------------------------------------
        record.update("validate_input", "validating input", JobState.VALIDATING)
        check_batch_size(len(docking_input.ligands))
        logger.info("input schema valid; %d ligand(s)", len(docking_input.ligands))

        # -- prepare_ligand --------------------------------------------------
        record.update("prepare_ligand", "preparing ligands", JobState.PREPARING_LIGAND)
        prep_failed: list[StructuredError] = []
        prepared: dict[str, LigandResult] = {}
        for spec in docking_input.ligands:
            ligand_dir = job_dir / "ligands" / spec.ligand_id
            ligand_dir.mkdir(parents=True, exist_ok=True)
            try:
                result = ligand_service.prepare_ligand(
                    spec, docking_input.ligand_preparation, ligand_dir
                )
                prepared[spec.ligand_id] = result
                logger.info("ligand %s prepared", spec.ligand_id)
            except Exception as exc:  # noqa: BLE001 —— 转结构化错误并继续下一个分子
                structured = _to_structured_error(exc, "prepare_ligand")
                logger.warning(
                    "ligand %s preparation failed: [%s] %s",
                    spec.ligand_id, structured.error_code, structured.message,
                )
                prep_failed.append(structured)
                results.append(
                    LigandResult(
                        ligand_id=spec.ligand_id,
                        status="FAILED",
                        structured_error=structured,
                    )
                )
        if not prepared:
            return fail(prep_failed[0])
        if prep_failed:
            job_warnings.append(
                f"{len(prep_failed)}/{len(docking_input.ligands)} ligand(s) "
                "failed preparation; see per-ligand structured_error"
            )

        # -- analyze_receptor ------------------------------------------------
        record.update(
            "analyze_receptor", "analyzing receptor", JobState.PREPARING_RECEPTOR
        )
        try:
            receptor_path = safe_resolve(
                docking_input.receptor.source, config.PROJECT_ROOT
            )
        except ValueError as exc:
            return fail(
                StructuredError(
                    error_code=ErrorCode.INPUT_VALIDATION_FAILED,
                    stage="analyze_receptor",
                    message=str(exc),
                    suggested_actions=["keep receptor source inside the project"],
                )
            )
        if not receptor_path.is_file():
            return fail(
                StructuredError(
                    error_code=ErrorCode.FILE_NOT_FOUND,
                    stage="analyze_receptor",
                    message=f"receptor file not found: {receptor_path}",
                )
            )
        check_upload_size(receptor_path)
        receptor_hash = sha256_file(receptor_path)
        (job_dir / "receptor" / "receptor_original.pdb").write_bytes(
            receptor_path.read_bytes()
        )
        report = receptor_service.analyze_receptor(receptor_path)
        logger.info(
            "receptor analyzed: chains=%s atoms=%d",
            report["chains"], report["atom_count"],
        )

        # -- prepare_receptor ------------------------------------------------
        record.update(
            "prepare_receptor", "cleaning receptor and writing pdbqt",
        )
        clean_pdb = job_dir / "receptor" / "receptor_clean.pdb"
        cleaning_summary, clean_warnings = receptor_service.clean_receptor(
            report, docking_input.receptor.config, clean_pdb
        )
        job_warnings.extend(clean_warnings)
        receptor_pdbqt = job_dir / "receptor" / "receptor.pdbqt"
        receptor_tool, receptor_pdbqt_warnings = (
            receptor_service.prepare_receptor_pdbqt(clean_pdb, receptor_pdbqt)
        )
        job_warnings.extend(receptor_pdbqt_warnings)
        api_calls.append(f"receptor pdbqt via {receptor_tool}")
        receptor_service.write_preparation_report(
            report, cleaning_summary, clean_warnings,
            job_dir / "receptor" / "receptor_preparation_report.json",
        )
        record.update(
            artifacts={
                "receptor_original": "receptor/receptor_original.pdb",
                "receptor_clean": "receptor/receptor_clean.pdb",
                "receptor_pdbqt": "receptor/receptor.pdbqt",
                "receptor_report": "receptor/receptor_preparation_report.json",
            }
        )

        # -- validate_box ----------------------------------------------------
        record.update("validate_box", "building docking box", JobState.VALIDATING_BOX)
        box_report = dict(report)
        box_report["bounding_box"] = receptor_service.bounding_box_from_report(report)
        box_result = box_service.build_box(docking_input.docking_box, box_report)
        job_warnings.extend(box_result.warnings)
        box_dict = {
            "mode": box_result.mode,
            "center": box_result.center,
            "size": box_result.size,
            "volume_angstrom3": box_result.volume_angstrom3,
            "units": "angstrom",
        }
        logger.info("box ready: %s", box_dict)

        # -- configure_vina --------------------------------------------------
        record.update("configure_vina", "configuring vina engine", JobState.DOCKING)
        engine = vina_service.engine_status()
        api_calls.append(
            f"vina adapters: python_api={engine['python_api_available']}, "
            f"cli={engine['cli_available']}"
        )

        # -- run_vina / parse_scores / export_poses ---------------------------
        record.update("run_vina", "running vina docking")
        docking_logs = job_dir / "logs"
        for ligand_id, result in prepared.items():
            ligand_pdbqt = job_dir / "ligands" / ligand_id / "ligand.pdbqt"
            try:
                dock_run = vina_service.dock_one(
                    receptor_pdbqt, ligand_pdbqt,
                    box_result.center, box_result.size,
                    docking_input.docking_parameters, docking_logs,
                )
            except Exception as exc:  # noqa: BLE001 —— 逐分子受控失败
                structured = _to_structured_error(exc, "run_vina")
                result.status = "FAILED"
                result.structured_error = structured
                results.append(result)
                job_warnings.append(
                    f"ligand {ligand_id} docking failed: {structured.message}"
                )
                continue
            engine_used = dock_run.engine_used
            api_calls.append(
                f"dock {ligand_id} via {dock_run.engine_used} "
                f"(seed={docking_input.docking_parameters.seed})"
            )
            (job_dir / "ligands" / ligand_id / "vina_output.pdbqt").write_text(
                dock_run.output_text, encoding="utf-8"
            )
            record.update("parse_scores", f"parsing scores for {ligand_id}")
            parsed = vina_service.parse_vina_output(dock_run.output_text)
            if not parsed:
                result.status = "FAILED"
                result.structured_error = StructuredError(
                    error_code=ErrorCode.NO_POSE,
                    stage="parse_scores",
                    message="vina produced no parseable pose",
                    suggested_actions=["check box placement and ligand pdbqt"],
                )
                results.append(result)
                continue
            record.update("export_poses", f"exporting poses for {ligand_id}")
            pose_records, pose_warnings = vina_service.export_poses(
                ligand_id, parsed, job_dir / "poses"
            )
            result.poses = [Pose(**rec) for rec in pose_records]
            result.best_affinity_kcal_mol = result.poses[0].affinity_kcal_mol
            heavy = result.descriptors.get("heavy_atom_count") or 0
            if heavy > 0:
                result.ligand_efficiency = round(
                    -result.best_affinity_kcal_mol / heavy, 4
                )
            result.warnings.extend(pose_warnings)
            result.provenance["vina_engine"] = dock_run.engine_used
            result.artifacts["vina_output"] = (
                f"ligands/{ligand_id}/vina_output.pdbqt"
            )
            results.append(result)
            logger.info(
                "ligand %s docked: best=%.3f kcal/mol, %d pose(s)",
                ligand_id, result.best_affinity_kcal_mol, len(result.poses),
            )

        if not any(r.status == "SUCCESS" for r in results):
            first_error = next(
                (r.structured_error for r in results if r.structured_error),
                None,
            ) or StructuredError(
                error_code=ErrorCode.VINA_FAILED,
                stage="run_vina",
                message="no ligand produced any pose",
            )
            return fail(first_error)

        # -- calculate_metrics / interpret ------------------------------------
        record.update("parse_scores", "scores parsed", JobState.PARSING)
        record.update("calculate_metrics", "computing metrics", JobState.ANALYZING)
        context = ComparisonContext(
            receptor_sha256=receptor_hash,
            box_mode=box_result.mode,
            box_center=box_result.center,
            box_size=box_result.size,
            docking_parameters=docking_input.docking_parameters.model_dump(),
        )
        comparison = comparison_service.compare_in_batch(
            results, context=context, job_id=job_id
        )
        comparison_dump = comparison.model_dump(mode="json")

        record.update("interpret", "writing reports")
        output_finished = _now()
        output = DockingOutput(
            job_id=job_id,
            job_name=docking_input.job_name,
            status="SUCCESS",
            state=JobState.SUCCESS,
            results=results,
            docking_box=box_dict,
            docking_parameters=docking_input.docking_parameters.model_dump(),
            warnings=job_warnings,
            structured_error=None,
            started_at=record.data["started_at"],
            finished_at=output_finished,
        )
        report_service.write_result_json(output, job_dir / "reports")
        report_service.write_comparison_csv(comparison, job_dir / "reports")
        markdown = interpretation_service.build_result_markdown(
            job_id=job_id,
            job_name=docking_input.job_name,
            results=[r.model_dump(mode="json") for r in results],
            box=box_dict,
            parameters=docking_input.docking_parameters.model_dump(),
            comparison=comparison_dump,
            warnings=job_warnings,
        )
        (job_dir / "reports" / "result.md").write_text(markdown, encoding="utf-8")

        # -- generate_manifest ------------------------------------------------
        record.update("generate_manifest", "building manifest", JobState.PACKAGING)
        _write_manifest(
            job_dir, job_id, docking_input, receptor_hash, results,
            None, output_finished, logger, api_calls, job_warnings,
        )

        # -- package_artifacts ------------------------------------------------
        record.update("package_artifacts", "packaging bundle.zip")
        _package_bundle(job_dir, results)

        # -- 完成 -------------------------------------------------------------
        record.transition(JobState.SUCCESS)
        record.finish(
            f"success: {sum(1 for r in results if r.status == 'SUCCESS')}"
            f"/{len(results)} ligand(s) docked"
        )
        logger.info("job %s finished: %s", job_id, record.data["message"])
        return RunOutcome(
            job_id=job_id, job_dir=job_dir, state=JobState.SUCCESS, output=output
        )

    except Exception as exc:  # noqa: BLE001 —— 兜底：任何未受控异常也转结构化错误
        logger.exception("job %s crashed", job_id)
        return fail(_to_structured_error(exc, record.data.get("step") or "unknown"))


def _write_manifest(
    job_dir: Path,
    job_id: str,
    docking_input: DockingInput,
    receptor_hash: str | None,
    results: list[LigandResult],
    structured_error: StructuredError | None,
    finished_at: str,
    logger,
    api_calls: list[str],
    warnings: list[str],
) -> None:
    """组装并写 manifest.json（成功与失败路径共用）。"""
    input_hash = sha256_file(job_dir / "input.json")
    ligand_hashes: dict[str, str] = {}
    for result in results:
        pdbqt = job_dir / "ligands" / result.ligand_id / "ligand.pdbqt"
        if pdbqt.is_file():
            ligand_hashes[result.ligand_id] = sha256_file(pdbqt)
    artifact_paths = [
        "input.json",
        "reports/result.json",
        "reports/result.md",
        "reports/comparison.csv",
        "receptor/receptor_clean.pdb",
        "receptor/receptor.pdbqt",
        *(
            pose.pose_file
            for r in results
            for pose in r.poses[:3]
        ),
    ]
    manifest = provenance_service.build_manifest(
        job_id=job_id,
        job_name=docking_input.job_name,
        input_sha256=input_hash,
        receptor_sha256=receptor_hash,
        ligand_sha256=ligand_hashes,
        parameters=docking_input.docking_parameters.model_dump(),
        seed=docking_input.docking_parameters.seed,
        commands_or_api_calls=api_calls,
        started_at=_job_started_at(job_dir),
        finished_at=finished_at,
        status="FAILED" if structured_error else "SUCCESS",
        warnings=warnings,
        errors=[structured_error.model_dump(mode="json")] if structured_error else [],
        artifact_sha256=provenance_service.hash_artifacts(job_dir, artifact_paths),
    )
    (job_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("manifest.json written (%d artifacts hashed)", len(manifest["artifact_sha256"]))


def _job_started_at(job_dir: Path) -> str:
    try:
        return json.loads((job_dir / "job.json").read_text(encoding="utf-8"))[
            "started_at"
        ]
    except Exception:  # noqa: BLE001
        return _now()


def _package_bundle(job_dir: Path, results: list[LigandResult]) -> None:
    """打包 bundle.zip：manifest + 报告 + 每分子 top-3 pose（pdbqt/pdb）。"""
    bundle = job_dir / "bundle.zip"
    members = ["manifest.json", "reports/result.json", "reports/result.md",
               "reports/comparison.csv"]
    for result in results:
        for pose in result.poses[:3]:
            members.append(pose.pose_file)
            if pose.pose_pdb_file:
                members.append(pose.pose_pdb_file)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for member in members:
            target = job_dir / member
            if target.is_file():
                zf.write(target, arcname=member)


def _jsonable(value):
    """递归净化为可 JSON 序列化结构（ValidationError.errors() 的 ctx 可能含异常对象）。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def run_job_from_json(payload: dict) -> RunOutcome:
    """便捷入口：从 dict 校验 schema 后执行（schema 错误转结构化错误）。"""
    from pydantic import ValidationError

    try:
        docking_input = DockingInput.model_validate(payload)
    except ValidationError as exc:
        structured = StructuredError(
            error_code=ErrorCode.INPUT_VALIDATION_FAILED,
            stage="validate_input",
            message="input failed schema validation",
            details={"errors": _jsonable(exc.errors())},
        )
        return RunOutcome(
            job_id="", job_dir=config.OUTPUTS_DIR, state=JobState.FAILED,
            structured_error=structured,
        )
    return run_job(docking_input)
