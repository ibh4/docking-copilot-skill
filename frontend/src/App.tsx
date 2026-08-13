/**
 * App：页面编排与状态管理。
 * - 提交 docking（单分子 run / 多分子 batch）；
 * - 轮询 GET /api/jobs/{job_id}（2s 间隔，SUCCESS/FAILED/CANCELLED 后停止）；
 * - 成功后拉取 result.json 与 /api/comparison；
 * - 布局：顶部 StatusHeader（含「分子对接 / 项目介绍」导航）；左侧 MoleculeList + InputPanel；
 *   中部 WorkflowStepper + 运行示例按钮 + Viewer3D（标签面板内画布半尺寸居中）；
 *   右侧 ResultTable + RadarChart + FailurePanel；底部固定免责声明。
 * - 页面切换为前端内部 state 路由（无 react-router）：docking（默认首页）/ intro。
 * - Viewer3D / RadarChart 通过 React.lazy 懒加载（重组件分包）。
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import StatusHeader, { type AppPage } from './components/StatusHeader';
import InputPanel from './components/InputPanel';
import WorkflowStepper from './components/WorkflowStepper';
import ExampleLauncher from './components/ExampleLauncher';
import IntroPage from './components/IntroPage';
import MoleculeList from './components/MoleculeList';
import ResultTable from './components/ResultTable';
import FailurePanel from './components/FailurePanel';
import { errorMessage, isApiError, fetchComparison, fetchJobResult, fetchJobStatus, submitDocking } from './services/api';
import {
  EXAMPLE_FORM,
  EMPTY_FORM,
  type ComparisonOutput,
  type DockingInput,
  type DockingResultFile,
  type InputFormState,
  type JobStatus,
  type StructuredError,
  TERMINAL_STATES,
} from './types';
import { buildDockingInput, validateForm } from './utils/validate';

const Viewer3D = lazy(() => import('./components/Viewer3D'));
const RadarChart = lazy(() => import('./components/RadarChart'));

const POLL_INTERVAL_MS = 2000;

const DISCLAIMER =
  '免责声明：Vina 对接打分为计算估计值，不代表实验结合亲和力、自由能或药效；' +
  '所有指标仅适用于同一受体、同一准备流程、同一 docking box、同一参数下的同批次相对比较。';

export default function App(): JSX.Element {
  const [page, setPage] = useState<AppPage>('docking');
  const [offline, setOffline] = useState(false);
  const [form, setForm] = useState<InputFormState>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<StructuredError | null>(null);

  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<DockingResultFile | null>(null);
  const [comparison, setComparison] = useState<ComparisonOutput | null>(null);
  const [submittedInput, setSubmittedInput] = useState<DockingInput | null>(null);
  const [selectedLigandId, setSelectedLigandId] = useState<string | null>(null);

  const ligandResults = useMemo(() => {
    if (!result) {
      return [];
    }
    return result.ligand_results ?? result.results ?? [];
  }, [result]);

  const selectedLigand = useMemo(
    () => ligandResults.find((r) => r.ligand_id === selectedLigandId) ?? null,
    [ligandResults, selectedLigandId],
  );

  // 页面切换时同步浏览器标签页标题
  useEffect(() => {
    document.title = page === 'intro' ? 'DockingCopilot Skill · 项目介绍' : 'DockingCopilot Skill · 分子对接';
  }, [page]);

  const resetJobState = useCallback((): void => {
    setJobId(null);
    setJobStatus(null);
    setResult(null);
    setComparison(null);
    setSelectedLigandId(null);
  }, []);

  const submit = useCallback(async (input: DockingInput): Promise<void> => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await submitDocking(input);
      resetJobState();
      setJobId(res.job_id);
      setSubmittedInput(input);
      setJobStatus({ state: 'CREATED', job_id: res.job_id });
    } catch (err) {
      // 提交失败时清空旧任务状态，避免 FailurePanel 残留上一个任务的 job_id
      resetJobState();
      if (isApiError(err)) {
        // 透传后端已解析的结构化错误（error_code/stage/details/suggested_actions）
        setSubmitError(err.structured);
      } else {
        setSubmitError({
          error_code: 'SUBMIT_FAILED',
          stage: 'submit',
          message: errorMessage(err),
          recoverable: true,
          suggested_actions: ['检查后端是否启动（/health）', '核对输入参数后重试'],
        });
      }
    } finally {
      setSubmitting(false);
    }
  }, [resetJobState]);

  const handleSubmit = useCallback((): void => {
    const errors = validateForm(form);
    if (errors.length > 0) {
      return;
    }
    void submit(buildDockingInput(form));
  }, [form, submit]);

  const handleRunExample = useCallback((): void => {
    setForm(EXAMPLE_FORM);
    void submit(buildDockingInput(EXAMPLE_FORM));
  }, [submit]);

  // 轮询任务状态：2s 间隔，终态后停止并拉取 result 与 comparison
  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;

    const poll = async (): Promise<boolean> => {
      try {
        const status = await fetchJobStatus(jobId);
        if (!active) {
          return false;
        }
        setJobStatus(status);
        if (TERMINAL_STATES.includes(status.state)) {
          if (status.state === 'SUCCESS') {
            try {
              const res = await fetchJobResult(jobId);
              if (!active) {
                return false;
              }
              setResult(res);
              const candidates = res.ligand_results ?? res.results ?? [];
              const firstSuccess = candidates.find((r) => r.status === 'SUCCESS');
              setSelectedLigandId(firstSuccess?.ligand_id ?? candidates[0]?.ligand_id ?? null);
            } catch (err) {
              setJobStatus((prev) => (prev ? { ...prev, message: `结果加载失败：${errorMessage(err)}` } : prev));
            }
            fetchComparison(jobId)
              .then((cmp) => {
                if (active) {
                  setComparison(cmp);
                }
              })
              .catch(() => {
                if (active) {
                  setComparison(null);
                }
              });
          }
          return false;
        }
        return true;
      } catch (err) {
        if (active) {
          setJobStatus((prev) => (prev ? { ...prev, message: `状态轮询失败：${errorMessage(err)}` } : prev));
        }
        return true;
      }
    };

    void poll();
    const timer = setInterval(() => {
      void poll().then((cont) => {
        if (!cont) {
          clearInterval(timer);
        }
      });
    }, POLL_INTERVAL_MS);

    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [jobId]);

  return (
    <div className="app">
      <StatusHeader activePage={page} onNavigate={setPage} onOfflineChange={setOffline} />

      {page === 'intro' ? (
        <IntroPage />
      ) : (
      <main className="app__main">
        <div className="app__col app__col--left">
          <MoleculeList
            jobId={jobId}
            results={ligandResults}
            selectedLigandId={selectedLigandId}
            onSelect={setSelectedLigandId}
          />
          <InputPanel
            form={form}
            onChange={setForm}
            onSubmit={handleSubmit}
            submitting={submitting}
            disabled={false}
          />
          {submitError && <FailurePanel error={submitError} jobId={jobId} />}
        </div>

        <div className="app__col app__col--center">
          <WorkflowStepper jobId={jobId} jobStatus={jobStatus} result={result} />
          <ExampleLauncher onRunExample={handleRunExample} submitting={submitting} offline={offline} />
          <Suspense fallback={<div className="panel">3D 视图加载中…</div>}>
            <Viewer3D
              jobId={result ? jobId : null}
              ligandResults={ligandResults}
              selectedLigandId={selectedLigandId}
              box={submittedInput?.docking_box ?? null}
            />
          </Suspense>
        </div>

        <div className="app__col app__col--right">
          <ResultTable jobId={jobId} result={result} selectedLigand={selectedLigand} submittedInput={submittedInput} />
          <Suspense fallback={<div className="panel">雷达图加载中…</div>}>
            <RadarChart results={ligandResults} comparison={comparison} selectedLigandId={selectedLigandId} />
          </Suspense>
          {jobStatus?.state === 'FAILED' && <FailurePanel error={jobStatus.structured_error ?? {
            error_code: 'UNKNOWN',
            stage: jobStatus.step ?? 'unknown',
            message: jobStatus.message ?? '任务失败（后端未返回结构化错误）',
            recoverable: false,
          }} jobId={jobId} />}
        </div>
      </main>
      )}

      <footer className="app__disclaimer">{DISCLAIMER}</footer>
    </div>
  );
}
