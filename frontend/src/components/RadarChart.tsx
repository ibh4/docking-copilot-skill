/**
 * RadarChart：ECharts 雷达图「Relative Docking & Developability Profile」。
 * - ≤4 分子叠加（多选），失败分子不参与；
 * - tooltip 同时显示原始值与归一化值；
 * - 优先使用 /api/comparison 返回（molecules/radar_dimensions），字段不可用时
 *   回退到本地批内归一化（utils/radar.ts）；
 * - 附 scientific_warning、归一化方法与阈值文本 + 归一化数值表 + CSV/JSON 下载。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import * as echarts from 'echarts';
import type { ComparisonOutput, LigandResult } from '../types';
import { buildLocalComparison, FIT_BANDS, type RadarSeriesEntry } from '../utils/radar';

export interface RadarChartProps {
  results: LigandResult[];
  comparison: ComparisonOutput | null;
  selectedLigandId: string | null;
}

const MAX_OVERLAY = 4;

/** 雷达维度 → 中文显示名（未收录的维度保持原样，兼容后端自定义命名） */
const DIM_ZH: Record<string, string> = {
  'Relative Affinity': '相对亲和力',
  'Ligand Efficiency': '配体效率',
  'Pose Separation': 'Pose 区分度',
  'Molecular Size Fit': '分子大小适配',
  'LogP Fit': 'LogP 适配',
  'TPSA Fit': 'TPSA 适配',
  'Flexibility Fit': '柔性适配',
  'Preparation Quality': '准备质量',
  affinity: '亲和力',
  relative_affinity: '相对亲和力',
  ligand_efficiency: '配体效率',
  pose_consistency: 'Pose 一致性',
  pose_separation: 'Pose 区分度',
  drug_likeness: '类药性',
  preparation_quality: '准备质量',
};

function dimLabel(dim: string): string {
  return DIM_ZH[dim] ?? dim;
}

/**
 * 后端 /api/comparison 返回的英文归一化方法说明 → 中文。
 * 公式字段名（relative_affinity 等）按约定保留英文，语义与后端原文逐句对应；
 * 仅在完全匹配时替换，未知文案原样展示不臆改。
 */
const NORMALIZATION_METHOD_ZH =
  '相对对接画像（Relative Docking Profile，仅展示用途、限同一批次内）：' +
  'relative_affinity = (worst_affinity - affinity) / (worst_affinity - best_affinity)，取值 [0,1]，越高越有利' +
  '（affinity 单位 kcal/mol，越负越好）；' +
  'ligand_efficiency = -best_affinity / heavy_atom_count（kcal/mol/重原子，仅作辅助指标）；' +
  'pose_score_gap = pose2.affinity - pose1.affinity（kcal/mol；≥1.0 时 pose_consistency 记 1.0，线性降至 0.0 处为 0）；' +
  'molwt_fit：MolWt≤500 记 1.0，线性降至 600 (g/mol) 处为 0；' +
  'logp_fit：LogP 在 [-1,5] 内记 1.0，向 -3/7 线性降至 0；' +
  'tpsa_fit：TPSA≤140 记 1.0，线性降至 180 (Å²) 处为 0；' +
  'flexibility_fit：可旋转键≤7 记 1.0，线性降至 12 处为 0；' +
  'preparation_quality = max(0, 1 - 0.1 × 准备警告数)；' +
  'composite_display_score = 0.4×relative_affinity + 0.2×pose_consistency + 0.2×ligand_efficiency_rank_norm + ' +
  '0.2×preparation_quality，仅在批内 ≥2 个成功分子时计算。';

/** 后端科学警告 → 中文（经验打分、仅展示、批内可比、非自由能/结合概率、不可换算 Kd/IC50） */
const SCIENTIFIC_WARNING_ZH =
  '相对对接打分为经验打分，仅限同一批次内计算的展示性估计值；' +
  '只有同一受体、同一 box、同一 Vina 参数下才可比；' +
  '它们不是绝对结合自由能、结合概率，不能换算为 Kd/Ki/IC50，也不是任何实验或药效指标。';

