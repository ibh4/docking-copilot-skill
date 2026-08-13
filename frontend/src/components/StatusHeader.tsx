/**
 * StatusHeader：顶部项目区。
 * - 「分子对接 / 项目介绍」导航栏（state 路由，当前项高亮）；
 * - 轮询 /health（5s）显示后端状态，并通过 onOfflineChange 上报离线状态；
 * - 展示 /api/version 的 skill 版本与环境信息；
 * - "查看 SKILL.md" 文本入口（展示相对路径）。
 */
import { useEffect, useState } from 'react';
import { fetchHealth, fetchVersion } from '../services/api';
import type { HealthResponse, VersionResponse } from '../types';

export type AppPage = 'docking' | 'intro';

export interface StatusHeaderProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  onOfflineChange: (offline: boolean) => void;
}

const NAV_ITEMS: readonly { page: AppPage; label: string }[] = [
  { page: 'docking', label: '分子对接' },
  { page: 'intro', label: '项目介绍' },
];

const SKILL_MD_PATH = '../SKILL.md'; // 相对 frontend/ 的仓库根路径

export default function StatusHeader({ activePage, onNavigate, onOfflineChange }: StatusHeaderProps): JSX.Element {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [offline, setOffline] = useState<boolean>(false);
  const [version, setVersion] = useState<VersionResponse | null>(null);

  useEffect(() => {
    let active = true;
    const check = async (): Promise<void> => {
      try {
        const h = await fetchHealth();
        if (active) {
          setHealth(h);
          setOffline(false);
        }
      } catch {
        if (active) {
          setHealth(null);
          setOffline(true);
        }
      }
    };
    void check();
    const timer = setInterval(() => void check(), 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  // 离线状态变化时上报给 App（供步骤条下方示例按钮禁用等使用）
  useEffect(() => {
    onOfflineChange(offline);
  }, [offline, onOfflineChange]);

  useEffect(() => {
    if (offline) {
      return;
    }
    let active = true;
    fetchVersion()
      .then((v) => {
        if (active) {
          setVersion(v);
        }
      })
      .catch(() => {
        if (active) {
          setVersion(null);
        }
      });
    return () => {
      active = false;
    };
  }, [offline]);

  const envParts: string[] = [];
  if (version) {
    if (version.vina) {
      envParts.push(`Vina ${version.vina}`);
    }
    if (version.rdkit) {
      envParts.push(`RDKit ${version.rdkit}`);
    }
    if (version.meeko) {
      envParts.push(`Meeko ${version.meeko}`);
    }
  }

  return (
    <header className="status-header">
      <div className="status-header__brand">
        <h1>DockingCopilot Skill</h1>
        <span className="status-header__subtitle">SMILES → Vina 对接 → 结构化结果与解释</span>
      </div>
      <nav className="status-header__nav" aria-label="页面导航">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.page}
            type="button"
            className={`nav-item${activePage === item.page ? ' nav-item--active' : ''}`}
            onClick={() => onNavigate(item.page)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="status-header__info">
        <span className={`badge ${offline ? 'badge--offline' : 'badge--online'}`}>
          {offline ? '后端离线' : `后端在线${health?.status ? `：${health.status}` : ''}`}
        </span>
        <span className="status-header__version">
          {version?.skill_version ? `Skill 版本 v${version.skill_version}` : 'Skill 版本未知'}
          {version?.api_version ? ` · API v${version.api_version}` : ''}
        </span>
        {envParts.length > 0 && <span className="status-header__env">{envParts.join(' · ')}</span>}
        <span className="status-header__skill-link" title={`仓库根目录下的 SKILL.md（相对 frontend/：${SKILL_MD_PATH}）`}>
          查看 SKILL.md（{SKILL_MD_PATH}）
        </span>
      </div>
      {offline && (
        <div className="status-header__offline-banner">
          后端不可达（http://127.0.0.1:8000）。界面仅离线展示，请先启动 FastAPI 后端后重试。
        </div>
      )}
    </header>
  );
}
