/**
 * IntroPage：项目介绍页（导航「项目介绍」入口）。
 * 内容提炼自 SKILL.md 与 README.md：项目简介、功能特性、工作流概览（12 态）、
 * 科学边界、快速开始命令、数据来源与自主性声明。
 * 配图：内联 SVG 管线流程图 + 靶点 3D 图与 Demo 截图（public/ 静态资源，均附中文图注）。
 * 纯展示组件，无外部依赖；文案如实不夸大科学结论。
 */

const FEATURES: readonly { emoji: string; title: string; desc: string }[] = [
  { emoji: '🧪', title: '配体准备', desc: 'SMILES 解析与校验（RDKit）、ETKDGv3 三维构象构建、MMFF94/UFF 力场优化（受控回退并留痕）、Meeko PDBQT 准备，每分子最多 10 个候选构象取力场能量最低者。' },
  { emoji: '🧫', title: '受体准备', desc: '受体 PDB 分析（Biopython）与按策略清洗：链/水/辅因子/金属/共晶配体可配置；Meeko 严格模式失败时受控回退 --allow_bad_res 并记录任务级警告。' },
  { emoji: '📦', title: '搜索盒校验', desc: '四种 box 模式（explicit / reference_ligand / residue_list / whole_receptor）；硬约束：单边 10–30 Å、体积 ≤ 27000 Å³、必须与受体包围盒相交；参考配体缺失不静默生成盒，直接报 INVALID_BOX。' },
  { emoji: '⚓', title: 'AutoDock Vina 对接', desc: 'Python API 子进程优先、CLI 受控回退的双适配器；固定 seed（默认 42）保证可复现；单分子保护性超时 300 s。' },
  { emoji: '📈', title: '批量与比较', desc: '同批最多 20 个分子串行对接，单分子失败不终止整批；批内相对指标（affinity、配体效率、pose 区分度、类药性 fit、准备质量）与雷达图画像，归一化公式随结果一并输出。' },
  { emoji: '🎁', title: '结果解读与打包', desc: '固定科学措辞的解释报告（result.json / result.md / comparison.csv）、描述符与警告、manifest 记录输入/产物哈希与版本，bundle.zip 全量产物打包。' },
];

const WORKFLOW_STATES: readonly { state: string; desc: string }[] = [
  { state: 'CREATED', desc: '任务已创建，进入串行队列' },
  { state: 'VALIDATING', desc: '输入 Schema 校验（Pydantic + JSON Schema）' },
  { state: 'PREPARING_LIGAND', desc: '配体 3D 构建与 PDBQT 准备（RDKit + Meeko）' },
  { state: 'PREPARING_RECEPTOR', desc: '受体分析与清洗（Biopython + Meeko）' },
  { state: 'VALIDATING_BOX', desc: '搜索盒四模式校验' },
  { state: 'DOCKING', desc: 'AutoDock Vina 对接（API 优先 / CLI 回退）' },
  { state: 'PARSING', desc: '打分解析与 pose 导出' },
  { state: 'ANALYZING', desc: '描述符、批内相对指标与解释报告' },
  { state: 'PACKAGING', desc: 'manifest 哈希记录与 bundle 打包' },
  { state: 'SUCCESS / FAILED / CANCELLED', desc: '终态：成功（可含警告）/ 结构化错误失败 / 取消' },
];

const QUICK_COMMANDS: readonly { cmd: string; desc: string }[] = [
  { cmd: 'mamba env create -f environment.yml && conda activate dockskill', desc: '创建并激活 conda 环境（一次性，Python 3.11，macOS arm64）' },
  { cmd: 'make check', desc: '环境自检，成功输出标记 DOCKING_SKILL_CHECK_PASS' },
  { cmd: 'make example', desc: '运行示例：乙醇真实对接 + 非法 SMILES 结构化错误，输出 RUN_EXAMPLE_PASS' },
  { cmd: 'make test', desc: 'pytest 109 个用例（含 13 个失败案例回归）' },
  { cmd: 'make reproducibility', desc: '双跑可复现验证，输出 REPRODUCIBILITY_PASS' },
  { cmd: 'make backend', desc: '启动 FastAPI（仅监听 127.0.0.1:8000）' },
  { cmd: 'make frontend', desc: '启动前端 Demo（http://localhost:5173，首次需 cd frontend && npm install）' },
];

