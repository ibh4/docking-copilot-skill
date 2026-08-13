/**
 * 输入解析与运行前参数检查（前端基本数值校验；最终校验以后端 VALIDATING 阶段为准）。
 */
import type { BoxMode, DockingBox, DockingInput, InputFormState, LigandSpec } from '../types';

const MAX_LIGANDS = 20;

/**
 * 解析多行 SMILES 文本。
 * 每行格式：`name<TAB 或空格>SMILES`；无名称时自动生成 mol_N。
 * 空行与以 # 开头的行被忽略。
 */
export function parseLigandLines(text: string): LigandSpec[] {
  const ligands: LigandSpec[] = [];
  const lines = text.split('\n');
  let auto = 0;
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line.length === 0 || line.startsWith('#')) {
      continue;
    }
    let name = '';
    let smiles = line;
    if (line.includes('\t')) {
      const parts = line.split('\t');
      name = (parts[0] ?? '').trim();
      smiles = (parts.slice(1).join('\t') ?? '').trim();
    } else {
      const firstSpace = line.indexOf(' ');
      if (firstSpace > 0) {
        name = line.slice(0, firstSpace).trim();
        smiles = line.slice(firstSpace + 1).trim();
      }
    }
    auto += 1;
    const idBase = name.length > 0 ? name : smiles;
    const ligandId = sanitizeLigandId(idBase) || `mol_${auto}`;
    ligands.push({
      ligand_id: ligandId,
      smiles,
      name: name.length > 0 ? name : null,
    });
  }
  return ligands;
}

/** ligand_id 约束：1-64 字符，空白替换为下划线 */
export function sanitizeLigandId(raw: string): string {
  return raw.replace(/\s+/g, '_').slice(0, 64);
}

