/**
 * Viewer3D：3Dmol.js 单实例三维视图。
 * 三个标签：
 * - Ligand：ball-and-stick，读 ligands/<id>/ligand.pdb（回退 ligand.sdf）；
 * - Receptor：cartoon + docking box 线框，读 receptor/receptor.pdb；
 * - Docked Complex：蛋白 cartoon + pose sticks + box，支持 pose 切换并显示 affinity/rank。
 * 切换分子/pose 时先 clear 再加载；同一时刻只挂载一个 viewer。
 * PDBQT 不直接交给 3Dmol：若后端仅提供 receptor.pdbqt 则显示提示。
 */
import { useEffect, useRef, useState } from 'react';
import * as $3Dmol from '3dmol';
import { fetchJobFileText } from '../services/api';
import type { DockingBox, LigandResult, Pose } from '../types';

export interface Viewer3DProps {
  jobId: string | null;
  ligandResults: LigandResult[];
  selectedLigandId: string | null;
  box: DockingBox | null;
}

type ViewerTab = 'ligand' | 'receptor' | 'complex';

const TAB_LABELS: Record<ViewerTab, string> = {
  ligand: '配体',
  receptor: '受体',
  complex: '对接复合物',
};

function padPoseRank(rank: number): string {
  return rank.toString().padStart(3, '0');
}

/** pose PDB 路径：优先 pose_pdb_file，否则按契约路径 poses/<ligand_id>/pose_NNN.pdb 构造 */
function posePdbPath(ligandId: string, pose: Pose): string {
  if (pose.pose_pdb_file) {
    return pose.pose_pdb_file;
  }
  return `poses/${ligandId}/pose_${padPoseRank(pose.rank)}.pdb`;
}

/** 受体 PDB：兼容当前后端实现 receptor/receptor_clean.pdb 与契约 receptor/receptor.pdb */
async function fetchReceptorPdb(jobId: string): Promise<string> {
  try {
    return await fetchJobFileText(jobId, 'receptor/receptor_clean.pdb');
  } catch {
    return fetchJobFileText(jobId, 'receptor/receptor.pdb');
  }
}

function drawBoxWireframe(viewer: $3Dmol.GLViewer, box: DockingBox): void {
  const center = box.center;
  const size = box.size;
  if (!center || !size) {
    return;
  }
  const [cx, cy, cz] = center;
  const [sx, sy, sz] = size;
  if ([cx, cy, cz, sx, sy, sz].some((v) => typeof v !== 'number' || !Number.isFinite(v))) {
    return;
  }
  const hx = sx / 2;
  const hy = sy / 2;
  const hz = sz / 2;
  const corners: Array<{ x: number; y: number; z: number }> = [];
  for (const dx of [-hx, hx]) {
    for (const dy of [-hy, hy]) {
      for (const dz of [-hz, hz]) {
        corners.push({ x: cx + dx, y: cy + dy, z: cz + dz });
      }
    }
  }
  // 立方体 12 条边（corners 按 dx,dy,dz 二进制位索引）
  const edges: ReadonlyArray<readonly [number, number]> = [
    [0, 1], [0, 2], [0, 4], [1, 3], [1, 5], [2, 3],
    [2, 6], [3, 7], [4, 5], [4, 6], [5, 7], [6, 7],
  ];
  for (const [a, b] of edges) {
    viewer.addLine({ start: corners[a], end: corners[b], color: 'orange', linewidth: 2 });
  }
}

