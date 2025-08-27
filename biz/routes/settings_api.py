#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI听世界 - 设置API路由
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import json
import os
import requests
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 创建设置API路由器
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])

# 配置文件路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "settings.json"


def load_settings() -> Dict[str, Any]:
    """加载设置配置"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            # 默认配置
            return {
                "openai": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-3.5-turbo",
                    "max_tokens": 2000,
                },
                "ollama": {
                    "installed": False,
                    "base_url": "http://localhost:11434",
                    "models": [],
                },
                "system": {
                    "default_language": "zh",
                    "storage_path": str(PROJECT_ROOT / "data" / "outputs"),
                    "max_concurrent": 3,
                },
            }
    except Exception as e:
        logger.error(f"加载设置失败: {e}")
        return {}


def save_settings(settings: Dict[str, Any]) -> bool:
    """保存设置配置"""
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        return False


@settings_router.get("/openai")
async def get_openai_settings() -> Dict[str, Any]:
    """获取OpenAI配置"""
    try:
        settings = load_settings()
        openai_config = settings.get("openai", {})

        # 隐藏API密钥的敏感信息
        # if openai_config.get("api_key"):
        #     openai_config["api_key"] = "sk-" + "*" * 20 + openai_config["api_key"][-8:]

        return {"success": True, "data": openai_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/openai")
async def update_openai_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新OpenAI配置"""
    try:
        settings = load_settings()

        # 更新OpenAI配置
        if "openai" not in settings:
            settings["openai"] = {}

        # 只更新提供的字段
        for key, value in config.items():
            if key in ["api_key", "base_url", "model", "max_tokens"]:
                settings["openai"][key] = value

        if save_settings(settings):
            return {"success": True, "message": "OpenAI配置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@settings_router.post("/openai/test")
async def test_openai_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """测试OpenAI连接"""
    try:
        api_key = config.get("api_key", "")
        base_url = config.get("base_url", "https://api.openai.com/v1")
        model = config.get("model", "gpt-3.5-turbo")

        if not api_key:
            return {"success": False, "error": "API密钥不能为空"}

        # 测试API连接
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        test_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
            ],
            "max_tokens": config.get("max_tokens", 2000),
        }

        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=test_data,
            timeout=10,
        )

        if response.status_code == 200:
            return {"success": True, "message": "连接成功"}
        else:
            error_msg = f"连接失败: {response.status_code}"
            try:
                error_detail = response.json().get("error", {}).get("message", "")
                if error_detail:
                    error_msg += f" - {error_detail}"
            except:
                pass
            return {"success": False, "error": error_msg}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "连接超时"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "无法连接到服务器"}
    except Exception as e:
        return {"success": False, "error": f"测试失败: {str(e)}"}


@settings_router.get("/ollama")
async def get_ollama_settings() -> Dict[str, Any]:
    """获取Ollama配置"""
    try:
        settings = load_settings()
        ollama_config = settings.get("ollama", {})

        return {"success": True, "data": ollama_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/ollama/detect")
async def detect_ollama() -> Dict[str, Any]:
    """检测Ollama安装状态"""
    try:
        # 检查Ollama是否安装
        try:
            result = subprocess.run(
                ["ollama", "--version"], capture_output=True, text=True, timeout=5
            )
            installed = result.returncode == 0
            version = result.stdout.strip() if installed else ""
        except (subprocess.TimeoutExpired, FileNotFoundError):
            installed = False
            version = ""

        # 检查Ollama服务是否运行
        running = False
        models = []

        if installed:
            try:
                # 尝试连接Ollama API
                response = requests.get("http://localhost:11434/api/tags", timeout=5)
                if response.status_code == 200:
                    running = True
                    data = response.json()
                    models = [model["name"] for model in data.get("models", [])]
            except:
                pass

        # 更新配置
        settings = load_settings()
        settings["ollama"] = {
            "installed": installed,
            "version": version,
            "running": running,
            "base_url": "http://localhost:11434",
            "models": models,
        }
        save_settings(settings)

        return {
            "success": True,
            "data": {
                "installed": installed,
                "version": version,
                "running": running,
                "models": models,
                "model_count": len(models),
            },
        }

    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.get("/system")
async def get_system_settings() -> Dict[str, Any]:
    """获取系统设置"""
    try:
        settings = load_settings()
        system_config = settings.get("system", {})

        return {"success": True, "data": system_config}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}


@settings_router.post("/system")
async def update_system_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """更新系统设置"""
    try:
        settings = load_settings()

        # 更新系统配置
        if "system" not in settings:
            settings["system"] = {}

        # 只更新提供的字段
        for key, value in config.items():
            if key in ["default_language", "storage_path", "max_concurrent"]:
                settings["system"][key] = value

        # 验证存储路径
        if "storage_path" in config:
            storage_path = Path(config["storage_path"])
            try:
                storage_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {"success": False, "error": f"无效的存储路径: {str(e)}"}

        if save_settings(settings):
            return {"success": True, "message": "系统设置已更新"}
        else:
            return {"success": False, "error": "保存配置失败"}

    except Exception as e:
        return {"success": False, "error": str(e)}


@settings_router.get("/all")
async def get_all_settings() -> Dict[str, Any]:
    """获取所有设置"""
    try:
        settings = load_settings()

        # 隐藏敏感信息
        # if settings.get("openai", {}).get("api_key"):
        #     api_key = settings["openai"]["api_key"]
        #     settings["openai"]["api_key"] = "sk-" + "*" * 20 + api_key[-8:]

        return {"success": True, "data": settings}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}
