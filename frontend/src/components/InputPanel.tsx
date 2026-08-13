/**
 * InputPanel：输入区。
 * - 多行 SMILES（每行 name<TAB 或空格>SMILES）；
 * - receptor 来源路径（仓库相对路径，契约不支持浏览器上传）；
 * - box 模式选择与 center/size / reference / residue 输入；
 * - exhaustiveness / num_modes / seed；
 * - 提交 + “运行前参数检查”（前端基本数值校验）。
 */
import { useState } from 'react';
import type { BoxMode, InputFormState } from '../types';
import { boxModeLabel, validateForm } from '../utils/validate';

export interface InputPanelProps {
  form: InputFormState;
  onChange: (form: InputFormState) => void;
  onSubmit: () => void;
  submitting: boolean;
  disabled: boolean;
}

const BOX_MODES: readonly BoxMode[] = ['explicit', 'reference_ligand', 'residue_list', 'whole_receptor'];

export default function InputPanel({ form, onChange, onSubmit, submitting, disabled }: InputPanelProps): JSX.Element {
  const [checkMessages, setCheckMessages] = useState<string[] | null>(null);

  const set = (patch: Partial<InputFormState>): void => {
    onChange({ ...form, ...patch });
    setCheckMessages(null);
  };

  const runCheck = (): void => {
    const errors = validateForm(form);
    setCheckMessages(errors);
  };

  const handleSubmit = (): void => {
    const errors = validateForm(form);
    setCheckMessages(errors);
    if (errors.length === 0) {
      onSubmit();
    }
  };

  return (
    <section className="panel input-panel">
      <h2>输入</h2>

      <label className="field">
        <span>任务名称（job_name）</span>
        <input
          type="text"
          value={form.jobName}
          maxLength={128}
          placeholder="my_docking_job"
          onChange={(e) => set({ jobName: e.target.value })}
        />
      </label>

      <label className="field">
        <span>配体 SMILES（每行：name&lt;TAB 或空格&gt;SMILES，最多 20 个）</span>
        <textarea
          value={form.ligandsText}
          rows={5}
          placeholder={'benzene\tc1ccccc1\nethanol\tCCO'}
          onChange={(e) => set({ ligandsText: e.target.value })}
        />
      </label>

      <label className="field">
        <span>受体来源（仓库相对路径，如 examples/data/sample_receptor.pdb）</span>
        <input type="text" value={form.receptorSource} onChange={(e) => set({ receptorSource: e.target.value })} />
      </label>

      <label className="field">
        <span>对接盒（Docking Box）模式</span>
        <select value={form.boxMode} onChange={(e) => set({ boxMode: e.target.value as BoxMode })}>
          {BOX_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {boxModeLabel(mode)}
            </option>
          ))}
        </select>
      </label>

      {form.boxMode === 'explicit' && (
        <div className="field-grid">
          <label className="field">
            <span>盒中心 center (x, y, z) Å</span>
            <div className="triple-input">
              <input type="text" value={form.centerX} placeholder="x" onChange={(e) => set({ centerX: e.target.value })} />
              <input type="text" value={form.centerY} placeholder="y" onChange={(e) => set({ centerY: e.target.value })} />
              <input type="text" value={form.centerZ} placeholder="z" onChange={(e) => set({ centerZ: e.target.value })} />
            </div>
          </label>
          <label className="field">
            <span>盒边长 size (x, y, z) Å</span>
            <div className="triple-input">
              <input type="text" value={form.sizeX} placeholder="x" onChange={(e) => set({ sizeX: e.target.value })} />
              <input type="text" value={form.sizeY} placeholder="y" onChange={(e) => set({ sizeY: e.target.value })} />
              <input type="text" value={form.sizeZ} placeholder="z" onChange={(e) => set({ sizeZ: e.target.value })} />
            </div>
          </label>
        </div>
      )}

      {form.boxMode === 'reference_ligand' && (
        <div className="field-grid">
          <label className="field">
            <span>参考配体残基（如 LIG 或 A/1437）</span>
            <input type="text" value={form.referenceLigandResid} onChange={(e) => set({ referenceLigandResid: e.target.value })} />
          </label>
          <label className="field">
            <span>外扩 padding (Å，0-12)</span>
            <input type="text" value={form.padding} onChange={(e) => set({ padding: e.target.value })} />
          </label>
        </div>
      )}

      {form.boxMode === 'residue_list' && (
        <div className="field-grid">
          <label className="field">
            <span>口袋残基列表（如 A/585,A/600）</span>
            <input type="text" value={form.residueIds} onChange={(e) => set({ residueIds: e.target.value })} />
          </label>
          <label className="field">
            <span>外扩 padding (Å，0-12)</span>
            <input type="text" value={form.padding} onChange={(e) => set({ padding: e.target.value })} />
          </label>
        </div>
      )}

      {form.boxMode === 'whole_receptor' && (
        <p className="warning-text">whole_receptor 仅用于小型测试：搜索空间大，耗时且结果解释力弱。</p>
      )}

      <div className="field-grid">
        <label className="field">
          <span>exhaustiveness (1-32)</span>
          <input type="text" value={form.exhaustiveness} onChange={(e) => set({ exhaustiveness: e.target.value })} />
        </label>
        <label className="field">
          <span>num_modes (1-20)</span>
          <input type="text" value={form.numModes} onChange={(e) => set({ numModes: e.target.value })} />
        </label>
        <label className="field">
          <span>seed</span>
          <input type="text" value={form.seed} onChange={(e) => set({ seed: e.target.value })} />
        </label>
      </div>

      {checkMessages !== null && (
        <div className={checkMessages.length === 0 ? 'check-ok' : 'check-errors'}>
          {checkMessages.length === 0 ? (
            <span>参数检查通过：可以提交。</span>
          ) : (
            <ul>
              {checkMessages.map((msg) => (
                <li key={msg}>{msg}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="input-panel__actions">
        <button type="button" className="btn" onClick={runCheck} disabled={disabled}>
          运行前参数检查
        </button>
        <button type="button" className="btn btn--primary" onClick={handleSubmit} disabled={disabled || submitting}>
          {submitting ? '提交中…' : '提交对接任务'}
        </button>
      </div>
    </section>
  );
}
