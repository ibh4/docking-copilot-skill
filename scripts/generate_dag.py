#!/usr/bin/env python3
"""生成工作流 DAG 产物：dags/workflow.mmd / workflow.json / workflow.svg。

节点与边来自 backend/app/workflow/dag.py（与 runner 状态机单一事实来源一致），
SVG 为脚本自绘的简化矢量图（纯静态布局，无外部依赖）。

用法：
    conda run -n dockskill python scripts/generate_dag.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.workflow.dag import build_dag, to_json_text, to_mermaid  # noqa: E402

DAGS_DIR = PROJECT_ROOT / "dags"

# -- SVG 布局常量 ------------------------------------------------------------
BOX_WIDTH = 260
BOX_HEIGHT = 34
V_GAP = 16
MARGIN = 24
STATE_BADGE_DX = 12


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def build_svg() -> str:
    """按 DAG 节点顺序绘制纵向流程图（简化矢量图）。"""
    nodes, edges = build_dag()
    n = len(nodes)
    width = BOX_WIDTH + 2 * MARGIN + 220
    height = MARGIN * 2 + n * BOX_HEIGHT + (n - 1) * V_GAP + 60

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        'font-family="Helvetica, Arial, sans-serif">'
    )
    parts.append(
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
    )
    parts.append(
        f'<text x="{MARGIN}" y="{MARGIN}" font-size="16" font-weight="bold">'
        "DockingCopilot Skill workflow DAG (nodes == runner states)</text>"
    )

    index_of = {node.id: i for i, node in enumerate(nodes)}

    def node_y(i: int) -> int:
        return MARGIN + 30 + i * (BOX_HEIGHT + V_GAP)

    for edge in edges:
        i, j = index_of[edge.source], index_of[edge.target]
        x = MARGIN + BOX_WIDTH // 2
        y1 = node_y(i) + BOX_HEIGHT
        y2 = node_y(j)
        parts.append(
            f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - 6}" '
            'stroke="#444444" stroke-width="1.5"/>'
        )
        parts.append(
            f'<polygon points="{x - 5},{y2 - 8} {x + 5},{y2 - 8} {x},{y2}" '
            'fill="#444444"/>'
        )

    for i, node in enumerate(nodes):
        y = node_y(i)
        parts.append(
            f'<rect x="{MARGIN}" y="{y}" width="{BOX_WIDTH}" '
            f'height="{BOX_HEIGHT}" rx="6" fill="#eef4ff" '
            'stroke="#3355aa" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{MARGIN + 12}" y="{y + BOX_HEIGHT // 2 + 5}" '
            f'font-size="13" fill="#111111">{_escape(node.id)}</text>'
        )
        parts.append(
            f'<text x="{MARGIN + BOX_WIDTH + STATE_BADGE_DX}" '
            f'y="{y + BOX_HEIGHT // 2 + 5}" font-size="11" fill="#555555">'
            f"state: {_escape(node.state)}</text>"
        )

    parts.append(
        f'<text x="{MARGIN}" y="{height - MARGIN // 2}" font-size="11" '
        'fill="#666666">任何步骤失败 → FAILED（结构化错误）；'
        "终态：SUCCESS / FAILED / CANCELLED</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> int:
    DAGS_DIR.mkdir(parents=True, exist_ok=True)
    mmd_path = DAGS_DIR / "workflow.mmd"
    json_path = DAGS_DIR / "workflow.json"
    svg_path = DAGS_DIR / "workflow.svg"
    mmd_path.write_text(to_mermaid(), encoding="utf-8")
    json_path.write_text(to_json_text(), encoding="utf-8")
    svg_path.write_text(build_svg(), encoding="utf-8")
    for path in (mmd_path, json_path, svg_path):
        print(f"written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
