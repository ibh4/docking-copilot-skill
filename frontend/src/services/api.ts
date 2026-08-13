/**
 * API 服务层：全部请求走 Vite dev 代理（/api、/health -> http://127.0.0.1:8000）。
 * 错误统一转换为 ApiRequestError（携带后端结构化错误字段），界面绝不吞错。
 */
import type {
  ComparisonOutput,
  DockingInput,
  DockingResultFile,
  HealthResponse,
  JobStatus,
  StructuredError,
  SubmitResponse,
  VersionResponse,
} from '../types';

export class ApiRequestError extends Error {
  readonly status: number;
  readonly structured: StructuredError;

  constructor(status: number, structured: StructuredError) {
    super(structured.message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.structured = structured;
  }
}

function toStructuredError(status: number, raw: unknown, fallback: string): StructuredError {
  if (raw !== null && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    const message = typeof obj['message'] === 'string' ? obj['message'] : fallback;
    const details = obj['details'];
    const suggested = obj['suggested_actions'];
    return {
      error_code: typeof obj['error_code'] === 'string' ? obj['error_code'] : `HTTP_${status}`,
      stage: typeof obj['stage'] === 'string' ? obj['stage'] : 'http',
      message,
      details: details !== null && typeof details === 'object' ? (details as Record<string, unknown>) : undefined,
      recoverable: typeof obj['recoverable'] === 'boolean' ? obj['recoverable'] : false,
      suggested_actions: Array.isArray(suggested) ? suggested.filter((s): s is string => typeof s === 'string') : undefined,
    };
  }
  return { error_code: `HTTP_${status}`, stage: 'http', message: fallback, recoverable: false };
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (err) {
    throw new ApiRequestError(0, {
      error_code: 'NETWORK_UNREACHABLE',
      stage: 'http',
      message: `无法连接后端（${path}）。请确认 FastAPI 服务运行于 http://127.0.0.1:8000。`,
      recoverable: true,
      suggested_actions: ['启动后端：uvicorn backend.app:app --port 8000', '确认 dev 代理配置 /api -> 127.0.0.1:8000'],
      details: { cause: err instanceof Error ? err.message : String(err) },
    });
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw new ApiRequestError(res.status, toStructuredError(res.status, body, `请求失败：${res.status} ${res.statusText}（${path}）`));
  }
  return (await res.json()) as T;
}

async function httpText(path: string): Promise<string> {
  let res: Response;
  try {
    res = await fetch(path);
  } catch {
    throw new ApiRequestError(0, {
      error_code: 'NETWORK_UNREACHABLE',
      stage: 'http',
      message: `无法连接后端（${path}）。`,
      recoverable: true,
    });
  }
  if (!res.ok) {
    throw new ApiRequestError(res.status, {
      error_code: res.status === 404 ? 'FILE_NOT_FOUND' : `HTTP_${res.status}`,
      stage: 'files',
      message: `文件不可用（${res.status}）：${path}`,
      recoverable: res.status !== 404,
    });
  }
  return res.text();
}

// ---------- 端点封装 ----------

export function fetchHealth(): Promise<HealthResponse> {
  return http<HealthResponse>('/health');
}

export function fetchVersion(): Promise<VersionResponse> {
  return http<VersionResponse>('/api/version');
}

/** 单分子用 /api/docking/run，多分子（≤20）用 /api/docking/batch */
export function submitDocking(input: DockingInput): Promise<SubmitResponse> {
  const path = input.ligands.length <= 1 ? '/api/docking/run' : '/api/docking/batch';
  return http<SubmitResponse>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
}

export function fetchJobStatus(jobId: string): Promise<JobStatus> {
  return http<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchJobResult(jobId: string): Promise<DockingResultFile> {
  return http<DockingResultFile>(`/api/jobs/${encodeURIComponent(jobId)}/result`);
}

export function fetchJobArtifacts(jobId: string): Promise<unknown[]> {
  return http<unknown[]>(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`);
}

export function fetchComparison(jobId: string): Promise<ComparisonOutput> {
  return http<ComparisonOutput>('/api/comparison', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function fetchJobFileText(jobId: string, relativePath: string): Promise<string> {
  return httpText(jobFileUrl(jobId, relativePath));
}

/** 产物文件下载/展示 URL（files 端点） */
export function jobFileUrl(jobId: string, relativePath: string): string {
  const clean = relativePath.replace(/^\/+/, '');
  return `/api/jobs/${encodeURIComponent(jobId)}/files/${clean
    .split('/')
    .map((seg) => encodeURIComponent(seg))
    .join('/')}`;
}

export function jobResultUrl(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/result`;
}

export function isApiError(err: unknown): err is ApiRequestError {
  return err instanceof ApiRequestError;
}

export function errorMessage(err: unknown): string {
  if (isApiError(err)) {
    return err.structured.message;
  }
  return err instanceof Error ? err.message : String(err);
}
