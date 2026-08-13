"""输入/输出 Pydantic Schema —— 全项目单一事实来源。

覆盖：分子输入与准备参数、受体配置、搜索盒（四模式）、Vina 参数、
单分子结果（Pose / LigandResult）、整批输出（DockingOutput）、
比较上下文与输出（ComparisonContext / ComparisonOutput）、
结构化错误（StructuredError）与工作流状态（JobState 12 态）。

单位约定：
- 几何量（box center/size、坐标）单位为 Å（Angstrom）；
- 结合亲和力 affinity 单位为 kcal/mol；
- 能量类字段均在字段描述中显式标注单位。
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app import config

# ---------------------------------------------------------------------------
# 结构化错误码（字符串常量，跨进程/跨语言稳定；与 docs/FAILURE_CASES.md 对齐）
# ---------------------------------------------------------------------------


class ErrorCode:
    """结构化错误码常量集合。"""

    INPUT_VALIDATION_FAILED = "INPUT_VALIDATION_FAILED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    INVALID_SMILES = "INVALID_SMILES"
    MULTI_FRAGMENT_LIGAND = "MULTI_FRAGMENT_LIGAND"
    UNSUPPORTED_ELEMENT = "UNSUPPORTED_ELEMENT"
    LIGAND_TOO_LARGE = "LIGAND_TOO_LARGE"
    CONFORMER_GENERATION_FAILED = "CONFORMER_GENERATION_FAILED"
    PDBQT_PREPARATION_FAILED = "PDBQT_PREPARATION_FAILED"
    INVALID_RECEPTOR = "INVALID_RECEPTOR"
    CHAIN_NOT_FOUND = "CHAIN_NOT_FOUND"
    RECEPTOR_PREPARATION_FAILED = "RECEPTOR_PREPARATION_FAILED"
    INVALID_BOX = "INVALID_BOX"
    BOX_OUTSIDE_RECEPTOR = "BOX_OUTSIDE_RECEPTOR"
    BOX_TOO_LARGE = "BOX_TOO_LARGE"
    VINA_FAILED = "VINA_FAILED"
    VINA_TIMEOUT = "VINA_TIMEOUT"
    NO_POSE = "NO_POSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# 工作流状态机（12 态；转移表见 app/workflow/states.py）
# ---------------------------------------------------------------------------


class JobState(str, Enum):
    """对接任务的 12 个生命周期状态。"""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PREPARING_LIGAND = "PREPARING_LIGAND"
    PREPARING_RECEPTOR = "PREPARING_RECEPTOR"
    VALIDATING_BOX = "VALIDATING_BOX"
    DOCKING = "DOCKING"
    PARSING = "PARSING"
    ANALYZING = "ANALYZING"
    PACKAGING = "PACKAGING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# 输入模型
# ---------------------------------------------------------------------------


class LigandSpec(BaseModel):
    """单个小分子输入。"""

    ligand_id: str = Field(..., min_length=1, max_length=64)
    smiles: str = Field(..., min_length=1, max_length=500)
    name: str | None = None


#: 向后兼容别名（Phase 0 命名）
LigandInput = LigandSpec


class LigandPreparation(BaseModel):
    """小分子 3D 准备参数（默认值与提示词 3 规范一致）。"""

    add_hydrogens: bool = True
    embed_method: Literal["ETKDGv3"] = "ETKDGv3"
    num_conformers: int = Field(10, ge=1, le=50)
    optimize_force_field: Literal["MMFF94", "UFF"] = "MMFF94"
    max_iterations: int = Field(500, ge=0, le=10000)
    select_conformer_by: Literal["minimum_force_field_energy"] = (
        "minimum_force_field_energy"
    )
    random_seed: int = 42


class ReceptorConfig(BaseModel):
    """受体清洗策略（每个决策可配置、可解释、可追踪，不做无条件删水/删异源）。"""

    selected_chains: list[str] | None = Field(
        default=None, description="保留的链 ID 列表；None 表示保留全部链"
    )
    keep_waters: bool = False
    keep_cofactors: list[str] = Field(default_factory=list)
    keep_metals: list[str] = Field(default_factory=list)
    remove_original_ligands: bool = True
    alternate_location_policy: Literal["highest_occupancy", "keep_all"] = (
        "highest_occupancy"
    )
    missing_residue_policy: Literal["warn", "error"] = "warn"
    protonation_policy: Literal["tool_default"] = "tool_default"


class ReceptorRef(BaseModel):
    """受体引用：仓库内相对路径或 outputs 内 job 产物路径。"""

    source: str = Field(..., min_length=1)
    config: ReceptorConfig = Field(default_factory=ReceptorConfig)


class DockingBox(BaseModel):
    """docking 搜索盒（单位 Å），支持四种模式。

    - explicit：显式 center/size（center 单位 Å，size 单边长度单位 Å）；
    - reference_ligand：按已知共晶配体残基坐标生成（padding 单位 Å）；
    - residue_list：按指定口袋残基生成（padding 单位 Å）；
    - whole_receptor：全受体包围盒（仅小型测试，附强警告）。
    """

    mode: Literal[
        "explicit", "reference_ligand", "residue_list", "whole_receptor"
    ] = "explicit"
    center: list[float] | None = Field(
        default=None, min_length=3, max_length=3, description="盒中心坐标（Å）"
    )
    size: list[float] | None = Field(
        default=None, min_length=3, max_length=3, description="盒边长（Å）"
    )
    reference_ligand_resid: str | None = Field(
        default=None, description="参考配体残基标识，如 'LIG' 或 'A/1437'"
    )
    residue_ids: list[str] | None = Field(
        default=None, description="口袋残基标识列表，如 ['A/585', 'A/600']"
    )
    padding_angstrom: float = Field(
        8.0, ge=0.0, le=12.0, description="reference/residue 模式的盒外扩（Å）"
    )
    units: Literal["angstrom"] = "angstrom"

    @model_validator(mode="after")
    def _check_mode_fields(self) -> "DockingBox":
        if self.mode == "explicit":
            if self.center is None or self.size is None:
                raise ValueError(
                    "explicit box mode requires both center and size"
                )
            for coord in self.center:
                if not math.isfinite(coord):
                    raise ValueError(
                        f"box center must be finite floats, got {coord}"
                    )
            for edge in self.size:
                if not math.isfinite(edge) or edge <= 0:
                    raise ValueError("box size must be positive finite floats")
                if not config.BOX_EDGE_MIN <= edge <= config.BOX_EDGE_MAX:
                    raise ValueError(
                        f"box edge {edge} outside [{config.BOX_EDGE_MIN}, "
                        f"{config.BOX_EDGE_MAX}] Angstrom"
                    )
            volume = self.size[0] * self.size[1] * self.size[2]
            if volume > config.BOX_VOLUME_MAX:
                raise ValueError(
                    f"box volume {volume} exceeds limit "
                    f"{config.BOX_VOLUME_MAX} A^3"
                )
        elif self.mode == "reference_ligand" and not self.reference_ligand_resid:
            raise ValueError(
                "reference_ligand mode requires reference_ligand_resid"
            )
        elif self.mode == "residue_list" and not self.residue_ids:
            raise ValueError("residue_list mode requires residue_ids")
        return self


class VinaParams(BaseModel):
    """AutoDock Vina 对接参数。"""

    scoring_function: Literal["vina"] = "vina"
    exhaustiveness: int = Field(
        config.EXHAUSTIVENESS_DEFAULT,
        ge=config.EXHAUSTIVENESS_MIN,
        le=config.EXHAUSTIVENESS_MAX,
    )
    num_modes: int = Field(config.NUM_MODES_DEFAULT, ge=1, le=20)
    energy_range: float = Field(
        3.0, ge=0.0, le=10.0, description="保留 pose 的能量窗口（kcal/mol）"
    )
    cpu: int = Field(config.CPU_DEFAULT, ge=1, le=config.CPU_MAX)
    seed: int = config.VINA_SEED_DEFAULT


#: 向后兼容别名（Phase 0 命名）
DockingParameters = VinaParams


class DockingInput(BaseModel):
    """一次对接任务的完整输入。"""

    job_name: str = Field(..., min_length=1, max_length=128)
    ligands: list[LigandSpec] = Field(..., min_length=1)
    ligand_preparation: LigandPreparation = Field(
        default_factory=LigandPreparation
    )
    receptor: ReceptorRef
    docking_box: DockingBox = Field(default_factory=DockingBox)
    docking_parameters: VinaParams = Field(default_factory=VinaParams)

    @field_validator("ligands")
    @classmethod
    def _check_batch(cls, v: list[LigandSpec]) -> list[LigandSpec]:
        if len(v) > config.BATCH_MAX_LIGANDS:
            raise ValueError(
                f"too many ligands: {len(v)} > {config.BATCH_MAX_LIGANDS}"
            )
        ids = [spec.ligand_id for spec in v]
        if len(set(ids)) != len(ids):
            raise ValueError("ligand_id must be unique within one job")
        return v


# ---------------------------------------------------------------------------
# 输出模型
# ---------------------------------------------------------------------------


class Pose(BaseModel):
    """单个对接 pose。affinity 单位 kcal/mol，rmsd 单位 Å。"""

    rank: int
    affinity_kcal_mol: float
    rmsd_lb: float
    rmsd_ub: float
    pose_file: str = Field(..., description="PDBQT pose 文件（job 目录相对路径）")
    pose_pdb_file: str | None = Field(
        default=None, description="PDB pose 文件（job 目录相对路径）"
    )


class LigandResult(BaseModel):
    """单分子对接结果。affinity 单位 kcal/mol。"""

    ligand_id: str
    status: Literal["SUCCESS", "FAILED"]
    best_affinity_kcal_mol: float | None = None
    poses: list[Pose] = Field(default_factory=list)
    ligand_efficiency: float | None = Field(
        default=None,
        description="-best_affinity / heavy_atom_count（kcal/mol/重原子，仅辅助指标）",
    )
    descriptors: dict = Field(default_factory=dict)
    preparation_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    structured_error: "StructuredError | None" = None


class StructuredError(BaseModel):
    """结构化错误：贯穿所有阶段的统一错误表达，绝不吞错。"""

    error_code: str
    stage: str
    message: str
    details: dict = Field(default_factory=dict)
    recoverable: bool = False
    suggested_actions: list[str] = Field(default_factory=list)


LigandResult.model_rebuild()


class DockingOutput(BaseModel):
    """一次对接任务的完整输出（写入 reports/result.json）。"""

    job_id: str
    job_name: str
    status: str
    state: JobState
    results: list[LigandResult] = Field(default_factory=list)
    docking_box: dict = Field(default_factory=dict)
    docking_parameters: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    structured_error: StructuredError | None = None
    started_at: str
    finished_at: str | None = None
    runtime_seconds: float | None = None


class ComparisonContext(BaseModel):
    """比较上下文：只有同受体/同准备/同 box/同参数才可相对比较。"""

    receptor_sha256: str | None = None
    box_mode: str | None = None
    box_center: list[float] | None = None
    box_size: list[float] | None = None
    docking_parameters: dict = Field(default_factory=dict)
    consistent: bool = True
    notes: list[str] = Field(default_factory=list)


class ComparisonOutput(BaseModel):
    """批次内相对比较结果（展示性指标，公式见 normalization_method）。"""

    job_id: str
    context: ComparisonContext
    ligand_ids: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    normalization_method: str
    disclaimer: str = (
        "相对指标仅用于同一批次、同一受体与同一参数下的展示性排序，"
        "不是绝对结合概率、实验自由能或药效。"
    )
