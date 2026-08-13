/**
 * MoleculeList：左侧候选分子列表。
 * 2D SVG 缩略图（files 端点）+ best affinity + 批内 rank + status + warnings；
 * 点击切换 Viewer3D 与结果表格。失败分子保留失败原因，不参与排名。
 */
import { jobFileUrl } from '../services/api';
import type { LigandResult } from '../types';
import { rankResults } from '../utils/rank';

export interface MoleculeListProps {
  jobId: string | null;
  results: LigandResult[];
  selectedLigandId: string | null;
  onSelect: (ligandId: string) => void;
}

export default function MoleculeList({ jobId, results, selectedLigandId, onSelect }: MoleculeListProps): JSX.Element {
  const ranks = rankResults(results);

  if (results.length === 0) {
    return (
      <section className="panel molecule-list">
        <h2>候选分子</h2>
        <p className="muted">任务成功后在此展示候选列表。</p>
      </section>
    );
  }

  return (
    <section className="panel molecule-list">
      <h2>候选分子（{results.length}）</h2>
      <ul>
        {results.map((r) => {
          const warningCount = (r.warnings?.length ?? 0) + (r.preparation_warnings?.length ?? 0);
          const rank = ranks.get(r.ligand_id);
          return (
            <li key={r.ligand_id}>
              <button
                type="button"
                className={`mol-card${selectedLigandId === r.ligand_id ? ' mol-card--selected' : ''}`}
                onClick={() => onSelect(r.ligand_id)}
              >
                {jobId && (
                  <img
                    className="mol-card__thumb"
                    src={jobFileUrl(jobId, `ligands/${r.ligand_id}/ligand_2d.svg`)}
                    alt={`${r.ligand_id} 2D 结构`}
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                    }}
                  />
                )}
                <div className="mol-card__body">
                  <span className="mol-card__name">{r.ligand_id}</span>
                  <span className="mol-card__meta">
                    {r.status === 'SUCCESS' ? (
                      <>
                        亲和力 {typeof r.best_affinity_kcal_mol === 'number' ? r.best_affinity_kcal_mol.toFixed(2) : '—'} kcal/mol
                        {rank !== undefined ? ` · 批内排名 ${rank}` : ''}
                      </>
                    ) : (
                      <>FAILED{r.structured_error ? `：${r.structured_error.message}` : ''}</>
                    )}
                  </span>
                  <span className="mol-card__meta">
                    状态：{r.status}
                    {warningCount > 0 ? ` · ${warningCount} 条警告` : ''}
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
