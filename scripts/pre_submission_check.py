#!/usr/bin/env python3
"""提交前一致性质检（Phase 4 / 提示词 10、12）。

核对项：
1. SKILL.md / README.md / SUBMISSION.md 引用的仓库相对路径均存在；
2. 文档中的 `make <target>` 命令均在 Makefile 中定义；
3. schemas/*.schema.json 与 backend/app/schemas.py 的 Pydantic 导出一致；
4. examples/failure_cases/ 目录与 backend/tests/test_failures.py 测试对应；
5. 敏感信息扫描（/Users/<name>、API key、token、密码）；
6. 大文件检查（>1MB 警告；node_modules / outputs 不入 git）；
7. repository_size：被跟踪文件总大小与 .git 体积（当前赛规 50MB 上限，
   阈值 45MB 留 5MB 余量），超限 FAIL。

输出 reports/pre_submission_check.json 与 reports/pre_submission_check.md；
退出码：0 = 无 FAIL（WARNING 允许），1 = 存在 FAIL。

用法：
    conda run -n dockskill python scripts/pre_submission_check.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"

results: list[dict] = []


def record(name: str, status: str, detail: str) -> None:
    results.append({"check": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")


# ---------------------------------------------------------------------------
# 待扫描文件集合（与提交内容一致：排除运行时/构建产物）
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache",
    "outputs", "dist", ".venv",
}
TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".yml", ".yaml", ".toml", ".txt", ".cff",
    ".mmd", ".ts", ".tsx", ".css", ".html", ".sh", ".cjs", ".svg",
    ".gitignore", ".example",
}


def submit_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PROJECT_ROOT.rglob("*")):
        rel_parts = set(path.relative_to(PROJECT_ROOT).parts)
        if rel_parts & EXCLUDE_DIRS:
            continue
        if path.is_file() and (
            path.suffix in TEXT_SUFFIXES or path.name in (".gitignore", ".env.example")
        ):
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# 1. 文档引用路径存在性
# ---------------------------------------------------------------------------

PATH_RE = re.compile(
    r"(?:^|\s|[`（(：:])([a-zA-Z][a-zA-Z0-9_./-]*\.(?:md|py|json|ipynb|svg|mmd|pdb|"
    r"pdbqt|cff|yml|toml|txt|tsx?|csv|zip|sdf|sh))"
)
BACKTICK_DIR_RE = re.compile(r"`([a-zA-Z][a-zA-Z0-9_./-]*/)`")

#: 仅校验以这些顶级目录/文件开头的仓库内路径（排除 job 目录内相对路径）
TOP_LEVEL = {
    "backend", "frontend", "scripts", "docs", "dags", "schemas",
    "examples", "notebooks", "reports", "outputs", "vendor",
    "skills", "README.md", "SUBMISSION.md", "Makefile",
    "environment.yml", "requirements.txt", "pyproject.toml",
    "CITATION.cff", "LICENSE",
}


def check_doc_paths() -> None:
    missing: list[str] = []
    checked = 0
    for doc in ("skills/docking-copilot/SKILL.md", "README.md", "SUBMISSION.md"):
        doc_path = PROJECT_ROOT / doc
        if not doc_path.is_file():
            missing.append(f"{doc}: 文件不存在")
            continue
        text = doc_path.read_text(encoding="utf-8")
        candidates = set(PATH_RE.findall(text))
        candidates |= {m + "." for m in BACKTICK_DIR_RE.findall(text)}
        for cand in sorted(candidates):
            if cand.startswith(("http", "reports/pre_submission_check")):
                continue
            cand_clean = cand.rstrip(".")
            first = cand_clean.split("/", 1)[0]
            if first not in TOP_LEVEL:
                continue  # job 目录内相对路径（如 poses/<id>/pose_001.pdbqt）
            checked += 1
            if cand_clean.endswith("/"):
                if not (PROJECT_ROOT / cand_clean).is_dir():
                    missing.append(f"{doc}: 目录不存在 {cand_clean}")
            elif not (PROJECT_ROOT / cand_clean).exists():
                missing.append(f"{doc}: 路径不存在 {cand_clean}")
    if missing:
        record("文档路径存在性", FAIL, "; ".join(missing[:10]))
    else:
        record("文档路径存在性", PASS, f"SKILL/README/SUBMISSION 引用的 {checked} 个路径均存在")


# ---------------------------------------------------------------------------
# 2. Makefile 目标一致性
# ---------------------------------------------------------------------------

MAKE_CMD_RE = re.compile(r"make\s+([a-z][a-z0-9_-]*)\b")


def check_makefile_targets() -> None:
    makefile = PROJECT_ROOT / "Makefile"
    targets = {
        m.group(1)
        for line in makefile.read_text(encoding="utf-8").splitlines()
        if (m := re.match(r"^([a-z][a-z0-9_-]*):", line))
    }
    missing: list[str] = []
    for doc in ("skills/docking-copilot/SKILL.md", "README.md", "SUBMISSION.md"):
        path = PROJECT_ROOT / doc
        if not path.is_file():
            continue
        for target in set(MAKE_CMD_RE.findall(path.read_text(encoding="utf-8"))):
            if target not in targets:
                missing.append(f"{doc}: make {target} 未在 Makefile 定义")
    if missing:
        record("Makefile 目标一致性", FAIL, "; ".join(sorted(set(missing))))
    else:
        record(
            "Makefile 目标一致性", PASS,
            f"文档引用的 make 命令均在 Makefile 定义（目标: {', '.join(sorted(targets))}）",
        )


# ---------------------------------------------------------------------------
# 3. schemas/ 与 Pydantic 导出一致
# ---------------------------------------------------------------------------

def check_schemas() -> None:
    from app.schemas import (  # noqa: E402
        ComparisonOutput,
        DockingInput,
        DockingOutput,
        StructuredError,
    )

    exports = {
        "docking_input.schema.json": DockingInput,
        "docking_output.schema.json": DockingOutput,
        "comparison_output.schema.json": ComparisonOutput,
        "error.schema.json": StructuredError,
    }
    diffs: list[str] = []
    for filename, model in exports.items():
        path = PROJECT_ROOT / "schemas" / filename
        if not path.is_file():
            diffs.append(f"{filename} 缺失")
            continue
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        fresh = json.loads(json.dumps(model.model_json_schema()))
        if on_disk != fresh:
            diffs.append(f"{filename} 与 Pydantic 导出不一致")
    if diffs:
        record("schemas/ 与 Pydantic 一致", FAIL, "; ".join(diffs))
    else:
        record(
            "schemas/ 与 Pydantic 一致", PASS,
            f"{len(exports)} 个 JSON Schema 与 backend/app/schemas.py 导出完全一致",
        )


# ---------------------------------------------------------------------------
# 4. 失败案例目录与测试对应
# ---------------------------------------------------------------------------

def check_failure_cases() -> None:
    cases_dir = PROJECT_ROOT / "examples" / "failure_cases"
    cases = sorted(
        p.name for p in cases_dir.iterdir() if p.is_dir()
    )
    problems: list[str] = []
    for case in cases:
        for required in ("input.json", "expected.json"):
            if not (cases_dir / case / required).is_file():
                problems.append(f"{case} 缺 {required}")
    test_file = PROJECT_ROOT / "backend" / "tests" / "test_failures.py"
    test_names = re.findall(
        r"def (test_case_\w+)", test_file.read_text(encoding="utf-8")
    )
    if len(test_names) < len(cases):
        problems.append(
            f"测试数 {len(test_names)} < 案例目录数 {len(cases)}"
        )
    if problems:
        record("失败案例与测试对应", FAIL, "; ".join(problems))
    else:
        record(
            "失败案例与测试对应", PASS,
            f"{len(cases)} 个案例目录均含 input.json/expected.json，"
            f"test_failures.py 含 {len(test_names)} 个 test_case_* 测试",
        )


# ---------------------------------------------------------------------------
# 5. 敏感信息扫描
# ---------------------------------------------------------------------------

SENSITIVE_PATTERNS = [
    (re.compile(r"/Users/[A-Za-z0-9_.\-]+"), "macOS 用户绝对路径"),
    (re.compile(r"sk-[A-Za-z0-9]{16,}"), "疑似 OpenAI API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "疑似 GitHub token"),
    (re.compile(r"(?i)\b(api[_-]?key|token|password|passwd)\b\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
     "疑似硬编码凭据"),
]
ALLOWED = {".env.example"}


def check_secrets(files: list[Path]) -> None:
    hits: list[str] = []
    for path in files:
        if path.name in ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in SENSITIVE_PATTERNS:
            for m in pattern.finditer(text):
                rel = path.relative_to(PROJECT_ROOT)
                line_no = text.count("\n", 0, m.start()) + 1
                # 命中片段脱敏，避免质检报告自身二次携带敏感内容
                snippet = re.sub(r"/Users/[A-Za-z0-9_.\-]+", "/Users/<masked>", m.group(0))
                snippet = re.sub(r"(?i)(key|token|password)\b.{4,}", r"\1=<masked>", snippet)
                hits.append(f"{rel}:{line_no} [{label}] {snippet[:40]!r}")
    if hits:
        record("敏感信息扫描", FAIL, "; ".join(hits[:10]))
    else:
        record(
            "敏感信息扫描", PASS,
            f"扫描 {len(files)} 个提交文件，未发现 /Users 路径、API key、token、密码",
        )


# ---------------------------------------------------------------------------
# 6. 大文件与 gitignore
# ---------------------------------------------------------------------------

def check_large_files(files: list[Path]) -> None:
    big: list[str] = []
    for path in files:
        size = path.stat().st_size
        if size > 1024 * 1024:
            big.append(f"{path.relative_to(PROJECT_ROOT)} ({size / 1024 / 1024:.1f} MB)")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    ignore_problems = [
        name for name, pattern in (
            ("node_modules", "node_modules/"), ("outputs", "outputs/*"),
        )
        if pattern not in gitignore
    ]
    if ignore_problems:
        record("大文件/产物隔离", FAIL, f".gitignore 未排除: {ignore_problems}")
    elif big:
        record("大文件/产物隔离", WARNING, f">1MB 提交文件: {big}")
    else:
        record(
            "大文件/产物隔离", PASS,
            "提交文件均 ≤1MB；node_modules/ 与 outputs/ 已在 .gitignore 排除",
        )


# ---------------------------------------------------------------------------
# 7. 仓库体积检查（当前赛规：提交包 ≤50MB，单文件 ≤10MB）
# ---------------------------------------------------------------------------

#: 阈值 45MB = 50MB 上限留 5MB 余量
REPO_SIZE_LIMIT_MB: int = 50
REPO_SIZE_THRESHOLD_MB: int = 45


def _tracked_bytes() -> tuple[int, int] | None:
    """统计 git 被跟踪文件的个数与总字节数；非 git 仓库或 git 不可用返回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files", "-z"],
            capture_output=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    total, count = 0, 0
    for rel in out.decode("utf-8", "replace").split("\x00"):
        if not rel:
            continue
        p = PROJECT_ROOT / rel
        if p.is_file():
            total += p.stat().st_size
            count += 1
    return count, total


