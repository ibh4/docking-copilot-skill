"""版本信息端点。"""

from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.services.provenance_service import environment_versions

router = APIRouter(prefix="/api", tags=["version"])


@router.get(
    "/version",
    summary="服务与科学计算依赖版本",
    responses={
        200: {
            "description": "版本信息",
            "content": {
                "application/json": {
                    "example": {
                        "skill_version": "0.1.0",
                        "api_version": "v1",
                        "vina": "1.2.5",
                        "rdkit": "2024.09.6",
                        "meeko": "0.7.0",
                        "python": "3.11.12",
                    }
                }
            },
        }
    },
)
def version() -> dict:
    """返回 Skill/API 版本与 Vina、RDKit、Meeko、Python 运行时版本。"""
    env = environment_versions()
    return {
        "skill_version": __version__,
        "api_version": "v1",
        "vina": env["vina_version"],
        "rdkit": env["rdkit_version"],
        "meeko": env["meeko_version"],
        "python": env["python_version"],
    }
