/**
 * WorkflowStepper：工作流步骤条。
 * 将 12 个 JobState 映射为 8 个展示步骤；五态样式 pending/running/success/warning/failed；
 * 点击步骤显示 message、产物链接与失败建议。
 * 轮询由 App 层完成（2s 间隔，终态停止），本组件只消费状态。
 */
import { useState } from 'react';
import { jobFileUrl } from '../services/api';
import type { ArtifactEntry, DockingResultFile, JobState, JobStatus } from '../types';

export interface WorkflowStepperProps {
  jobId: string | null;
  jobStatus: JobStatus | null;
  result: DockingResultFile | null;
}

interface StepDef {
  label: string;
  state: JobState;
}

const STEPS: readonly StepDef[] = [
  { label: '输入校验', state: 'VALIDATING' },
  { label: '配体 3D', state: 'PREPARING_LIGAND' },
  { label: '受体准备', state: 'PREPARING_RECEPTOR' },
  { label: '对接盒校验', state: 'VALIDATING_BOX' },
  { label: 'Vina 对接', state: 'DOCKING' },
  { label: 'Pose 解析', state: 'PARSING' },
  { label: '结果解读', state: 'ANALYZING' },
  { label: '打包', state: 'PACKAGING' },
];

type StepVisual = 'pending' | 'running' | 'success' | 'warning' | 'failed';

function stateIndex(state: string): number {
  return STEPS.findIndex((s) => s.state.toLowerCase() === state.toLowerCase());
}

function computeStepVisuals(jobStatus: JobStatus | null, result: DockingResultFile | null): StepVisual[] {
  if (!jobStatus) {
    return STEPS.map(() => 'pending');
  }
  const { state } = jobStatus;
  if (state === 'SUCCESS') {
    const hasWarnings = (result?.warnings?.length ?? 0) > 0;
    return STEPS.map((_, i) => (hasWarnings && i === STEPS.length - 1 ? 'warning' : 'success'));
  }
  if (state === 'FAILED') {
    const errStage = jobStatus.structured_error?.stage ?? '';
    let failedIdx = stateIndex(state);
    // 失败阶段优先按 JobState 匹配（大小写不敏感），避免中文标签化后丢失回退匹配
    const errIdx = STEPS.findIndex((s) => s.state.toLowerCase() === errStage.toLowerCase());
    if (errIdx >= 0) {
      failedIdx = errIdx;
    }
    if (failedIdx < 0) {
      failedIdx = 0;
    }
    return STEPS.map((_, i) => (i < failedIdx ? 'success' : i === failedIdx ? 'failed' : 'pending'));
  }
  if (state === 'CANCELLED') {
    const idx = stateIndex(jobStatus.step ?? '');
    return STEPS.map((_, i) => (idx >= 0 && i === idx ? 'warning' : 'pending'));
  }
  if (state === 'CREATED') {
    return STEPS.map(() => 'pending');
  }
  const idx = stateIndex(state);
  return STEPS.map((_, i) => (i < idx ? 'success' : i === idx ? 'running' : 'pending'));
}

const VISUAL_SYMBOL: Record<StepVisual, string> = {
  pending: '○',
  running: '◐',
  success: '✓',
  warning: '⚠',
  failed: '✗',
};

const VISUAL_LABEL: Record<StepVisual, string> = {
  pending: '等待中',
  running: '进行中',
  success: '成功',
  warning: '有警告',
  failed: '失败',
};

/** 兼容两种 artifacts 形态：列表（契约）与 dict 名称→路径（当前后端实现） */
function normalizeArtifacts(artifacts: JobStatus['artifacts']): ArtifactEntry[] {
  if (!artifacts) {
    return [];
  }
  if (Array.isArray(artifacts)) {
    return artifacts;
  }
  return Object.entries(artifacts).map(([name, path]) => ({ name, path }));
}

export default function WorkflowStepper({ jobId, jobStatus, result }: WorkflowStepperProps): JSX.Element {
  const [selectedStep, setSelectedStep] = useState<number | null>(null);

  const visuals = computeStepVisuals(jobStatus, result);
  const artifacts = normalizeArtifacts(jobStatus?.artifacts);
  const progress = typeof jobStatus?.progress === 'number' ? Math.min(100, Math.max(0, jobStatus.progress)) : null;

  return (
    <section className="panel workflow-stepper">
      <div className="workflow-stepper__head">
        <h2>工作流</h2>
        {jobStatus && (
          <span className="workflow-stepper__state">
            {jobStatus.state}
            {progress !== null ? ` · ${Math.round(progress)}%` : ''}
            {jobStatus.step ? ` · ${jobStatus.step}` : ''}
          </span>
        )}
        {jobId && <span className="workflow-stepper__job-id">任务 ID：{jobId}</span>}
      </div>

      {!jobStatus && <p className="muted">尚未提交任务。填写左侧输入，或点击下方「运行示例」按钮。</p>}

      {jobStatus && (
        <>
          <ol className="stepper">
            {STEPS.map((step, i) => (
              <li key={step.state}>
                <button
                  type="button"
                  className={`step step--${visuals[i] ?? 'pending'}${selectedStep === i ? ' step--selected' : ''}`}
                  onClick={() => setSelectedStep(selectedStep === i ? null : i)}
                >
                  <span className="step__symbol">{VISUAL_SYMBOL[visuals[i] ?? 'pending']}</span>
                  <span className="step__label">{step.label}</span>
                </button>
              </li>
            ))}
          </ol>

          {jobStatus.message && <p className="workflow-stepper__message">{jobStatus.message}</p>}

          {selectedStep !== null && (
            <div className="step-detail">
              <h3>{STEPS[selectedStep]?.label ?? ''}（{STEPS[selectedStep]?.state ?? ''}）</h3>
              <p className="muted">
                状态：{VISUAL_LABEL[visuals[selectedStep] ?? 'pending']}
                {jobStatus.state === STEPS[selectedStep]?.state && jobStatus.message ? ` — ${jobStatus.message}` : ''}
              </p>
              {artifacts.length > 0 && jobId && (
                <div>
                  <span>产物：</span>
                  <ul className="artifact-list">
                    {artifacts.map((artifact, i) => {
                      const path = artifact.path ?? artifact.name ?? `artifact_${i}`;
                      return (
                        <li key={`${path}_${i}`}>
                          {artifact.path ? (
                            <a href={jobFileUrl(jobId, artifact.path)} target="_blank" rel="noreferrer">
                              {artifact.name ?? artifact.path}
                            </a>
                          ) : (
                            <span>{artifact.name ?? path}</span>
                          )}
                          {typeof artifact.size_bytes === 'number' ? ` (${artifact.size_bytes} B)` : ''}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {jobStatus.state === 'FAILED' && jobStatus.structured_error && (
                <p className="error-text">
                  失败阶段：{jobStatus.structured_error.stage} — {jobStatus.structured_error.message}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
