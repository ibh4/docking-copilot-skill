#!/usr/bin/env python3
"""Validate the official GitHub submission layout for DockingCopilot.

This script intentionally checks the four organizer reminders:
1) repository root contains skills/<skill-name>/SKILL.md;
2) SKILL.md frontmatter contains name + description;
3) skill directory name equals frontmatter name;
4) skills/ contains exactly one skill directory.

When executed inside a real Git clone, it also verifies that the detected project
root is the Git repository root so an accidental wrapper directory such as
repo/docking-copilot-skill/skills/... is rejected.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
skills = root / "skills"
errs: list[str] = []
warns: list[str] = []

# GitHub path must be repository-root/skills/...
try:
    git_root_raw = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    git_root = Path(git_root_raw).resolve()
    if git_root != root.resolve():
        errs.append(
            "skills/ is nested below the Git repository root: "
            f"git root={git_root}, detected project root={root.resolve()}. "
            "Move skills/ directly to the GitHub repository root."
        )
except Exception:
    warns.append("Git repository root could not be detected; run this check again after git init/clone.")

# There must be exactly one skill.
dirs = [p for p in skills.iterdir() if p.is_dir() and not p.name.startswith(".")] if skills.is_dir() else []
if len(dirs) != 1:
    errs.append(f"skills/ must contain exactly one skill directory, found {len(dirs)}")

skill_dir = dirs[0] if len(dirs) == 1 else None
skill_file = skill_dir / "SKILL.md" if skill_dir else None
if not skill_file or not skill_file.is_file():
    errs.append("missing repository-root/skills/<skill-name>/SKILL.md")
else:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        errs.append("SKILL.md must start with YAML frontmatter delimiter '---'")

    # Restrict parsing to the first frontmatter block.
    frontmatter = ""
    if lines and lines[0].strip() == "---":
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
            frontmatter = "\n".join(lines[1:end])
        except StopIteration:
            errs.append("SKILL.md frontmatter has no closing '---'")

    m = re.search(r"^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$", frontmatter, re.M)
    if not m:
        errs.append("SKILL.md frontmatter is missing name")
        skill_name = None
    else:
        skill_name = m.group(1).strip()
        if not re.fullmatch(r"[a-z0-9-]{1,64}", skill_name):
            errs.append(f"invalid frontmatter name: {skill_name!r}")

    d = re.search(r"^description:\s*['\"]?(.*?)['\"]?\s*$", frontmatter, re.M)
    if not d or not d.group(1).strip():
        errs.append("SKILL.md frontmatter is missing description")
    elif len(d.group(1).strip()) > 1024:
        errs.append(f"description is too long: {len(d.group(1).strip())} characters")

    # Organizer reminder #4: path skill-name == frontmatter name.
    if skill_name and skill_dir and skill_dir.name != skill_name:
        errs.append(
            f"skill-name mismatch: directory is skills/{skill_dir.name}/ but frontmatter name is {skill_name!r}"
        )

    if len(lines) >= 500:
        errs.append(f"SKILL.md has {len(lines)} lines; recommended <500")

# requirements.txt is optional officially, but required by this implementation.
req = root / "requirements.txt"
if not req.is_file():
    errs.append("missing root requirements.txt required by this implementation")

# File/package limits, excluding runtime/build directories.
exclude = {".git", "node_modules", "outputs", "__pycache__", ".pytest_cache", "dist", ".venv"}
total = 0
for p in root.rglob("*"):
    if not p.is_file() or set(p.relative_to(root).parts) & exclude:
        continue
    s = p.stat().st_size
    total += s
    if s > 10 * 1024 * 1024:
        errs.append(f"file >10MB: {p.relative_to(root)} ({s/1024/1024:.2f}MB)")
if total > 50 * 1024 * 1024:
    errs.append(f"package >50MB: {total/1024/1024:.2f}MB")

for w in warns:
    print("WARNING", w)

if errs:
    for e in errs:
        print("FAIL", e)
    print("OFFICIAL_SUBMISSION_CHECK_FAIL")
    sys.exit(1)

assert skill_dir is not None and skill_file is not None
print(f"PASS GitHub repository root: {root}")
print(f"PASS exact Skill path: skills/{skill_dir.name}/SKILL.md")
print(f"PASS skill-name matches frontmatter name: {skill_dir.name}")
print("PASS frontmatter contains name + description")
print(f"PASS skills/ contains exactly one skill: {skill_dir.name}")
print(f"PASS SKILL lines: {len(skill_file.read_text(encoding='utf-8').splitlines())}")
print(f"PASS package size: {total/1024/1024:.2f} MB")
print("OFFICIAL_SUBMISSION_CHECK_PASS")
