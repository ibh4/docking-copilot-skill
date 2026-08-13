/**
 * 前端类型定义：与冻结 API 契约及 schemas/*.schema.json 对齐。
 * 禁止使用 any；对后端可能出现的可选字段一律显式标注。
 */

// ---------- Job 生命周期 ----------

export const JOB_STATES = [
  'CREATED',
  'VALIDATING',
  'PREPARING_LIGAND',
  'PREPARING_RECEPTOR',
  'VALIDATING_BOX',
  'DOCKING',
  'PARSING',
  'ANALYZING',
  'PACKAGING',
  'SUCCESS',
  'FAILED',
  'CANCELLED',
] as const;

export type JobState = (typeof JOB_STATES)[number];

export const TERMINAL_STATES: readonly JobState[] = ['SUCCESS', 'FAILED', 'CANCELLED'];

// ---------- 结构化错误 ----------

export interface StructuredError {
  error_code: string;
  stage: string;
  message: string;
  details?: Record<string, unknown>;
  recoverable?: boolean;
  suggested_actions?: string[];
}

// ---------- 输入（DockingInput） ----------

export interface LigandSpec {
  ligand_id: string;
  smiles: string;
  name?: string | null;
}

export type BoxMode = 'explicit' | 'reference_ligand' | 'residue_list' | 'whole_receptor';

export interface DockingBox {
  mode?: BoxMode;
  center?: [number, number, number] | null;
  size?: [number, number, number] | null;
  reference_ligand_resid?: string | null;
  residue_ids?: string[] | null;
  padding_angstrom?: number;
  units?: 'angstrom';
}

export interface LigandPreparation {
  add_hydrogens?: boolean;
  embed_method?: 'ETKDGv3';
  num_conformers?: number;
  optimize_force_field?: 'MMFF94' | 'UFF';
  max_iterations?: number;
  select_conformer_by?: 'minimum_force_field_energy';
  random_seed?: number;
}

export interface ReceptorConfig {
  selected_chains?: string[] | null;
  keep_waters?: boolean;
  keep_cofactors?: string[];
  keep_metals?: string[];
  remove_original_ligands?: boolean;
  alternate_location_policy?: 'highest_occupancy' | 'keep_all';
  missing_residue_policy?: 'warn' | 'error';
  protonation_policy?: 'tool_default';
}

export interface ReceptorRef {
  source: string;
  config?: ReceptorConfig;
}

export interface VinaParams {
  scoring_function?: 'vina';
  exhaustiveness?: number;
  num_modes?: number;
  energy_range?: number;
  cpu?: number;
  seed?: number;
}

export interface DockingInput {
  job_name: string;
  ligands: LigandSpec[];
  ligand_preparation?: LigandPreparation;
  receptor: ReceptorRef;
  docking_box?: DockingBox;
  docking_parameters?: VinaParams;
}

// ---------- 任务状态 ----------

export interface SubmitResponse {
  job_id: string;
  state: string;
}

export interface ArtifactEntry {
  path?: string;
  name?: string;
  description?: string;
  size_bytes?: number;
}

export interface JobStatus {
  job_id?: string;
  state: JobState;
  step?: string | null;
  progress?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  /** 契约为列表；当前后端实现返回 dict（名称→相对路径），两者都兼容 */
  artifacts?: ArtifactEntry[] | Record<string, string>;
  structured_error?: StructuredError | null;
}

// ---------- 结果（result.json） ----------

export interface Pose {
  rank: number;
  affinity_kcal_mol: number;
  rmsd_lb: number;
  rmsd_ub: number;
  /** PDBQT pose 文件（job 目录相对路径），不直接用于 3Dmol 渲染 */
  pose_file: string;
  /** PDB pose 文件（若后端提供） */
  pose_pdb_file?: string | null;
}

export type LigandStatus = 'SUCCESS' | 'FAILED';

/** 描述符取值可能为数值、字符串或布尔（后端 additionalProperties 对象） */
export type DescriptorValue = number | string | boolean | null;

