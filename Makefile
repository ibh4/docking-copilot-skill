# DockingCopilot Skill Makefile
# 约定：所有目标均在项目根目录执行；Python 使用 dockskill conda 环境
# （先 `conda activate dockskill`，或 `mamba run -n dockskill make <target>`）。

# 已激活 dockskill 环境时直接用 python；否则回退到 conda run。
# 可用 `make test PYTHON=...` 显式覆盖。
ifeq ($(CONDA_DEFAULT_ENV),dockskill)
PYTHON ?= python
else
PYTHON ?= conda run -n dockskill python
endif
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
# backend/app 内部使用 `from app...` 绝对导入，需把 backend/ 加入 PYTHONPATH
export PYTHONPATH := $(CURDIR)/backend$(if $(PYTHONPATH),:$(PYTHONPATH),)

.PHONY: check example test schemas dag failure-cases reproducibility backend frontend dev web clean

## check: 运行环境自检，成功时输出唯一标记 DOCKING_SKILL_CHECK_PASS
check:
	$(PYTHON) scripts/check_environment.py

## example: 运行可复现示例（占位，后续任务实现完整对接闭环）
example:
	$(PYTHON) scripts/run_example.py

## test: 运行后端测试
test:
	$(PYTHON) -m pytest backend/tests

## schemas: 重新导出 JSON Schema（与 backend/app/schemas.py 保持同步）
schemas:
	$(PYTHON) scripts/generate_schemas.py

## dag: 生成工作流 DAG（dags/workflow.mmd / workflow.json / workflow.svg）
dag:
	$(PYTHON) scripts/generate_dag.py

## failure-cases: 再生成 examples/failure_cases/ 全部失败案例
failure-cases:
	$(PYTHON) scripts/generate_failure_cases.py

## reproducibility: 双跑可复现性验证，产出 reports/reproducibility_report.{md,json}
reproducibility:
	$(PYTHON) scripts/verify_reproducibility.py

## backend: 启动 FastAPI 后端（workers=1，16GB 内存约束；仅监听 127.0.0.1）
backend:
	$(PYTHON) -m uvicorn backend.app.main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --workers 1

## frontend: 启动前端开发服务器（前端工程由后续任务创建）
frontend:
	cd frontend && npm run dev

## dev: 同时给出后端与前端启动提示（分两个终端运行 make backend / make frontend）
dev:
	@echo "开发模式：请在两个终端分别运行 'make backend' 与 'make frontend'"

## web: 一键打开网页 Demo（幂等）——服务未启动则后台启动，随后自动打开浏览器；
##      无 GUI/headless 环境下 open 失败仅打印链接，不中断流程
web:
	bash scripts/open_demo.sh

## clean: 清理 Python 缓存（不删除 outputs/ 中的运行结果）
clean:
	find . -type d -name __pycache__ -not -path "./.git/*" -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -not -path "./.git/*" -delete
