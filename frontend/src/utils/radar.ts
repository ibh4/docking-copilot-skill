/**
 * 雷达图本地兜底计算（提示词 8 归一化原则）。
 * 当 /api/comparison 不可用或字段缺失时，用 result.json 中的原始指标
 * 在批次内做透明归一化；所有维度同时提供原始值与归一化值。
 *
 * 归一化说明（同时展示于页面 normalization_method 文本）：
 * - Relative Affinity：批内 min-max（-affinity，越负越好 → 分数越高）；
 * - Ligand Efficiency：批内 min-max（LE = -best_affinity / heavy_atom_count，仅辅助指标）；
 * - Pose Separation：|pose2 - pose1| 分差越大 → 越好，批内 min-max；缺少第二 pose 记 0 并在 warnings 说明；
 * - Molecular Size Fit / LogP Fit / TPSA Fit / Flexibility Fit：目标区间映射
 *   （区间内 100，区间外按距离线性衰减至 0），阈值见 FIT_BANDS；
 * - Preparation Quality：100 - 25 * (warnings + preparation_warnings 数量)，截断到 0-100。
 * 注意：这些是展示性相对指标，不是绝对结合概率、实验自由能或药效。
 */
import type { DescriptorValue, LigandResult } from '../types';

export const RADAR_DIMENSIONS = [
  'Relative Affinity',
  'Ligand Efficiency',
  'Pose Separation',
  'Molecular Size Fit',
  'LogP Fit',
  'TPSA Fit',
  'Flexibility Fit',
  'Preparation Quality',
] as const;

export type RadarDimension = (typeof RADAR_DIMENSIONS)[number];

export interface RadarSeriesEntry {
  ligandId: string;
  /** 与 RADAR_DIMENSIONS 一一对应的原始值（null = 不可用） */
  raw: (number | null)[];
  /** 与 RADAR_DIMENSIONS 一一对应的归一化值 0-100 */
  normalized: (number | null)[];
  notes: string[];
}

export interface LocalComparison {
  dimensions: RadarDimension[];
  series: RadarSeriesEntry[];
  normalizationMethod: string;
  scientificWarning: string;
}

/** 目标区间（可配置阈值，页面同时展示） */
export const FIT_BANDS: ReadonlyArray<{
  dimension: RadarDimension;
  unit: string;
  ideal: [number, number];
  tolerance: number;
}> = [
  { dimension: 'Molecular Size Fit', unit: 'Da', ideal: [150, 500], tolerance: 150 },
  { dimension: 'LogP Fit', unit: 'logP', ideal: [-1, 5], tolerance: 3 },
  { dimension: 'TPSA Fit', unit: 'Å²', ideal: [20, 140], tolerance: 60 },
  { dimension: 'Flexibility Fit', unit: '可旋转键数', ideal: [0, 10], tolerance: 6 },
];

export const LOCAL_NORMALIZATION_METHOD =
  '批内稳健归一化：affinity/LE/pose gap 取批内 min-max（affinity 取负值方向，越负越好）；' +
  'MolWt/LogP/TPSA/rotatable bonds 用目标区间映射（区间内 100，区间外线性衰减）；' +
  'Preparation Quality 按 warning 数量扣分（每条 -25，下限 0）。';

export const LOCAL_SCIENTIFIC_WARNING =
  '雷达图仅表示同一受体、同一 docking box、同一 Vina 参数、同一批次内的相对画像，' +
  '不是绝对结合概率、实验自由能或药效预测。缺失指标以“—”标示（不可用，与得分为 0 不同），并在 tooltip 中标注。';