/** 后端固定英文文案 → 中文译文（完全匹配才替换） */
const BACKEND_TEXT_ZH: Record<string, string> = {
  'Relative Docking Profile (display-only, in-batch): relative_affinity = (worst_affinity - affinity) / (worst_affinity - best_affinity) in [0,1], higher = more favorable (affinity in kcal/mol, more negative is better); ligand_efficiency = -best_affinity / heavy_atom_count (kcal/mol per heavy atom, auxiliary only); pose_score_gap = pose2.affinity - pose1.affinity (kcal/mol; >=1.0 gives pose_consistency 1.0, linearly down to 0 at 0.0); molwt_fit = 1.0 if MolWt<=500, linearly to 0 at 600 (g/mol); logp_fit = 1.0 within [-1,5], linearly to 0 at -3/7; tpsa_fit = 1.0 if TPSA<=140, linearly to 0 at 180 (A^2); flexibility_fit = 1.0 if rotatable_bonds<=7, linearly to 0 at 12; preparation_quality = max(0, 1 - 0.1 * num_preparation_warnings); composite_display_score = 0.4*relative_affinity + 0.2*pose_consistency + 0.2*ligand_efficiency_rank_norm + 0.2*preparation_quality, only computed for batches with >=2 successful ligands.':
    NORMALIZATION_METHOD_ZH,
  'Relative docking scores are empirical, display-only estimates computed within one batch; they are comparable only for the same receptor, box and Vina parameters, and are not absolute binding free energies, binding probabilities or any experimental/effect measure.':
    SCIENTIFIC_WARNING_ZH,
};

function translateBackendText(text: string): string {
  return BACKEND_TEXT_ZH[text.trim()] ?? text;
}

interface RadarModel {
  dimensions: string[];
  entries: RadarSeriesEntry[];
  normalizationMethod: string;
  warning: string;
  source: 'backend' | 'local';
}

/** 雷达维度 → metrics 中原始值字段的候选名（兼容后端不同命名） */
const DIM_RAW_ALIASES: Record<string, string[]> = {
  affinity: ['best_affinity_kcal_mol', 'affinity'],
  relative_affinity: ['relative_affinity', 'best_affinity_kcal_mol'],
  ligand_efficiency: ['ligand_efficiency'],
  pose_consistency: ['pose_score_gap_kcal_mol', 'pose_consistency'],
  pose_separation: ['pose_score_gap_kcal_mol', 'pose_consistency'],
  drug_likeness: ['drug_likeness'],
  preparation_quality: ['preparation_quality'],
};

function lookupRaw(
  metrics: Record<string, number | string | null> | undefined,
  dim: string,
): number | null {
  if (!metrics) {
    return null;
  }
  const keys = DIM_RAW_ALIASES[dim] ?? [dim];
  for (const key of keys) {
    const v = metrics[key];
    if (typeof v === 'number' && Number.isFinite(v)) {
      return v;
    }
  }
  return null;
}

/** 从后端比较输出提取雷达数据；字段不可用（全空）时返回 null 触发本地回退 */
function extractBackendModel(comparison: ComparisonOutput): RadarModel | null {
  const dimensions = comparison.radar_dimensions;
  if (!dimensions || dimensions.length === 0) {
    return null;
  }
  const warning = translateBackendText(
    comparison.scientific_warning ??
      comparison.disclaimer ??
      '相对指标仅适用于同一受体、同一 box、同一参数的同一批次。',
  );
  const normalizationMethod = translateBackendText(
    comparison.normalization_method ?? '后端提供（normalization_method 缺失）',
  );

  // 形态 1（当前后端实现）：radar = {ligand_id: {dim: 归一化值 0-1}}，原始值在 metrics
  if (comparison.radar && Object.keys(comparison.radar).length > 0) {
    const entries: RadarSeriesEntry[] = Object.entries(comparison.radar).map(([ligandId, values]) => ({
      ligandId,
      raw: dimensions.map((dim) => lookupRaw(comparison.metrics?.[ligandId], dim)),
      normalized: dimensions.map((dim) => {
        const v = values[dim];
        return typeof v === 'number' && Number.isFinite(v) ? Math.round(v * 1000) / 10 : null;
      }),
      notes: [],
    }));
    return { dimensions, entries, normalizationMethod, warning, source: 'backend' };
  }

  // 形态 2（提示词 8 契约）：molecules 列表
  const molecules = comparison.molecules;
  if (molecules && molecules.length > 0) {
    const entries: RadarSeriesEntry[] = molecules.map((mol) => {
      const rawArr = dimensions.map((dim) => {
        const v = mol.raw?.[dim];
        return typeof v === 'number' ? v : null;
      });
      const normArr = dimensions.map((dim) => {
        const v = mol.normalized?.[dim];
        return typeof v === 'number' ? v : null;
      });
      return { ligandId: mol.ligand_id, raw: rawArr, normalized: normArr, notes: [] };
    });
    if (entries.every((e) => e.normalized.every((v) => v === null))) {
      return null;
    }
    return { dimensions, entries, normalizationMethod, warning, source: 'backend' };
  }

  return null;
}

