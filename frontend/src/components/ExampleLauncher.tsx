/**
 * ExampleLauncher：工作流步骤条下方的「运行示例」按钮。
 * 绿色主按钮 + 中文说明行；点击行为与原顶部 Run Example 完全一致
 * （加载仓库示例 benzene + ethanol 并提交对接任务）。
 */

export interface ExampleLauncherProps {
  onRunExample: () => void;
  submitting: boolean;
  offline: boolean;
}

export default function ExampleLauncher({ onRunExample, submitting, offline }: ExampleLauncherProps): JSX.Element {
  return (
    <div className="example-launcher">
      <button
        type="button"
        className="btn btn--example"
        onClick={onRunExample}
        disabled={submitting || offline}
        title={offline ? '后端离线，无法运行示例' : '加载仓库内置示例（benzene + ethanol）并提交'}
      >
        {submitting ? '提交中…' : '运行示例'}
      </button>
      <p className="example-launcher__hint">
        一键运行内置示例：苯（benzene）+ 乙醇（ethanol）对接随仓库分发的样例受体，体验完整对接流程。
      </p>
    </div>
  );
}