def _git_dir_bytes() -> int | None:
    """统计 .git 目录实际占用字节数（含 loose 对象与 pack）。"""
    git_dir = PROJECT_ROOT / ".git"
    if not git_dir.is_dir():
        return None
    return sum(p.stat().st_size for p in git_dir.rglob("*") if p.is_file())


def check_repository_size() -> None:
    tracked = _tracked_bytes()
    git_bytes = _git_dir_bytes()
    if tracked is None or git_bytes is None:
        record("repository_size", WARNING, "无法统计（非 git 仓库或 git 不可用）")
        return
    count, tracked_bytes = tracked
    tracked_mb = tracked_bytes / 1024 / 1024
    git_mb = git_bytes / 1024 / 1024
    threshold = REPO_SIZE_THRESHOLD_MB * 1024 * 1024
    detail = (
        f"被跟踪文件 {count} 个共 {tracked_mb:.2f} MB；.git 体积 {git_mb:.2f} MB；"
        f"阈值 {REPO_SIZE_THRESHOLD_MB} MB（赛规上限 {REPO_SIZE_LIMIT_MB} MB 留 "
        f"{REPO_SIZE_LIMIT_MB - REPO_SIZE_THRESHOLD_MB} MB 余量）"
    )
    if tracked_bytes > threshold or git_bytes > threshold:
        record("repository_size", FAIL, detail)
    else:
        record("repository_size", PASS, detail)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    files = submit_files()
    check_doc_paths()
    check_makefile_targets()
    check_schemas()
    check_failure_cases()
    check_secrets(files)
    check_large_files(files)
    check_repository_size()

    counts = {s: sum(1 for r in results if r["status"] == s) for s in (PASS, WARNING, FAIL)}
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
        "verdict": "SUBMIT" if counts[FAIL] == 0 else "BLOCKED",
        "checks": results,
    }

    reports = PROJECT_ROOT / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "pre_submission_check.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# 提交前质检报告（pre_submission_check）",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 结果: PASS {counts[PASS]} / WARNING {counts[WARNING]} / FAIL {counts[FAIL]}",
        f"- 结论: {'可以提交' if counts[FAIL] == 0 else '存在 FAIL，需修复'}",
        "",
        "| 检查 | 状态 | 详情 |",
        "| --- | --- | --- |",
    ]
    for r in results:
        lines.append(f"| {r['check']} | {r['status']} | {r['detail']} |")
    lines.append("")
    (reports / "pre_submission_check.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(f"\n汇总: PASS {counts[PASS]} / WARNING {counts[WARNING]} / FAIL {counts[FAIL]}")
    if counts[FAIL] == 0:
        print("PRE_SUBMISSION_CHECK_PASS")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