function formatNum(value: number | null, digits = 2): string {
  return value === null ? '不可用' : value.toFixed(digits);
}

function buildCsv(model: RadarModel): string {
  const header = ['ligand_id', ...model.dimensions.map((d) => `${d}(raw)`), ...model.dimensions.map((d) => `${d}(normalized)`)];
  const rows = model.entries.map((e) => [
    e.ligandId,
    ...e.raw.map((v) => (v === null ? '' : String(v))),
    ...e.normalized.map((v) => (v === null ? '' : String(v))),
  ]);
  return [header, ...rows].map((r) => r.map((c) => `"${c.replaceAll('"', '""')}"`).join(',')).join('\n');
}

function downloadText(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function RadarChart({ results, comparison, selectedLigandId }: RadarChartProps): JSX.Element {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  const [checked, setChecked] = useState<string[]>([]);

  const model = useMemo<RadarModel | null>(() => {
    if (results.length === 0) {
      return null;
    }
    if (comparison) {
      const backend = extractBackendModel(comparison);
      if (backend) {
        return backend;
      }
    }
    const local = buildLocalComparison(results);
    return {
      dimensions: [...local.dimensions],
      entries: local.series,
      normalizationMethod: local.normalizationMethod,
      warning: local.scientificWarning,
      source: 'local',
    };
  }, [results, comparison]);

  // 默认勾选前 4 个成功分子；结果集变化时重置
  useEffect(() => {
    if (!model) {
      setChecked([]);
      return;
    }
    const defaults = model.entries.slice(0, MAX_OVERLAY).map((e) => e.ligandId);
    setChecked(defaults);
  }, [model]);

  const toggle = (ligandId: string): void => {
    setChecked((prev) => {
      if (prev.includes(ligandId)) {
        return prev.filter((id) => id !== ligandId);
      }
      if (prev.length >= MAX_OVERLAY) {
        return prev;
      }
      return [...prev, ligandId];
    });
  };

  // 初始化与销毁 ECharts 实例。
  // 依赖 [model]：model 为 null 时渲染占位分支（无 chartRef 容器），
  // 任务成功后容器才出现，必须重跑 effect 完成惰性初始化，否则图表永不渲染。
  useEffect(() => {
    const container = chartRef.current;
    if (!container || !model) {
      return;
    }
    const chart = echarts.init(container);
    chartInstanceRef.current = chart;
    const onResize = (): void => chart.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chart.dispose();
      chartInstanceRef.current = null;
    };
  }, [model]);

  // 数据变化时刷新图表（chart 实例由上方 effect 惰性初始化，未就绪时跳过）
  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart) {
      return;
    }
    if (!model) {
      chart.clear();
      return;
    }
    const lookup = new Map(model.entries.map((e) => [e.ligandId, e]));
    const checkedEntries = model.entries.filter((e) => checked.includes(e.ligandId));
    // 当前勾选分子全部缺失的维度，轴标签显示 "—"（不可用，非 0 分）
    const unavailable = model.dimensions.map((_, i) =>
      checkedEntries.every((e) => e.normalized[i] === null),
    );
    const option: echarts.EChartsOption = {
      backgroundColor: 'transparent',
      title: {
        // 标题按项目约定保留英文原名（SKILL.md §12），附中文副标题
        text: 'Relative Docking & Developability Profile',
        subtext: '相对对接与可成药性画像',
        left: 'center',
        textStyle: { fontSize: 13, color: '#c9d4e3' },
        subtextStyle: { fontSize: 11, color: '#8494ab' },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: unknown): string => {
          if (typeof params !== 'object' || params === null) {
            return '';
          }
          const p = params as { name?: unknown; value?: unknown };
          const name = typeof p.name === 'string' ? p.name : '';
          const entry = lookup.get(name);
          if (!entry) {
            return name;
          }
          const values = Array.isArray(p.value) ? p.value : [];
          const lines = model.dimensions.map((dim, i) => {
            const norm = values[i];
            const normText = typeof norm === 'number' ? norm.toFixed(1) : '不可用';
            const rawText = typeof norm === 'number' ? formatNum(entry.raw[i] ?? null) : '不可用';
            return `${dimLabel(dim)}：归一化 ${normText} / 原始 ${rawText}`;
          });
          const notes = entry.notes.length > 0 ? [`备注：${entry.notes.join('；')}`] : [];
          return [name, ...lines, ...notes].join('<br/>');
        },
      },
      legend: {
        bottom: 0,
        textStyle: { color: '#c9d4e3' },
      },
      radar: {
        indicator: model.dimensions.map((dim, i) => ({
          name: unavailable[i] ? `${dimLabel(dim)}（—）` : dimLabel(dim),
          max: 100,
          min: 0,
        })),
        radius: '60%',
        axisName: { color: '#9fb0c6', fontSize: 10 },
        splitArea: { areaStyle: { color: ['rgba(120,140,170,0.06)', 'rgba(120,140,170,0.12)'] } },
      },
      series: [
        {
          type: 'radar',
          emphasis: { lineStyle: { width: 3 } },
          data: model.entries
            .filter((e) => checked.includes(e.ligandId))
            .map((e) => ({
              name: e.ligandId,
              // null 维度跳过（undefined 顶点），不绘为 0
              value: e.normalized.map((v) => v ?? undefined),
              symbol: selectedLigandId === e.ligandId ? 'circle' : 'none',
            })),
        },
      ],
    };
    chart.setOption(option, true);
  }, [model, checked, selectedLigandId]);

  if (!model) {
    return (
      <section className="panel radar-chart">
        <h2>多分子比较</h2>
        <p className="muted">
          任务成功且至少 1 个分子对接成功后，展示雷达图（Relative Docking &amp; Developability Profile，相对对接与可成药性画像）。
        </p>
      </section>
    );
  }

  return (
    <section className="panel radar-chart">
      <h2>多分子比较</h2>
      <div className="radar-chart__select">
        <span>叠加（≤{MAX_OVERLAY}）：</span>
        {model.entries.map((e) => (
          <label key={e.ligandId} className={`radar-check${selectedLigandId === e.ligandId ? ' radar-check--current' : ''}`}>
            <input
              type="checkbox"
              checked={checked.includes(e.ligandId)}
              disabled={!checked.includes(e.ligandId) && checked.length >= MAX_OVERLAY}
              onChange={() => toggle(e.ligandId)}
            />
            {e.ligandId}
          </label>
        ))}
      </div>

      <div ref={chartRef} className="radar-chart__canvas" />
      <p className="radar-chart__null-note">
        图中不可用维度以“—”标示并跳过对应顶点；“—”表示指标不可用（数据缺失），与得分为 0 不同。
      </p>

      <table className="data-table radar-chart__table">
        <caption>归一化数值（0-100，同时保留原始值于 tooltip/CSV）</caption>
        <thead>
          <tr>
            <th>分子</th>
            {model.dimensions.map((dim) => (
              <th key={dim} title={dim}>{dimLabel(dim)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {model.entries.map((e) => (
            <tr key={e.ligandId}>
              <td>{e.ligandId}</td>
              {e.normalized.map((v, i) => (
                <td key={model.dimensions[i] ?? i} title={`原始值：${formatNum(e.raw[i] ?? null)}`}>
                  {v === null ? '—' : v.toFixed(1)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="radar-chart__fit-bands">
        <span>目标区间阈值（Fit 维度）：</span>
        <ul>
          {FIT_BANDS.map((band) => (
            <li key={band.dimension}>
              {dimLabel(band.dimension)}：[{band.ideal[0]}, {band.ideal[1]}] {band.unit}，容差 ±{band.tolerance}
            </li>
          ))}
        </ul>
      </div>

      <p className="radar-chart__method">归一化方法：{model.normalizationMethod}</p>
      <p className="radar-chart__warning">⚠ {model.warning}</p>

      <div className="radar-chart__downloads">
        <span>导出：</span>
        <button
          type="button"
          className="btn btn--small"
          onClick={() => downloadText('comparison_radar.csv', buildCsv(model), 'text/csv')}
        >
          CSV
        </button>
        <button
          type="button"
          className="btn btn--small"
          onClick={() => downloadText('comparison_radar.json', JSON.stringify(model, null, 2), 'application/json')}
        >
          JSON
        </button>
        <span className="muted">数据源：{model.source === 'backend' ? '/api/comparison' : '本地批内归一化（后端比较不可用）'}</span>
      </div>
    </section>
  );
}
