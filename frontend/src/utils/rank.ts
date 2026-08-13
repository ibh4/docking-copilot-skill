/** 批内相对 rank 计算：按 best affinity 升序（越负越好），失败分子不参与排名 */
import type { LigandResult } from '../types';

export function rankResults(results: LigandResult[]): Map<string, number> {
  const ranked = results
    .filter((r) => r.status === 'SUCCESS' && typeof r.best_affinity_kcal_mol === 'number')
    .sort((a, b) => (a.best_affinity_kcal_mol ?? 0) - (b.best_affinity_kcal_mol ?? 0));
  const map = new Map<string, number>();
  ranked.forEach((r, i) => {
    map.set(r.ligand_id, i + 1);
  });
  return map;
}
