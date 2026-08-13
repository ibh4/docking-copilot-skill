/**
 * FailurePanel：失败界面。
 * 显示 error_code、失败阶段、可恢复性与建议修复动作；原输入在 InputPanel 中保留，
 * 用户可直接修改参数后重新提交。
 */
import type { StructuredError } from '../types';

export interface FailurePanelProps {
  error: StructuredError | null;
  jobId: string | null;
}

export default function FailurePanel({ error, jobId }: FailurePanelProps): JSX.Element | null {
  if (!error) {
    return null;
  }
  return (
    <section className="panel failure-panel">
      <h2>任务失败</h2>
      <table className="kv-table">
        <tbody>
          <tr>
            <td>错误码（error_code）</td>
            <td>{error.error_code}</td>
          </tr>
          <tr>
            <td>失败阶段（stage）</td>
            <td>{error.stage}</td>
          </tr>
          <tr>
            <td>可恢复（recoverable）</td>
            <td>{error.recoverable ? '是（可按建议修复后重试）' : '否'}</td>
          </tr>
          {jobId && (
            <tr>
              <td>任务 ID（job_id）</td>
              <td>{jobId}</td>
            </tr>
          )}
        </tbody>
      </table>
      <p className="failure-panel__message">{error.message}</p>
      {error.suggested_actions && error.suggested_actions.length > 0 && (
        <div className="failure-panel__actions">
          <span>建议修复：</span>
          <ul>
            {error.suggested_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      )}
      {error.details && Object.keys(error.details).length > 0 && (
        <details>
          <summary>详细数据（details）</summary>
          <pre>{JSON.stringify(error.details, null, 2)}</pre>
        </details>
      )}
      <p className="muted">原输入已保留在左侧输入区，可直接修改参数后重新提交。</p>
    </section>
  );
}