interface PipelineStep {
  title: string;
  sub: string;
  stroke: string;
}

const PIPELINE_STEPS: readonly PipelineStep[] = [
  { title: 'SMILES 输入', sub: '配体规格 ≤20 个', stroke: '#223048' },
  { title: '3D 构象生成', sub: 'RDKit · PDBQT 准备', stroke: '#223048' },
  { title: '受体准备', sub: '清洗与链/水策略', stroke: '#223048' },
  { title: '搜索盒校验', sub: '四模式硬约束', stroke: '#223048' },
  { title: 'Vina 对接', sub: '固定 seed 可复现', stroke: '#3fbf7f' },
  { title: '结果解读', sub: '雷达图 · bundle 打包', stroke: '#4da3ff' },
];

/** 内联 SVG：六步对接管线流程图（中文标注，配色随页面深色科研风格） */
function PipelineDiagram(): JSX.Element {
  const boxW = 145;
  const boxH = 54;
  const gap = 12;
  const top = 30;
  return (
    <svg
      className="intro-pipeline"
      viewBox={`0 0 ${PIPELINE_STEPS.length * (boxW + gap) - gap + 20} 130`}
      role="img"
      aria-label="分子对接工作流管线图"
    >
      <defs>
        <marker id="pipeline-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 0 0 L 8 4 L 0 8 z" fill="#4da3ff" />
        </marker>
      </defs>
      {PIPELINE_STEPS.map((step, i) => {
        const x = 10 + i * (boxW + gap);
        return (
          <g key={step.title}>
            {i > 0 && (
              <line
                x1={x - gap + 2}
                y1={top + boxH / 2}
                x2={x - 3}
                y2={top + boxH / 2}
                stroke="#4da3ff"
                strokeWidth={1.5}
                markerEnd="url(#pipeline-arrow)"
              />
            )}
            <rect x={x} y={top} width={boxW} height={boxH} rx={8} fill="#0d1420" stroke={step.stroke} strokeWidth={1.5} />
            <text x={x + boxW / 2} y={top + 23} textAnchor="middle" fill="#d7e0ec" fontSize={12.5} fontWeight={600}>
              {step.title}
            </text>
            <text x={x + boxW / 2} y={top + 40} textAnchor="middle" fill="#8494ab" fontSize={10}>
              {step.sub}
            </text>
          </g>
        );
      })}
      <text x={10} y={112} fill="#8494ab" fontSize={10.5}>
        任一步骤失败 → 结构化错误终态 FAILED（error_code / stage / 可恢复性 / 建议修复动作），绝不静默修复。
      </text>
    </svg>
  );
}

