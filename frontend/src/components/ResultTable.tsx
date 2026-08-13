/**
 * ResultTable：结果区。
 * top poses 表、分子描述符、参数摘要、warnings、科学解释与局限性、下载链接
 * （JSON 走 result 端点；MD/CSV/bundle.zip 走 files 端点）。
 * 所有关键数据同时以表格/文本呈现，不依赖图形。
 */
import { jobFileUrl, jobResultUrl } from '../services/api';
import type { DescriptorValue, DockingInput, DockingResultFile, LigandResult } from '../types';

export interface ResultTableProps {
  jobId: string | null;
  result: DockingResultFile | null;
  selectedLigand: LigandResult | null;
  submittedInput: DockingInput | null;
}

function formatValue(value: DescriptorValue): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  return String(value);
}

const INTERPRETATION =
  '科学解释：Vina affinity 是经验打分函数的估计值（单位 kcal/mol，仅作相对排序参考），越负通常表示预测的结合越强，' +
  '但它不是结合自由能，也不能换算为 Kd/IC50 或药效；' +
  'ligand efficiency（LE = -affinity / 重原子数）仅用于粗略比较不同大小分子的效率。' +
  'pose 的 rmsd_lb/rmsd_ub 是 Vina 相对最优 pose 的估计偏差，不代表对实验构象的 RMSD。';

const LIMITATIONS =
  '局限性：本结果未包含受体柔性、溶剂化与熵效应的严格处理；打分函数存在系统性偏差，' +
  '不能区分活性/非活性，更不能替代实验。affinity 只适合在同一受体、同一 box、同一参数的批次内做相对排序。';

export default function ResultTable({ jobId, result, selectedLigand, submittedInput }: ResultTableProps): JSX.Element {
  if (!jobId || !result) {
    return (
      <section className="panel result-table">
        <h2>结果</h2>
        <p className="muted">任务成功完成后在此展示结果表。</p>
      </section>
    );
  }

  const poses = selectedLigand?.poses ?? [];
  const descriptors = selectedLigand?.descriptors ?? {};
  const warnings = [...(selectedLigand?.warnings ?? []), ...(selectedLigand?.preparation_warnings ?? [])];
  const boxParams = submittedInput?.docking_box;
  const vinaParams = submittedInput?.docking_parameters;

  return (
    <section className="panel result-table">
      <h2>结果{selectedLigand ? `：${selectedLigand.ligand_id}` : ''}</h2>

      {selectedLigand && (
        <>
          <div className="result-table__summary">
            <span>最优亲和力：{selectedLigand.best_affinity_kcal_mol?.toFixed(2) ?? '—'} kcal/mol</span>
            <span>配体效率（LE）：{selectedLigand.ligand_efficiency?.toFixed(3) ?? '—'}</span>
            <span>pose 数量：{poses.length}</span>
            <span>状态：{selectedLigand.status}</span>
          </div>

          {poses.length > 0 && (
            <table className="data-table">
              <caption>对接构象（Top poses）</caption>
              <thead>
                <tr>
                  <th>排名（rank）</th>
                  <th>affinity (kcal/mol)</th>
                  <th>rmsd_lb (Å)</th>
                  <th>rmsd_ub (Å)</th>
                  <th>pose 文件</th>
                </tr>
              </thead>
              <tbody>
                {poses.map((p) => (
                  <tr key={p.rank}>
                    <td>{p.rank}</td>
                    <td>{p.affinity_kcal_mol.toFixed(2)}</td>
                    <td>{p.rmsd_lb.toFixed(2)}</td>
                    <td>{p.rmsd_ub.toFixed(2)}</td>
                    <td className="cell-mono">{p.pose_pdb_file ?? p.pose_file}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {Object.keys(descriptors).length > 0 && (
            <table className="data-table descriptors-table">
              <caption>分子描述符</caption>
              <thead>
                <tr>
                  <th>描述符</th>
                  <th>值</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(descriptors).map(([key, value]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{formatValue(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <table className="data-table">
        <caption>参数摘要</caption>
        <tbody>
          <tr>
            <td>受体（receptor）</td>
            <td className="cell-mono">{submittedInput?.receptor.source ?? '—'}</td>
          </tr>
          <tr>
            <td>对接盒（docking box）</td>
            <td>
              {boxParams?.center && boxParams?.size
                ? `mode=${boxParams.mode ?? 'explicit'} center=[${boxParams.center.join(', ')}] size=[${boxParams.size.join(', ')}] Å`
                : `mode=${boxParams?.mode ?? '—'}`}
            </td>
          </tr>
          <tr>
            <td>Vina 参数</td>
            <td>
              {vinaParams
                ? `exhaustiveness=${vinaParams.exhaustiveness ?? 8} num_modes=${vinaParams.num_modes ?? 9} seed=${vinaParams.seed ?? 42} energy_range=${vinaParams.energy_range ?? 3.0} cpu=${vinaParams.cpu ?? 4}`
                : '—'}
            </td>
          </tr>
          <tr>
            <td>运行时间</td>
            <td>
              {result.started_at ?? '—'} → {result.finished_at ?? '—'}
              {typeof result.runtime_seconds === 'number' ? `（${result.runtime_seconds.toFixed(1)} s）` : ''}
            </td>
          </tr>
        </tbody>
      </table>

      {warnings.length > 0 && (
        <div className="result-table__warnings">
          <span>警告：</span>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {result.warnings && result.warnings.length > 0 && (
        <div className="result-table__warnings">
          <span>任务级警告：</span>
          <ul>
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="result-table__science">
        <p>{INTERPRETATION}</p>
        <p>{LIMITATIONS}</p>
      </div>

      <div className="result-table__downloads">
        <span>下载：</span>
        <a href={jobResultUrl(jobId)} download="result.json">result.json</a>
        <a href={jobFileUrl(jobId, 'reports/result.md')} download="result.md">result.md</a>
        <a href={jobFileUrl(jobId, 'reports/comparison.csv')} download="comparison.csv">comparison.csv</a>
        <a href={jobFileUrl(jobId, 'bundle.zip')} download="bundle.zip">bundle.zip</a>
      </div>
    </section>
  );
}
