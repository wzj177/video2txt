"""
全局异常处理中间件
统一API响应格式
"""

import logging
import traceback
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable


class GlobalExceptionHandler(BaseHTTPMiddleware):
    """全局异常处理中间件"""

    def __init__(self, app, debug: bool = False):
        super().__init__(app)
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next: Callable):
        try:
            response = await call_next(request)
            return response
        except HTTPException as exc:
            # FastAPI HTTPException - 保持原有的错误码
            return self._create_error_response(
                status_code=exc.status_code,
                message=exc.detail,
                error_type="HTTPException",
            )
        except ValueError as exc:
            # 参数错误
            self.logger.error(f"参数错误: {exc}")
            return self._create_error_response(
                status_code=400, message=str(exc), error_type="ValueError"
            )
        except TypeError as exc:
            # 类型错误 (通常是异步函数调用问题)
            self.logger.error(f"类型错误: {exc}")
            if "'coroutine' object is not subscriptable" in str(exc):
                return self._create_error_response(
                    status_code=500,
                    message="服务内部处理错误，请稍后重试",
                    error_type="AsyncError",
                )
            return self._create_error_response(
                status_code=500, message="服务内部错误", error_type="TypeError"
            )
        except Exception as exc:
            # 其他未捕获的异常
            self.logger.error(f"未处理异常: {exc}")
            if self.debug:
                self.logger.error(f"异常详情: {traceback.format_exc()}")

            return self._create_error_response(
                status_code=500,
                message="服务内部错误",
                error_type=type(exc).__name__,
                debug_info=str(exc) if self.debug else None,
            )

    def _create_error_response(
        self,
        status_code: int,
        message: str,
        error_type: str = "Error",
        debug_info: str = None,
    ) -> JSONResponse:
        """创建统一的错误响应"""
        error_response = {
            "success": False,
            "message": message,
            "error": {"type": error_type, "code": status_code},
            "data": None,
        }

        if debug_info:
            error_response["error"]["debug"] = debug_info

        return JSONResponse(status_code=status_code, content=error_response)


def create_success_response(data=None, message: str = "操作成功"):
    """创建统一的成功响应"""
    return {"success": True, "message": message, "data": data, "error": None}


def create_error_response(
    message: str, status_code: int = 400, error_type: str = "Error"
):
    """创建统一的错误响应"""
    return {
        "success": False,
        "message": message,
        "error": {"type": error_type, "code": status_code},
        "data": None,
    }
