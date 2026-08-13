#!/usr/bin/env python3
from __future__ import annotations
import importlib, platform, shutil, sys

checks = [
    ("pydantic", "pydantic"),
    ("rdkit", "rdkit"),
    ("meeko", "meeko"),
    ("vina", "vina"),
    ("Bio", "Bio"),
    ("numpy", "numpy"),
]
failed=[]
print(f"platform={platform.platform()}")
print(f"machine={platform.machine()}")
print(f"python={sys.version.split()[0]}")
for label,mod in checks:
    try:
        m=importlib.import_module(mod)
        v=getattr(m,"__version__","unknown")
        print(f"PASS {label} {v}")
    except Exception as e:
        failed.append(f"{label}: {type(e).__name__}: {e}")
        print(f"FAIL {label}: {e}")
for exe in ("vina","mk_prepare_ligand.py","mk_prepare_receptor.py","obabel"):
    p=shutil.which(exe)
    print(("PASS" if p else "WARNING")+f" executable {exe}: {p or 'not on PATH'}")
if failed:
    print("DOCKING_SKILL_RUNTIME_FAIL")
    raise SystemExit(1)
print("DOCKING_SKILL_RUNTIME_PASS")