function parseFinite(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

function parseInteger(value: string): number | null {
  const num = parseFinite(value);
  return num !== null && Number.isInteger(num) ? num : null;
}

/** 运行前参数检查：返回错误列表（空数组表示通过） */
export function validateForm(form: InputFormState): string[] {
  const errors: string[] = [];

  if (form.jobName.trim().length === 0) {
    errors.push('job_name 不能为空');
  } else if (form.jobName.trim().length > 128) {
    errors.push('job_name 长度不能超过 128');
  }

  const ligands = parseLigandLines(form.ligandsText);
  if (ligands.length === 0) {
    errors.push('至少需要 1 个配体（每行：name<TAB 或空格>SMILES）');
  } else if (ligands.length > MAX_LIGANDS) {
    errors.push(`批量模式最多支持 ${MAX_LIGANDS} 个配体，当前 ${ligands.length} 个`);
  }
  for (const ligand of ligands) {
    if (ligand.smiles.length === 0) {
      errors.push(`配体 ${ligand.ligand_id} 缺少 SMILES`);
    } else if (ligand.smiles.length > 500) {
      errors.push(`配体 ${ligand.ligand_id} 的 SMILES 过长（>500）`);
    }
  }
  const seen = new Set<string>();
  for (const ligand of ligands) {
    if (seen.has(ligand.ligand_id)) {
      errors.push(`ligand_id 重复：${ligand.ligand_id}`);
    }
    seen.add(ligand.ligand_id);
  }

  if (form.receptorSource.trim().length === 0) {
    errors.push('receptor.source 不能为空（仓库相对路径）');
  }

  if (form.boxMode === 'explicit') {
    const labels: ReadonlyArray<readonly [string, string]> = [
      ['center.x', form.centerX],
      ['center.y', form.centerY],
      ['center.z', form.centerZ],
    ];
    for (const [label, value] of labels) {
      if (parseFinite(value) === null) {
        errors.push(`box ${label} 必须是数字（当前 "${value}"）`);
      }
    }
    const sizes: ReadonlyArray<readonly [string, string]> = [
      ['size.x', form.sizeX],
      ['size.y', form.sizeY],
      ['size.z', form.sizeZ],
    ];
    for (const [label, value] of sizes) {
      const num = parseFinite(value);
      if (num === null) {
        errors.push(`box ${label} 必须是数字（当前 "${value}"）`);
      } else if (num <= 0) {
        errors.push(`box ${label} 必须 > 0`);
      } else if (num > 150) {
        errors.push(`box ${label} 过大（${num} Å），请确认单位与意图`);
      }
    }
  } else if (form.boxMode === 'reference_ligand') {
    if (form.referenceLigandResid.trim().length === 0) {
      errors.push('reference_ligand 模式需要提供参考配体残基标识（如 LIG 或 A/1437）');
    }
  } else if (form.boxMode === 'residue_list') {
    const residues = form.residueIds.split(/[\s,]+/).filter((s) => s.length > 0);
    if (residues.length === 0) {
      errors.push('residue_list 模式需要提供至少一个口袋残基标识（如 A/585,A/600）');
    }
  }

  const padding = parseFinite(form.padding);
  if (form.boxMode !== 'explicit') {
    if (padding === null) {
      errors.push('padding 必须是数字');
    } else if (padding < 0 || padding > 12) {
      errors.push('padding 取值范围为 0-12 Å');
    }
  }

  const exhaustiveness = parseInteger(form.exhaustiveness);
  if (exhaustiveness === null) {
    errors.push('exhaustiveness 必须是整数');
  } else if (exhaustiveness < 1 || exhaustiveness > 32) {
    errors.push('exhaustiveness 取值范围为 1-32');
  }

  const numModes = parseInteger(form.numModes);
  if (numModes === null) {
    errors.push('num_modes 必须是整数');
  } else if (numModes < 1 || numModes > 20) {
    errors.push('num_modes 取值范围为 1-20');
  }

  if (parseInteger(form.seed) === null) {
    errors.push('seed 必须是整数');
  }

  return errors;
}

/** 将表单转换为 DockingInput；调用前应先通过 validateForm */
export function buildDockingInput(form: InputFormState): DockingInput {
  const ligands = parseLigandLines(form.ligandsText);

  const dockingBox: DockingBox = { mode: form.boxMode, units: 'angstrom' };
  if (form.boxMode === 'explicit') {
    dockingBox.center = [
      parseFinite(form.centerX) ?? 0,
      parseFinite(form.centerY) ?? 0,
      parseFinite(form.centerZ) ?? 0,
    ];
    dockingBox.size = [
      parseFinite(form.sizeX) ?? 20,
      parseFinite(form.sizeY) ?? 20,
      parseFinite(form.sizeZ) ?? 20,
    ];
  } else {
    dockingBox.padding_angstrom = parseFinite(form.padding) ?? 8;
    if (form.boxMode === 'reference_ligand') {
      dockingBox.reference_ligand_resid = form.referenceLigandResid.trim();
    } else if (form.boxMode === 'residue_list') {
      dockingBox.residue_ids = form.residueIds.split(/[\s,]+/).filter((s) => s.length > 0);
    }
  }

  return {
    job_name: form.jobName.trim(),
    ligands,
    ligand_preparation: {
      add_hydrogens: true,
      embed_method: 'ETKDGv3',
      num_conformers: 10,
      optimize_force_field: 'MMFF94',
      max_iterations: 500,
      select_conformer_by: 'minimum_force_field_energy',
      random_seed: parseInteger(form.seed) ?? 42,
    },
    receptor: { source: form.receptorSource.trim() },
    docking_box: dockingBox,
    docking_parameters: {
      scoring_function: 'vina',
      exhaustiveness: parseInteger(form.exhaustiveness) ?? 8,
      num_modes: parseInteger(form.numModes) ?? 9,
      energy_range: 3.0,
      cpu: 4,
      seed: parseInteger(form.seed) ?? 42,
    },
  };
}

export function boxModeLabel(mode: BoxMode): string {
  switch (mode) {
    case 'explicit':
      return 'explicit（显式 center/size）';
    case 'reference_ligand':
      return 'reference_ligand（参考配体）';
    case 'residue_list':
      return 'residue_list（口袋残基）';
    case 'whole_receptor':
      return 'whole_receptor（全受体，仅测试）';
  }
}
