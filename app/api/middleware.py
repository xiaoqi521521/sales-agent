"""HTTP 中间件模块

提供请求追踪、日志记录等跨切面功能的 FastAPI 中间件。
"""
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request

from app.core.logging import format_kv, get_logger
from app.core.request_context import reset_trace_id, set_trace_id


logger = get_logger("sales_agent.api")
REQUEST_LOG_SEPARATOR = "=" * 80


def register_trace_middleware(app: FastAPI) -> None:
    """注册请求追踪中间件到 FastAPI 应用
    
    该中间件为每个 HTTP 请求生成或提取追踪 ID（trace_id），并将其注入到：
    - 请求上下文（通过 contextvars）
    - 响应头（X-Trace-Id）
    - 日志输出（所有相关日志自动携带 trace_id）
    
    同时记录请求的开始时间、结束时间和执行时长，用于性能监控和故障排查。
    
    Args:
        app: FastAPI 应用实例，中间件将注册到此应用
    """
    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        """追踪中间件核心逻辑
        
        工作流程：
        1. 从请求头提取或生成新的 trace_id
        2. 将 trace_id 设置到请求上下文
        3. 记录请求开始日志
        4. 调用后续处理链（路由处理器等）
        5. 捕获异常并记录失败日志
        6. 在响应头中注入 trace_id
        7. 记录请求完成日志
        
        Args:
            request: FastAPI 请求对象，包含请求方法、路径、头部等信息
            call_next: 下一个处理函数，调用它将执行后续的路由处理器和中间件
            
        Returns:
            response: HTTP 响应对象，将被添加 X-Trace-Id 头部
            
        Raises:
            Exception: 如果后续处理链抛出异常，会重新抛出该异常
        """
        # 从请求头获取客户端提供的 trace_id，若不存在则生成新的 UUID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid4())
        
        # 将 trace_id 设置到当前协程的上下文中，返回 token 用于后续清理
        # 这样后续的日志记录会自动携带此 trace_id
        token = set_trace_id(trace_id)
        
        # 记录请求开始的高精度时间戳（秒）
        started_at = perf_counter()
        
        # 记录请求开始的日志，包含 HTTP 方法和请求路径
        logger.info(REQUEST_LOG_SEPARATOR)
        logger.info(
            format_kv(
                "http_request_started",
                method=request.method,
                path=request.url.path,
            )
        )
        
        try:
            # 调用后续处理链，执行实际的路由处理器和业务逻辑
            response = await call_next(request)
        except Exception:
            # 如果处理过程中发生异常，计算耗时并记录失败日志
            duration_ms = int((perf_counter() - started_at) * 1000)
            logger.exception(
                format_kv(
                    "http_request_failed",
                    method=request.method,
                    path=request.url.path,
                    durationMs=duration_ms,
                )
            )
            # 重新抛出异常，让 FastAPI 的全局异常处理器处理
            raise
        finally:
            # 无论是否发生异常，都要清理请求上下文中的 trace_id
            # 防止协程复用时出现 trace_id 污染
            reset_trace_id(token)

        # 在响应头中注入 trace_id，方便客户端和服务端链路追踪
        response.headers["X-Trace-Id"] = trace_id
        
        # 计算请求总耗时（毫秒）
        duration_ms = int((perf_counter() - started_at) * 1000)
        
        # 再次设置 trace_id 到上下文（因为 finally 中已清理）
        # 这是为了确保日志记录时能正确携带 trace_id
        scoped_token = set_trace_id(trace_id)
        
        try:
            # 记录请求完成的日志，包含状态码和耗时
            logger.info(
                format_kv(
                    "http_request_completed",
                    method=request.method,
                    path=request.url.path,
                    statusCode=response.status_code,
                    durationMs=duration_ms,
                )
            )
        finally:
            # 清理第二次设置的 trace_id 上下文
            reset_trace_id(scoped_token)
        
        return response
