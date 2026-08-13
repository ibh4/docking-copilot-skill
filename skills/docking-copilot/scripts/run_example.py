#!/usr/bin/env python3
"""Official-skill wrapper around the repository's existing reproducible example."""
from pathlib import Path
import os, runpy, sys

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[3]
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))
runpy.run_path(str(REPO_ROOT / "scripts" / "run_example.py"), run_name="__main__")