export default function IntroPage(): JSX.Element {
  return (
    <main className="intro-page">
      <section className="panel">
        <h2>🎯 项目简介</h2>
        <p>
          <strong>DockingCopilot Skill</strong> 是面向 <strong>AI for Biomedicine</strong> 黑客松赛道的
          分子对接工作流 Skill：把「SMILES + 受体 PDB + 对接配置」封装为一条输入输出明确、参数受控、
          过程可追踪、失败可诊断、结果可解释、运行可复现的 AutoDock Vina 对接流水线。
        </p>
        <p className="muted">
          后端为 FastAPI + Python 3.11（RDKit / Meeko / AutoDock Vina / Open Babel / Biopython），
          前端为 React + Vite + TypeScript（3Dmol.js 三维视图 + ECharts 雷达图）。主交付物为仓库根目录的
          SKILL.md（23 节完整 Skill 文档），本页面内容与之一致。
        </p>
        <div className="intro-page__figures-duo">
          <figure className="intro-page__figure">
            <img src="/intro_target_3d.png" alt="靶点蛋白三维结构渲染图" loading="lazy" />
            <figcaption>
              靶点蛋白三维结构渲染（项目自有示例靶点，仅用于流程演示；示例盒中心不代表真实结合位点）
            </figcaption>
          </figure>
          <figure className="intro-page__figure">
            <img src="/intro_recommendation_pipeline.png" alt="分子推荐流程示意图" loading="lazy" />
            <figcaption>
              分子推荐流程：候选分子 → 打分排序 → Top-N 推荐（批内相对指标，仅展示性比较）
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="panel">
        <h2>⚙️ 功能特性</h2>
        <ul className="intro-page__features">
          {FEATURES.map((f) => (
            <li key={f.title}>
              <strong>{f.emoji} {f.title}</strong>
              <span>{f.desc}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>🔄 工作流概览（12 态状态机）</h2>
        <p className="muted">
          任务由 CREATED 进入串行队列，沿 9 个执行阶段顺序推进，最终进入三个终态之一；
          任一阶段失败都写入结构化错误（error_code / stage / 可恢复性 / 建议修复动作）。
        </p>
        <PipelineDiagram />
        <table className="data-table">
          <thead>
            <tr>
              <th>状态</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {WORKFLOW_STATES.map((s) => (
              <tr key={s.state}>
                <td className="cell-mono">{s.state}</td>
                <td>{s.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>🖥️ Demo 效果</h2>
        <div className="intro-page__figures-row">
          <figure className="intro-page__figure">
            <img src="/intro_demo_workflow.png" alt="Web Demo 工作流运行成功截图" loading="lazy" />
            <figcaption>
              网页 Demo：任务运行至 SUCCESS，步骤条、三维视图与结果表实时联动
            </figcaption>
          </figure>
          <figure className="intro-page__figure">
            <img src="/intro_demo_radar.png" alt="雷达图批内多分子比较截图" loading="lazy" />
            <figcaption>
              雷达图：同批多分子相对画像（Relative Docking &amp; Developability Profile，仅批内展示性比较）
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="panel">
        <h2>🧪 科学边界</h2>
        <ul>
          <li>⚠️ Vina affinity 是经验打分函数的估计值，不是结合自由能，不能换算 Kd/Ki/IC50，也不代表药效或活性；</li>
          <li>🧊 静态刚性受体：不考虑诱导契合、侧链重排与显式溶剂效应；质子化采用工具默认策略，不做 pH 显式建模；</li>
          <li>🚫 分数跨体系不可比：受体、链选择、box、质子化、参数任一不同即不可比；
            相对排序仅在同一受体、同一准备流程、同一 box、同一参数的同一批次内有展示意义；</li>
          <li>📐 分数接近（&lt; 1 kcal/mol）的 pose 不可区分；rmsd_lb/rmsd_ub 是 Vina 的自参照估计，不是对实验构象的 RMSD；</li>
          <li>🔬 本工具输出仅用于假设生成、候选排序与教学，不替代 MD/FEP 与实验验证，不用于医疗建议。</li>
        </ul>
      </section>

      <section className="panel">
        <h2>🚀 快速开始</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>命令</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            {QUICK_COMMANDS.map((c) => (
              <tr key={c.cmd}>
                <td className="cell-mono">{c.cmd}</td>
                <td>{c.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>📊 数据来源与自主性声明</h2>
        <p>
          ✅ 本 Skill 不依赖任何官方提供的领域知识库或标准答案。解释模板与科学限制文案由参赛者基于
          AutoDock Vina 与 RDKit 的公开文档及通用计算化学教材性知识自主整理；
          示例受体为项目自有数据文件（来源说明见 examples/data/DATA_PROVENANCE.md），
          数据收集与内容创作均由参赛者自主完成。
        </p>
      </section>
    </main>
  );
}