export interface LigandResult {
  ligand_id: string;
  status: LigandStatus;
  best_affinity_kcal_mol?: number | null;
  poses?: Pose[];
  ligand_efficiency?: number | null;
  descriptors?: Record<string, DescriptorValue>;
  preparation_warnings?: string[];
  warnings?: string[];
  structured_error?: StructuredError | null;
}

export interface DockingResultFile {
  job_id?: string;
  job_name?: string;
  status?: string;
  state?: JobState;
  /** 冻结契约字段名 */
  ligand_results?: LigandResult[];
  /** schemas/docking_output.schema.json 字段名（兼容） */
  results?: LigandResult[];
  docking_box?: Record<string, unknown>;
  docking_parameters?: Record<string, unknown>;
  warnings?: string[];
  started_at?: string;
  finished_at?: string | null;
  runtime_seconds?: number | null;
}

// ---------- 健康检查与版本 ----------

export interface HealthResponse {
  status: string;
  service?: string;
  version?: string;
}

export interface VersionResponse {
  skill_version?: string;
  api_version?: string;
  vina?: string;
  rdkit?: string;
  meeko?: string;
  python?: string;
}

// ---------- 多分子比较（ComparisonOutput） ----------

export interface ComparisonContext {
  receptor_sha256?: string | null;
  box_mode?: string | null;
  box_center?: number[] | null;
  box_size?: number[] | null;
  docking_parameters?: Record<string, unknown>;
  consistent?: boolean;
  notes?: string[];
}

/** 比较输出中的单个分子：原始值与归一化值（字段名以后端实现为准，此处宽松约束） */
export interface ComparisonMolecule {
  ligand_id: string;
  raw?: Record<string, number | null>;
  normalized?: Record<string, number | null>;
  score?: number | null;
  warnings?: string[];
}

export interface ComparisonOutput {
  job_id?: string;
  /** 提示词 8 契约字段 */
  comparison_context?: ComparisonContext;
  ranking_metric?: string;
  molecules?: ComparisonMolecule[];
  radar_dimensions?: string[];
  normalization_method?: string;
  scientific_warning?: string;
  /** schemas/comparison_output.schema.json 字段（兼容） */
  context?: ComparisonContext;
  ligand_ids?: string[];
  metrics?: Record<string, Record<string, number | string | null>>;
  disclaimer?: string;
  /** 当前后端实现额外字段：每个分子的雷达维度归一化值（0-1） */
  radar?: Record<string, Record<string, number | null>>;
}

// ---------- 前端表单 ----------

export interface InputFormState {
  jobName: string;
  ligandsText: string;
  receptorSource: string;
  boxMode: BoxMode;
  centerX: string;
  centerY: string;
  centerZ: string;
  sizeX: string;
  sizeY: string;
  sizeZ: string;
  referenceLigandResid: string;
  residueIds: string;
  padding: string;
  exhaustiveness: string;
  numModes: string;
  seed: string;
}

export const EXAMPLE_FORM: InputFormState = {
  jobName: 'example_benzene_ethanol',
  ligandsText: 'benzene\tc1ccccc1\nethanol\tCCO',
  receptorSource: 'examples/data/sample_receptor.pdb',
  boxMode: 'explicit',
  centerX: '18.3',
  centerY: '2.3',
  centerZ: '21.4',
  sizeX: '20',
  sizeY: '20',
  sizeZ: '20',
  referenceLigandResid: '',
  residueIds: '',
  padding: '8',
  exhaustiveness: '8',
  numModes: '9',
  seed: '42',
};

export const EMPTY_FORM: InputFormState = {
  jobName: '',
  ligandsText: '',
  receptorSource: 'examples/data/sample_receptor.pdb',
  boxMode: 'explicit',
  centerX: '',
  centerY: '',
  centerZ: '',
  sizeX: '20',
  sizeY: '20',
  sizeZ: '20',
  referenceLigandResid: '',
  residueIds: '',
  padding: '8',
  exhaustiveness: '8',
  numModes: '9',
  seed: '42',
};
