"""健康检查路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import VINA_EXECUTABLE

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="健康检查",
    responses={
        200: {
            "description": "服务可用",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "service": "DockingCopilot Skill",
                        "version": "0.1.0",
                        "vina_executable": "/opt/conda/envs/dockskill/bin/vina",
                    }
                }
            },
        }
    },
)
def health() -> dict:
    """返回服务与关键外部依赖的可用性摘要。"""
    return {
        "status": "ok",
        "service": "DockingCopilot Skill",
        "version": __version__,
        "vina_executable": str(VINA_EXECUTABLE) if VINA_EXECUTABLE else None,
    }