export default function Viewer3D({ jobId, ligandResults, selectedLigandId, box }: Viewer3DProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<$3Dmol.GLViewer | null>(null);
  const loadSeqRef = useRef(0);

  const [tab, setTab] = useState<ViewerTab>('ligand');
  const [poseIndex, setPoseIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedLigand = ligandResults.find((r) => r.ligand_id === selectedLigandId) ?? null;
  const poses = selectedLigand?.poses ?? [];
  const currentPose = poses[poseIndex] ?? poses[0] ?? null;

  // 切换分子时复位 pose 选择
  useEffect(() => {
    setPoseIndex(0);
  }, [selectedLigandId, jobId]);

  // 创建唯一 viewer 实例（卸载时释放容器内容）；
  // 容器尺寸变化（缩小后布局/窗口缩放）时调用 viewer.resize() 使画布跟随缩放
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const viewer = $3Dmol.createViewer(container, { backgroundColor: '#0d1117' });
    viewerRef.current = viewer;
    // 挂载后立即按容器当前尺寸（半宽/160px）同步画布，避免首次插入时尺寸不符
    viewer.resize();
    viewer.render();

    const ro = new ResizeObserver(() => {
      viewer.resize();
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      viewerRef.current = null;
      container.replaceChildren();
    };
  }, []);

  // 标签 / 分子 / pose 变化时：先清空再加载新内容
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) {
      return;
    }
    const seq = ++loadSeqRef.current;
    setError(null);

    if (!jobId || !selectedLigandId) {
      viewer.clear();
      viewer.render();
      return;
    }

    const stale = (): boolean => loadSeqRef.current !== seq;
    setLoading(true);

    const run = async (): Promise<void> => {
      viewer.clear();
      try {
        if (tab === 'ligand') {
          let data: string | null = null;
          let format = 'pdb';
          try {
            data = await fetchJobFileText(jobId, `ligands/${selectedLigandId}/ligand.pdb`);
          } catch {
            try {
              data = await fetchJobFileText(jobId, `ligands/${selectedLigandId}/ligand.sdf`);
              format = 'sdf';
            } catch {
              data = null;
            }
          }
          if (stale()) {
            return;
          }
          if (data === null) {
            throw new Error(`未找到配体可视化文件（ligands/${selectedLigandId}/ligand.pdb 或 ligand.sdf）`);
          }
          viewer.addModel(data, format);
          viewer.setStyle({}, { stick: { radius: 0.2 }, sphere: { scale: 0.25 } });
          viewer.zoomTo();
        } else if (tab === 'receptor') {
          let data: string;
          try {
            data = await fetchReceptorPdb(jobId);
          } catch {
            throw new Error('后端未提供清洗后的 receptor.pdb（若只有 receptor.pdbqt，按约定不直接交给 3Dmol 渲染）。');
          }
          if (stale()) {
            return;
          }
          viewer.addModel(data, 'pdb');
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
          if (box) {
            drawBoxWireframe(viewer, box);
          }
          viewer.zoomTo();
        } else {
          if (!selectedLigand || selectedLigand.status !== 'SUCCESS') {
            throw new Error('该分子未成功对接，无 pose 可显示。');
          }
          if (!currentPose) {
            throw new Error('该分子没有可用 pose。');
          }
          let receptorData: string;
          try {
            receptorData = await fetchReceptorPdb(jobId);
          } catch {
            throw new Error('后端未提供清洗后的 receptor.pdb（若只有 receptor.pdbqt，按约定不直接交给 3Dmol 渲染）。');
          }
          if (stale()) {
            return;
          }
          let poseData: string;
          try {
            poseData = await fetchJobFileText(jobId, posePdbPath(selectedLigandId, currentPose));
          } catch {
            throw new Error(`未找到 pose 文件：${posePdbPath(selectedLigandId, currentPose)}（PDBQT 不直接渲染）`);
          }
          if (stale()) {
            return;
          }
          const receptorModel = viewer.addModel(receptorData, 'pdb');
          receptorModel.setStyle({}, { cartoon: { color: '#8aa0b8', opacity: 0.9 } });
          const poseModel = viewer.addModel(poseData, 'pdb');
          poseModel.setStyle({}, { stick: { colorscheme: 'greenCarbon' } });
          if (box) {
            drawBoxWireframe(viewer, box);
          }
          viewer.zoomTo();
        }
        viewer.render();
      } catch (err) {
        if (!stale()) {
          setError(err instanceof Error ? err.message : String(err));
          viewer.render();
        }
      } finally {
        if (!stale()) {
          setLoading(false);
        }
      }
    };

    void run();
  }, [tab, jobId, selectedLigandId, selectedLigand, currentPose, box]);

  return (
    <section className="panel viewer3d">
      <div className="viewer3d__tabs">
        {(Object.keys(TAB_LABELS) as ViewerTab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`tab${tab === t ? ' tab--active' : ''}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
        {loading && <span className="viewer3d__loading">加载中…</span>}
      </div>

      <div className="viewer3d__toolbar">
        {tab === 'ligand' && selectedLigand && (
          <span>
            {selectedLigand.ligand_id}
            {selectedLigand.best_affinity_kcal_mol !== null && selectedLigand.best_affinity_kcal_mol !== undefined
              ? ` · 最优亲和力 ${selectedLigand.best_affinity_kcal_mol.toFixed(2)} kcal/mol`
              : ''}
          </span>
        )}
        {tab === 'complex' && poses.length > 0 && (
          <>
            <label className="viewer3d__pose-select">
              <span>构象（Pose）</span>
              <select
                value={poseIndex}
                onChange={(e) => setPoseIndex(Number(e.target.value))}
              >
                {poses.map((p, i) => (
                  <option key={p.rank} value={i}>
                    排名 {p.rank} · {p.affinity_kcal_mol.toFixed(2)} kcal/mol
                  </option>
                ))}
              </select>
            </label>
            {currentPose && (
              <span className="viewer3d__pose-info">
                当前：排名 {currentPose.rank} · affinity {currentPose.affinity_kcal_mol.toFixed(2)} kcal/mol ·
                rmsd [{currentPose.rmsd_lb.toFixed(2)}, {currentPose.rmsd_ub.toFixed(2)}]
              </span>
            )}
          </>
        )}
      </div>

      <div ref={containerRef} className="viewer3d__canvas" />

      {error && <p className="error-text viewer3d__error">{error}</p>}
      {!jobId && <p className="muted">尚无任务：提交对接后可在此查看配体 / 受体 / 对接复合物。</p>}
    </section>
  );
}
