#!/usr/bin/env python3
"""DockingCopilot Skill 环境自检。

检查 arm64 / Python / RDKit / Vina / Meeko / Open Babel / FastAPI /
Jupyter / Node / npm / 磁盘可写 / 目录可创建，输出 PASS / WARNING / FAIL：

- 机器可读：reports/environment_check.json
- 人类可读：reports/environment_check.md

退出码：0 = 无 FAIL（打印唯一标记 DOCKING_SKILL_CHECK_PASS）；1 = 存在 FAIL。
规则：Vina Python API 缺失但 CLI 可用时记 WARNING 而非 FAIL。
"""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
VENDOR_VINA = PROJECT_ROOT / "vendor" / "bin" / "vina"

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"

results: list[dict] = []


def record(name: str, status: str, detail: str) -> None:
    results.append({"component": name, "status": status, "detail": detail})
    print(f"[{status}] {name}: {detail}")


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s"


def check_arch() -> None:
    machine = platform.machine()
    if machine == "arm64":
        record("arm64", PASS, f"platform.machine()={machine}")
    else:
        record("arm64", FAIL, f"platform.machine()={machine}，期望 arm64")


def check_python() -> None:
    ver = sys.version_info
    if ver.major == 3 and ver.minor == 11:
        record("Python", PASS, f"{platform.python_version()} ({sys.executable})")
    else:
        record(
            "Python",
            WARNING,
            f"{platform.python_version()}，建议 3.11 ({sys.executable})",
        )


def check_rdkit() -> None:
    try:
        from rdkit import Chem
        from rdkit import __version__ as ver

        mol = Chem.MolFromSmiles("CCO")
        if mol is None:
            record("RDKit", FAIL, f"rdkit {ver}: 无法解析 CCO")
            return
        record("RDKit", PASS, f"rdkit {ver}，可解析 SMILES")
    except Exception as exc:  # noqa: BLE001
        record("RDKit", FAIL, f"import/解析失败: {exc}")


def _find_vina() -> str | None:
    explicit = os.environ.get("DOCKSKILL_VINA_EXECUTABLE")
    if explicit and Path(explicit).is_file():
        return explicit
    on_path = shutil.which("vina")
    if on_path:
        return on_path
    if VENDOR_VINA.is_file() and os.access(VENDOR_VINA, os.X_OK):
        return str(VENDOR_VINA)
    return None


def check_vina() -> None:
    cli_path = _find_vina()
    cli_ver = None
    if cli_path:
        rc, out = run_cmd([cli_path, "--version"])
        if rc == 0 and out:
            cli_ver = out.splitlines()[0].strip()
    api_ok = False
    api_err = ""
    try:
        mod = importlib.import_module("vina")
        getattr(mod, "Vina")
        api_ok = True
    except Exception as exc:  # noqa: BLE001
        api_err = str(exc)

    if cli_ver and api_ok:
        record("Vina", PASS, f"CLI: {cli_ver} ({cli_path}); Python API 可用")
    elif cli_ver:
        record(
            "Vina",
            WARNING,
            f"CLI 可用: {cli_ver} ({cli_path}); Python API 缺失 ({api_err})",
        )
    elif api_ok:
        record("Vina", WARNING, "Python API 可用，但 CLI 可执行文件未找到")
    else:
        record("Vina", FAIL, f"CLI 与 Python API 均不可用 ({api_err})")


