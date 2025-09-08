#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 系统API路由
"""

from fastapi import APIRouter
from typing import Dict, Any

from ..services.system_service import system_service

# 创建系统API路由器
system_router = APIRouter(prefix="/api/system", tags=["system"])


@system_router.get("/info")
async def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    try:
        info = system_service.get_system_info()
        return {"success": True, "data": info}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@system_router.get("/health")
async def health_check() -> Dict[str, Any]:
    """健康检查"""
    return {
        "success": True,
        "data": {"status": "healthy", "service": "听语AI", "version": "3.0.0"},
    }


@system_router.get("/version")
async def get_version() -> Dict[str, Any]:
    """获取版本信息"""
    return {
        "success": True,
        "data": {
            "version": "3.0.0",
            "build_date": "2025-08-21",
            "description": "听语AI - 智能语音文字转换系统",
        },
    }
