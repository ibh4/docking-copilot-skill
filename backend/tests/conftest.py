"""pytest 配置：把 backend/ 加入 sys.path，并提供公共 fixture。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PROJECT_ROOT = BACKEND_DIR.parent


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def sample_receptor_path(project_root: Path) -> Path:
    return project_root / "examples" / "data" / "sample_receptor.pdb"


@pytest.fixture()
def make_docking_input():
    """构造合法 DockingInput 的工厂（单分子乙醇，实测可用 box）。"""
    from app.schemas import DockingInput

    def _make(
        smiles: str = "CCO",
        ligand_id: str = "test_ligand",
        box_center=(18.3, 2.3, 21.4),
        box_size=(20.0, 20.0, 20.0),
        exhaustiveness: int = 8,
        receptor_source: str = "examples/data/sample_receptor.pdb",
    ) -> DockingInput:
        return DockingInput.model_validate(
            {
                "job_name": "pytest_job",
                "ligands": [{"ligand_id": ligand_id, "smiles": smiles}],
                "receptor": {"source": receptor_source},
                "docking_box": {
                    "mode": "explicit",
                    "center": list(box_center),
                    "size": list(box_size),
                },
                "docking_parameters": {
                    "exhaustiveness": exhaustiveness,
                    "num_modes": 3,
                    "seed": 42,
                    "cpu": 4,
                    "energy_range": 3.0,
                },
            }
        )

    return _make
