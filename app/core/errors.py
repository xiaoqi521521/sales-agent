from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """处理HTTP异常，返回统一格式的错误响应"""
        return error_response(
            status_code=exc.status_code,
            code=_code_for_status(exc.status_code),
            message=_message_from_detail(exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        """处理请求参数校验异常，返回422错误"""
        return error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message="请求参数校验失败",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        """处理未预期的异常，返回500内部服务器错误"""
        return error_response(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="服务暂时不可用，请稍后重试",
        )


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
        headers=headers,
    )


def _code_for_status(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
    }.get(status_code, "INTERNAL_SERVER_ERROR" if status_code >= 500 else "BAD_REQUEST")


def _message_from_detail(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return "请求处理失败"
