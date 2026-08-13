"""DockingCopilot Skill 后端入口（FastAPI 应用，Phase 3a）。

- 单一后台守护线程串行消费任务队列（结构性并发 = 1，无 Redis/Celery/DB）；
- POST 端点只做校验 + 入队并立即返回 ``{"job_id", "state": "CREATED"}``；
- job 状态完全由 ``outputs/<job_id>/job.json`` 文件承载；
- 全局异常处理器把所有错误统一为 schemas/error.schema.json 形状
  （不泄漏堆栈，绝不吞错）；
- CORS 仅允许本机前端 dev server（5173）；默认只监听 127.0.0.1。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import (
    artifacts,
    comparison,
    docking,
    health,
    ligands,
    queue,
    receptors,
    schemas,
    version,
)
from app.api.deps import ApiError, structured_error_response
from app.schemas import ErrorCode, StructuredError
from app.services import box_service, ligand_service, receptor_service
from app.utils.files import PathTraversalError
from app.utils.security import SecurityError

logger = logging.getLogger("dockskill.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时拉起唯一后台守护线程（串行任务队列）。"""
    queue.start_worker()
    yield


app = FastAPI(
    title="DockingCopilot Skill",
    description=(
        "可复现的分子对接 Copilot Skill：本地 FastAPI 服务 + 串行任务队列。"
        "POST 端点入队后立即返回 job_id，用 GET /api/jobs/{job_id} 轮询；"
        "job 状态由 outputs/<job_id>/job.json 承载。"
    ),
    version=__version__,
    lifespan=lifespan,
)

# CORS：仅本机前端开发服务器
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(version.router)
app.include_router(schemas.router)
app.include_router(ligands.router)
app.include_router(receptors.router)
app.include_router(docking.router)
app.include_router(comparison.router)
app.include_router(artifacts.router)


@app.get(
    "/",
    tags=["health"],
    responses={
        200: {
            "description": "服务元信息",
            "content": {
                "application/json": {
                    "example": {
                        "name": "DockingCopilot Skill",
                        "version": "0.1.0",
                        "docs": "/docs",
                        "health": "/health",
                    }
                }
            },
        }
    },
)
def root() -> dict:
    return {
        "name": "DockingCopilot Skill",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# 全局异常处理器：统一 StructuredError 形状，不泄漏堆栈，绝不吞错
# ---------------------------------------------------------------------------


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError):
    logger.warning(
        "api error %s %s -> %d [%s] %s",
        request.method, request.url.path, exc.status_code,
        exc.error.error_code, exc.error.message,
    )
    return structured_error_response(exc.error, exc.status_code)


def _jsonable(value):
    """递归净化为可 JSON 序列化结构（ctx 中可能含异常对象）。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return structured_error_response(
        StructuredError(
            error_code=ErrorCode.INPUT_VALIDATION_FAILED,
            stage="validate_input",
            message="request body failed schema validation",
            details={"errors": _jsonable(exc.errors())},
            recoverable=True,
            suggested_actions=["see GET /api/schema/input for the input schema"],
        ),
        400,
    )


@app.exception_handler(SecurityError)
async def handle_security_error(request: Request, exc: SecurityError):
    status = 413 if "too large" in str(exc) else 400
    return structured_error_response(
        StructuredError(
            error_code=ErrorCode.INPUT_VALIDATION_FAILED,
            stage="validate_input",
            message=str(exc),
            recoverable=True,
            suggested_actions=["reduce upload size or batch size"],
        ),
        status,
    )


@app.exception_handler(PathTraversalError)
async def handle_path_traversal(request: Request, exc: PathTraversalError):
    return structured_error_response(
        StructuredError(
            error_code=ErrorCode.INPUT_VALIDATION_FAILED,
            stage="api",
            message=str(exc),
            suggested_actions=["use a path inside the allowed directory"],
        ),
        403,
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    code = ErrorCode.FILE_NOT_FOUND if exc.status_code == 404 else (
        ErrorCode.INPUT_VALIDATION_FAILED
    )
    return structured_error_response(
        StructuredError(
            error_code=code,
            stage="api",
            message=str(exc.detail),
        ),
        exc.status_code,
    )


async def handle_service_error(request: Request, exc: Exception):
    """服务层受控异常逃逸到 API 层时的兜底（正常路径已在端点内转换）。"""
    return structured_error_response(
        StructuredError(
            error_code=getattr(exc, "code", ErrorCode.INTERNAL_ERROR),
            stage="api",
            message=str(exc),
            details=getattr(exc, "details", None) or {},
            recoverable=bool(getattr(exc, "recoverable", False)),
            suggested_actions=getattr(exc, "suggested_actions", None) or [],
        ),
        400,
    )


app.add_exception_handler(ligand_service.LigandError, handle_service_error)
app.add_exception_handler(receptor_service.ReceptorError, handle_service_error)
app.add_exception_handler(box_service.BoxError, handle_service_error)


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    logger.exception(
        "unhandled error on %s %s", request.method, request.url.path
    )
    return structured_error_response(
        StructuredError(
            error_code=ErrorCode.INTERNAL_ERROR,
            stage="api",
            message="internal server error",
            details={"exception_type": type(exc).__name__},
            suggested_actions=["check backend logs for details"],
        ),
        500,
    )