function getNumber(descriptors: Record<string, DescriptorValue> | undefined, keys: string[]): number | null {
  if (!descriptors) {
    return null;
  }
  for (const key of keys) {
    const value = descriptors[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function minMaxNormalize(values: (number | null)[], invert: boolean): (number | null)[] {
  const finite = values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (finite.length === 0) {
    return values.map(() => null);
  }
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  return values.map((v) => {
    if (v === null || !Number.isFinite(v)) {
      return null;
    }
    if (max === min) {
      return 50;
    }
    const t = (v - min) / (max - min);
    const oriented = invert ? 1 - t : t;
    return Math.round(oriented * 1000) / 10;
  });
}

function fitScore(value: number | null, ideal: [number, number], tolerance: number): number | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }
  const [lo, hi] = ideal;
  if (value >= lo && value <= hi) {
    return 100;
  }
  const distance = value < lo ? lo - value : value - hi;
  return Math.round(Math.max(0, 100 - (distance / tolerance) * 100) * 10) / 10;
}

/** 由成功分子结果构建本地比较数据（失败分子不参与，避免虚假排名） */
export function buildLocalComparison(results: LigandResult[]): LocalComparison {
  const ok = results.filter((r) => r.status === 'SUCCESS');

  const affinities = ok.map((r) => r.best_affinity_kcal_mol ?? null);
  const les = ok.map((r) => r.ligand_efficiency ?? null);
  const gaps = ok.map((r) => {
    const poses = r.poses ?? [];
    const first = poses[0];
    const second = poses[1];
    if (first && second) {
      return Math.abs(second.affinity_kcal_mol - first.affinity_kcal_mol);
    }
    return null;
  });

  const affNorm = minMaxNormalize(affinities, true);
  const leNorm = minMaxNormalize(les, false);
  const gapNorm = minMaxNormalize(gaps, false);

  const bandOf = (dim: RadarDimension) => FIT_BANDS.find((b) => b.dimension === dim);

  const series: RadarSeriesEntry[] = ok.map((r, i) => {
    const d = r.descriptors;
    const molWt = getNumber(d, ['MolWt', 'mol_wt', 'mw']);
    const logP = getNumber(d, ['LogP', 'log_p', 'logp']);
    const tpsa = getNumber(d, ['TPSA', 'tpsa']);
    const rotBonds = getNumber(d, ['RotatableBonds', 'rotatable_bonds', 'NumRotatableBonds']);

    const sizeBand = bandOf('Molecular Size Fit');
    const logpBand = bandOf('LogP Fit');
    const tpsaBand = bandOf('TPSA Fit');
    const flexBand = bandOf('Flexibility Fit');

    const sizeRaw = molWt;
    const logpRaw = logP;
    const tpsaRaw = tpsa;
    const flexRaw = rotBonds;

    const warningCount = (r.warnings?.length ?? 0) + (r.preparation_warnings?.length ?? 0);
    const prepQuality = Math.max(0, 100 - 25 * warningCount);

    const notes: string[] = [];
    if (gaps[i] === null) {
      notes.push('缺少第二 pose，Pose Separation 不可用');
    }

    return {
      ligandId: r.ligand_id,
      raw: [affinities[i] ?? null, les[i] ?? null, gaps[i] ?? null, sizeRaw, logpRaw, tpsaRaw, flexRaw, warningCount],
      normalized: [
        affNorm[i] ?? null,
        leNorm[i] ?? null,
        gapNorm[i] ?? null,
        sizeBand ? fitScore(sizeRaw, sizeBand.ideal, sizeBand.tolerance) : null,
        logpBand ? fitScore(logpRaw, logpBand.ideal, logpBand.tolerance) : null,
        tpsaBand ? fitScore(tpsaRaw, tpsaBand.ideal, tpsaBand.tolerance) : null,
        flexBand ? fitScore(flexRaw, flexBand.ideal, flexBand.tolerance) : null,
        prepQuality,
      ],
      notes,
    };
  });

  return {
    dimensions: [...RADAR_DIMENSIONS],
    series,
    normalizationMethod: LOCAL_NORMALIZATION_METHOD,
    scientificWarning: LOCAL_SCIENTIFIC_WARNING,
  };
}