def check_meeko() -> None:
    cli = shutil.which("mk_prepare_ligand.py") or shutil.which("mk_prepare_ligand")
    try:
        import meeko

        ver = getattr(meeko, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        record("Meeko", FAIL, f"import meeko 失败: {exc}")
        return
    if cli:
        record("Meeko", PASS, f"meeko {ver}; CLI: {cli}")
    else:
        record("Meeko", WARNING, f"meeko {ver} 可导入，但 mk_prepare_ligand CLI 不在 PATH")


def check_openbabel() -> None:
    rc, out = run_cmd(["obabel", "-V"])
    if rc == 0 and out:
        record("OpenBabel", PASS, out.strip())
        return
    try:
        from openbabel import openbabel as ob  # type: ignore

        record("OpenBabel", WARNING, f"obabel CLI 缺失，但 Python bindings 可用 ({ob.OBRelease.GetVersion()})")
    except Exception:  # noqa: BLE001
        record("OpenBabel", FAIL, f"obabel CLI 与 Python bindings 均不可用: {out}")


def check_fastapi() -> None:
    try:
        import fastapi
        import uvicorn  # noqa: F401

        record("FastAPI", PASS, f"fastapi {fastapi.__version__}")
    except Exception as exc:  # noqa: BLE001
        record("FastAPI", FAIL, f"import 失败: {exc}")


def check_jupyter() -> None:
    try:
        import ipykernel  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        record("Jupyter", FAIL, f"ipykernel 不可用: {exc}")
        return
    rc, out = run_cmd([sys.executable, "-m", "jupyter", "kernelspec", "list"])
    if rc == 0 and "dockskill" in out:
        record("Jupyter", PASS, "kernelspec 'dockskill' 已注册")
    else:
        record(
            "Jupyter",
            WARNING,
            "ipykernel 可用，但未注册 'dockskill' kernel"
            "（运行: python -m ipykernel install --user --name dockskill）",
        )


def check_node() -> None:
    rc, out = run_cmd(["node", "--version"])
    if rc == 0:
        record("Node", PASS, out.strip())
    else:
        record("Node", FAIL, out)


def check_npm() -> None:
    rc, out = run_cmd(["npm", "--version"])
    if rc == 0:
        record("npm", PASS, f"npm {out.strip()}")
    else:
        record("npm", FAIL, out)


def check_disk_writable() -> None:
    outputs = PROJECT_ROOT / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    try:
        fd, path = tempfile.mkstemp(dir=outputs, prefix=".check_")
        os.write(fd, b"ok")
        os.close(fd)
        os.unlink(path)
        record("磁盘可写", PASS, f"outputs/ 可写（仓库内相对路径：outputs）")
    except Exception as exc:  # noqa: BLE001
        record("磁盘可写", FAIL, f"outputs/ 写入失败: {exc}")


def check_dir_creatable() -> None:
    targets = [
        PROJECT_ROOT / "outputs",
        PROJECT_ROOT / "reports",
    ]
    try:
        tmp = PROJECT_ROOT / "outputs" / ".check_dir_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "probe.txt").write_text("ok")
        shutil.rmtree(tmp)
        record(
            "目录可创建",
            PASS,
            "可在 outputs/ 下创建并删除 job 子目录（"
            + ", ".join(str(t.relative_to(PROJECT_ROOT)) for t in targets)
            + " 存在）",
        )
    except Exception as exc:  # noqa: BLE001
        record("目录可创建", FAIL, f"创建/清理临时目录失败: {exc}")


def main() -> int:
    check_arch()
    check_python()
    check_rdkit()
    check_vina()
    check_meeko()
    check_openbabel()
    check_fastapi()
    check_jupyter()
    check_node()
    check_npm()
    check_disk_writable()
    check_dir_creatable()

    counts = {s: sum(1 for r in results if r["status"] == s) for s in (PASS, WARNING, FAIL)}
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "counts": counts,
        "checks": results,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "environment_check.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# 环境自检报告",
        "",
        f"- 生成时间: {summary['generated_at']}",
        f"- 平台: {summary['platform']}",
        f"- Python: {summary['python']}",
        f"- 结果: PASS {counts[PASS]} / WARNING {counts[WARNING]} / FAIL {counts[FAIL]}",
        "",
        "| 组件 | 状态 | 详情 |",
        "| --- | --- | --- |",
    ]
    for r in results:
        lines.append(f"| {r['component']} | {r['status']} | {r['detail']} |")
    lines.append("")
    (REPORTS_DIR / "environment_check.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(
        f"\n汇总: PASS {counts[PASS]} / WARNING {counts[WARNING]} / FAIL {counts[FAIL]}"
    )
    print(f"报告: {REPORTS_DIR / 'environment_check.json'}")
    print(f"报告: {REPORTS_DIR / 'environment_check.md'}")

    if counts[FAIL] == 0:
        print("DOCKING_SKILL_CHECK_PASS")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
