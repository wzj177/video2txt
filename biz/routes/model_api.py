#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 模型管理API路由
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List
import json
import os
import asyncio
import logging
from pathlib import Path
import requests
import hashlib
from datetime import datetime

from ..services.download_manager import download_manager

logger = logging.getLogger(__name__)

# 创建模型API路由器
model_router = APIRouter(prefix="/api/models", tags=["models"])

# 模型配置
MODEL_CONFIGS = {
    "whisper": {
        "tiny": {
            "name": "tiny",
            "size": "39MB",
            "description": "最小模型，速度快但精度较低，适合快速预览",
            "url": "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f83b26e78e39ff2a90c3a76f8e65c3c3c5/tiny.pt",
        },
        "small": {
            "name": "small",
            "size": "244MB",
            "description": "小型模型，平衡速度和精度，适合日常使用",
            "url": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b86c6e6d3c3c5/small.pt",
        },
        "medium": {
            "name": "medium",
            "size": "769MB",
            "description": "中型模型，更高精度，适合重要内容处理",
            "url": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c69d6c6c6e6d3c3c5e6d3c3c5e6d3c3c5/medium.pt",
        },
        "large": {
            "name": "large",
            "size": "1550MB",
            "description": "大型模型，最高精度，适合专业用途",
            "url": "https://openaipublic.azureedge.net/main/whisper/models/e4b87e7e0bf463eb8e6956e646f1e774b7dc2043e4b87e7e0bf463eb8e6956e6/large.pt",
        },
    },
    "faster_whisper": {
        "tiny": {
            "name": "faster-whisper-tiny",
            "size": "39MB",
            "description": "FasterWhisper最小模型，速度快5-10倍，适合实时处理",
            "model_type": "faster_whisper",
            "performance": "比标准Whisper快5-10倍，内存占用更低",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
        "small": {
            "name": "faster-whisper-small",
            "size": "244MB",
            "description": "FasterWhisper小型模型，平衡速度和精度，推荐日常使用",
            "model_type": "faster_whisper",
            "performance": "比标准Whisper快5-10倍，精度基本一致",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
        "medium": {
            "name": "faster-whisper-medium",
            "size": "769MB",
            "description": "FasterWhisper中型模型，更高精度，性能优异",
            "model_type": "faster_whisper",
            "performance": "比标准Whisper快5-10倍，适合高精度需求",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
        "large": {
            "name": "faster-whisper-large",
            "size": "1550MB",
            "description": "FasterWhisper大型模型，最高精度，企业级性能",
            "model_type": "faster_whisper",
            "performance": "比标准Whisper快5-10倍，最高精度",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
        "large-v2": {
            "name": "faster-whisper-large-v2",
            "size": "1550MB",
            "description": "FasterWhisper大型模型v2版本，改进的多语言支持",
            "model_type": "faster_whisper",
            "performance": "最新版本，改进了多语言识别精度",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别", "改进多语言"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
        "large-v3": {
            "name": "faster-whisper-large-v3",
            "size": "1550MB",
            "description": "FasterWhisper最新v3版本，最佳性能和精度",
            "model_type": "faster_whisper",
            "performance": "最新版本，显著改进的识别精度和鲁棒性",
            "features": ["GPU加速", "内存优化", "批处理支持", "流式识别", "最新优化"],
            "supported_devices": ["cpu", "cuda"],
            "compute_types": ["int8", "float16", "float32"],
            "install_guide": "需要安装faster-whisper: pip install faster-whisper",
        },
    },
    "sensevoice": {
        "small": {
            "name": "SenseVoice-Small",
            "size": "1.2GB",
            "description": "阿里达摩院快速语音理解模型，支持多语言识别、情感识别和事件检测",
            "repo": "iic/SenseVoiceSmall",
            "model_type": "funasr",  # 指定使用FunASR
            "languages": ["中文", "英语", "粤语", "日语", "韩语"],
            "features": ["ASR", "LID", "SER", "AED", "VAD"],
            "performance": "比Whisper-small快7倍，比Whisper-large快17倍",
            "install_guide": "需要安装FunASR: pip install funasr modelscope",
            "vad_support": True,  # 支持语音活动检测
            "trust_remote_code": True,  # 需要信任远程代码
            "supported_devices": ["cpu", "cuda:0"],  # 支持的设备
        }
    },
    "dolphin": {
        "base": {
            "name": "Dolphin-Base",
            "size": "400MB",
            "description": "基础方言识别模型，可达到Whisper large-v3的性能",
            "url": "https://github.com/DataoceanAI/Dolphin/releases/download/v1.0/base.pt",
            "local_path": "data/models/dolphin/base.pt",
            "performance": "基础模型，适合快速处理",
            "languages": [
                "中文及22个方言",
                "日语",
                "韩语",
                "泰语",
                "俄语",
                "阿拉伯语",
                "等36种语言",
            ],
            "dialect_support": "支持22个中文方言（四川话、上海话、广东话等）",
        },
        "small": {
            "name": "Dolphin-Small",
            "size": "800MB",
            "description": "小型方言识别模型，比base模型平均提升24.5% WER",
            "url": "https://github.com/DataoceanAI/Dolphin/releases/download/v1.0/small.pt",
            "local_path": "data/models/dolphin/small.pt",
            "performance": "推荐使用，性能与速度平衡",
            "languages": [
                "中文及22个方言",
                "日语",
                "韩语",
                "泰语",
                "俄语",
                "阿拉伯语",
                "等36种语言",
            ],
            "dialect_support": "支持22个中文方言（四川话、上海话、广东话等）",
        },
        "medium": {
            "name": "Dolphin-Medium",
            "size": "1.5GB",
            "description": "中型方言识别模型，比small模型额外提升8.3% WER",
            "url": "https://github.com/DataoceanAI/Dolphin/releases/download/v1.0/medium.pt",
            "local_path": "data/models/dolphin/medium.pt",
            "performance": "高精度，适合重要内容处理",
            "languages": [
                "中文及22个方言",
                "日语",
                "韩语",
                "泰语",
                "俄语",
                "阿拉伯语",
                "等36种语言",
            ],
            "dialect_support": "支持22个中文方言（四川话、上海话、广东话等）",
        },
        "large": {
            "name": "Dolphin-Large",
            "size": "3.0GB",
            "description": "大型方言识别模型，比medium模型额外提升6.5% WER，最高精度",
            "url": "https://github.com/DataoceanAI/Dolphin/releases/download/v1.0/large.pt",
            "local_path": "data/models/dolphin/large.pt",
            "performance": "最高精度，适合专业用途",
            "languages": [
                "中文及22个方言",
                "日语",
                "韩语",
                "泰语",
                "俄语",
                "阿拉伯语",
                "等36种语言",
            ],
            "dialect_support": "支持22个中文方言（四川话、上海话、广东话等）",
        },
    },
}


def get_model_storage_path() -> Path:
    """获取模型存储路径"""
    # 项目根目录下的data/models
    project_root = Path(__file__).parent.parent.parent
    models_path = project_root / "data" / "models"
    models_path.mkdir(parents=True, exist_ok=True)
    return models_path


def get_model_info(model_type: str, model_name: str) -> Dict[str, Any]:
    """获取模型信息"""
    if model_type not in MODEL_CONFIGS:
        return None

    if model_name not in MODEL_CONFIGS[model_type]:
        return None

    model_config = MODEL_CONFIGS[model_type][model_name].copy()

    # 添加配置键名，供前端API调用使用
    model_config["config_key"] = model_name

    # 检查模型是否已安装
    models_path = get_model_storage_path()

    if model_type == "whisper":
        # Whisper模型通常存储在用户目录下的.cache/whisper/
        import os

        whisper_cache = Path.home() / ".cache" / "whisper"
        model_file = whisper_cache / f"{model_name}.pt"
        model_config["installed"] = model_file.exists()
        model_config["local_path"] = str(model_file)

    elif model_type == "faster_whisper":
        # FasterWhisper模型检查 - 使用 Hugging Face 缓存
        try:
            from faster_whisper import WhisperModel

            # FasterWhisper 会自动管理模型下载和缓存
            # 检查是否可以加载模型（不实际加载，只检查）
            hf_cache = Path.home() / ".cache" / "huggingface"

            # 检查模型是否已缓存 - FasterWhisper使用Systran组织
            model_size_name = model_name.replace("faster-whisper-", "")
            possible_paths = [
                # FasterWhisper实际使用的路径（Systran组织）
                hf_cache / "hub" / f"models--Systran--faster-whisper-{model_size_name}",
                # 备选路径（以防将来变化）
                hf_cache
                / "transformers"
                / f"models--Systran--faster-whisper-{model_size_name}",
                hf_cache / "hub" / f"models--openai--whisper-{model_size_name}",
                hf_cache
                / "transformers"
                / f"models--openai--whisper-{model_size_name}",
            ]

            installed = False
            local_path = ""
            for path in possible_paths:
                if path.exists():
                    installed = True
                    local_path = str(path)
                    break

            # 如果缓存中没有，但faster-whisper包存在，标记为可安装
            if not installed:
                try:
                    import faster_whisper

                    model_config["can_download"] = True
                except ImportError:
                    model_config["can_download"] = False
                    model_config["error"] = "需要安装 faster-whisper 包"

            model_config["installed"] = installed
            model_config["local_path"] = local_path

        except ImportError:
            model_config["installed"] = False
            model_config["can_download"] = False
            model_config["error"] = (
                "需要安装 faster-whisper: pip install faster-whisper"
            )

    elif model_type == "sensevoice":
        # SenseVoice使用HuggingFace/ModelScope/FunASR缓存
        hf_cache = Path.home() / ".cache" / "huggingface" / "transformers"
        modelscope_cache = (
            Path.home()
            / ".cache"
            / "modelscope"
            / "hub"
            / "models"
            / "iic"
            / "SenseVoiceSmall"
        )
        funasr_cache = Path("./data/models/funasr_cache")

        # 检查是否存在
        installed = (
            (hf_cache.exists() and any(hf_cache.glob("*SenseVoice*")))
            or modelscope_cache.exists()
            or (funasr_cache.exists() and any(funasr_cache.glob("*SenseVoice*")))
        )
        model_config["installed"] = installed

    elif model_type == "dolphin":
        # Dolphin模型存储在项目目录
        model_file = models_path / "dolphin" / f"{model_name}.pt"
        model_config["installed"] = model_file.exists()
        model_config["local_path"] = str(model_file)

    return model_config


@model_router.get("")
async def list_models() -> Dict[str, Any]:
    """获取所有模型列表"""
    try:
        models = {"whisper": [], "faster_whisper": [], "sensevoice": [], "dolphin": []}

        for model_type in MODEL_CONFIGS:
            for model_name in MODEL_CONFIGS[model_type]:
                model_info = get_model_info(model_type, model_name)
                if model_info:
                    models[model_type].append(model_info)

        return {"success": True, "data": models}

    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        return {"success": False, "error": str(e), "data": {}}


@model_router.get("/{model_type}")
async def list_models_by_type(model_type: str) -> Dict[str, Any]:
    """获取指定类型的模型列表"""
    try:
        if model_type not in MODEL_CONFIGS:
            raise HTTPException(status_code=404, detail="模型类型不存在")

        models = []
        for model_name in MODEL_CONFIGS[model_type]:
            model_info = get_model_info(model_type, model_name)
            if model_info:
                models.append(model_info)

        return {"success": True, "data": models}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取{model_type}模型列表失败: {e}")
        return {"success": False, "error": str(e), "data": []}


@model_router.get("/{model_type}/{model_name}")
async def get_model_status(model_type: str, model_name: str) -> Dict[str, Any]:
    """获取特定模型状态"""
    try:
        model_info = get_model_info(model_type, model_name)
        if not model_info:
            raise HTTPException(status_code=404, detail="模型不存在")

        return {"success": True, "data": model_info}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型状态失败: {e}")
        return {"success": False, "error": str(e), "data": None}


@model_router.post("/{model_type}/{model_name}/download")
async def download_model(
    model_type: str, model_name: str, background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """下载模型"""
    try:
        model_info = get_model_info(model_type, model_name)
        if not model_info:
            raise HTTPException(status_code=404, detail="模型不存在")

        if model_info.get("installed", False):
            return {"success": False, "error": "模型已安装", "data": None}

        # 创建下载任务
        task_id = (
            f"download_{model_type}_{model_name}_{int(datetime.now().timestamp())}"
        )

        # 创建任务记录
        download_manager.create_task(
            task_id,
            {
                "status": "pending",
                "progress": 0,
                "current_step": "准备下载...",
                "model_type": model_type,
                "model_name": model_name,
                "model_info": model_info,
            },
        )

        # 添加后台下载任务
        background_tasks.add_task(
            download_model_task, task_id, model_type, model_name, model_info
        )

        return {
            "success": True,
            "data": {"task_id": task_id, "message": "下载任务已创建"},
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建下载任务失败: {e}")
        return {"success": False, "error": str(e), "data": None}


@model_router.delete("/{model_type}/{model_name}")
async def delete_model(model_type: str, model_name: str) -> Dict[str, Any]:
    """删除模型"""
    try:
        model_info = get_model_info(model_type, model_name)
        if not model_info:
            raise HTTPException(status_code=404, detail="模型不存在")

        if not model_info.get("installed", False):
            return {"success": False, "error": "模型未安装", "data": None}

        # 删除模型文件
        if model_type == "faster_whisper":
            # FasterWhisper 模型存储在 HuggingFace 缓存中
            hf_cache = Path.home() / ".cache" / "huggingface"
            model_size_name = model_name.replace("faster-whisper-", "")

            # 尝试删除不同可能的缓存目录
            possible_paths = [
                # FasterWhisper实际使用的路径（Systran组织）
                hf_cache / "hub" / f"models--Systran--faster-whisper-{model_size_name}",
                # 备选路径（以防将来变化）
                hf_cache
                / "transformers"
                / f"models--Systran--faster-whisper-{model_size_name}",
                hf_cache / "hub" / f"models--openai--whisper-{model_size_name}",
                hf_cache
                / "transformers"
                / f"models--openai--whisper-{model_size_name}",
            ]

            deleted_any = False
            for path in possible_paths:
                if path.exists():
                    import shutil

                    shutil.rmtree(path)
                    logger.info(f"已删除FasterWhisper模型缓存: {path}")
                    deleted_any = True

            if not deleted_any:
                logger.warning(f"未找到FasterWhisper模型缓存: {model_name}")

        elif "local_path" in model_info and model_info["local_path"]:
            # 其他模型的删除逻辑
            local_path = Path(model_info["local_path"])
            if local_path.exists():
                if local_path.is_dir():
                    import shutil

                    shutil.rmtree(local_path)
                else:
                    local_path.unlink()
                logger.info(f"已删除模型文件: {local_path}")

        return {"success": True, "message": "模型删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {e}")
        return {"success": False, "error": str(e)}


@model_router.get("/download/{task_id}/stream")
async def get_download_progress_stream(task_id: str):
    """获取下载进度流 (SSE)"""

    async def generate_progress():
        """生成下载进度数据流"""
        while True:
            try:
                # 获取任务当前状态
                task = download_manager.get_task_by_id(task_id)
                if not task:
                    yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                    break

                # 发送当前进度
                progress_data = {
                    "task_id": task_id,
                    "status": task.get("status", "unknown"),
                    "progress": task.get("progress", 0),
                    "current_step": task.get("current_step", ""),
                    "updated_at": task.get("updated_at", ""),
                    "model_type": task.get("model_type", ""),
                    "model_name": task.get("model_name", ""),
                }

                yield f"data: {json.dumps(progress_data)}\n\n"

                # 如果任务完成或失败，结束流
                if task.get("status") in ["completed", "failed"]:
                    break

                # 等待一段时间再次检查
                await asyncio.sleep(1)

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break

    return StreamingResponse(
        generate_progress(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


async def download_model_task(
    task_id: str, model_type: str, model_name: str, model_info: Dict[str, Any]
):
    """后台下载模型任务"""
    try:
        logger.info(f"开始下载模型: {model_type}/{model_name}")

        # 更新任务状态
        download_manager.update_task(
            task_id,
            {"status": "downloading", "progress": 0, "current_step": "正在下载模型..."},
        )

        if model_type == "whisper":
            # Whisper模型下载
            await download_whisper_model(task_id, model_name, model_info)

        elif model_type == "faster_whisper":
            # FasterWhisper模型下载
            await download_faster_whisper_model(task_id, model_name, model_info)

        elif model_type == "sensevoice":
            # SenseVoice模型下载
            await download_sensevoice_model(task_id, model_name, model_info)

        elif model_type == "dolphin":
            # Dolphin模型下载
            await download_dolphin_model(task_id, model_name, model_info)

        # 更新任务为完成状态
        download_manager.update_task(
            task_id,
            {
                "status": "completed",
                "progress": 100,
                "current_step": "下载完成",
                "completed_at": datetime.now().isoformat(),
            },
        )

        logger.info(f"模型下载完成: {model_type}/{model_name}")

    except Exception as e:
        logger.error(f"模型下载失败: {e}")

        # 更新任务为失败状态
        download_manager.update_task(
            task_id,
            {
                "status": "failed",
                "current_step": f"下载失败: {str(e)}",
                "error": str(e),
                "failed_at": datetime.now().isoformat(),
            },
        )


async def download_whisper_model(
    task_id: str, model_name: str, model_info: Dict[str, Any]
):
    """下载Whisper模型"""
    # 使用whisper库的内置下载功能
    try:
        import whisper

        # 更新进度
        download_manager.update_task(
            task_id,
            {"progress": 50, "current_step": "正在下载Whisper模型..."},
        )

        # 这会自动下载并缓存模型
        model = whisper.load_model(model_name)

        # 模拟下载进度更新
        for i in range(50, 100, 10):
            download_manager.update_task(task_id, {"progress": i})
            await asyncio.sleep(0.5)

        logger.info(f"Whisper {model_name} 模型下载完成")

    except ImportError:
        raise RuntimeError("openai-whisper 未安装")


async def download_faster_whisper_model(
    task_id: str, model_name: str, model_info: Dict[str, Any]
):
    """下载FasterWhisper模型"""
    try:
        from faster_whisper import WhisperModel

        # 更新进度
        download_manager.update_task(
            task_id,
            {"progress": 10, "current_step": "正在准备FasterWhisper模型下载..."},
        )

        # 解析模型大小 (faster-whisper-small -> small)
        model_size = model_name.replace("faster-whisper-", "")

        logger.info(f"开始下载 FasterWhisper 模型: {model_size}")

        # 更新进度
        download_manager.update_task(
            task_id,
            {"progress": 30, "current_step": f"正在下载 {model_size} 模型..."},
        )

        # FasterWhisper 会自动下载并缓存模型
        # 这里我们创建一个模型实例来触发下载
        model = WhisperModel(
            model_size,
            device="cpu",  # 下载时先用CPU，避免显存问题
            compute_type="int8",  # 使用较小的计算类型加快下载
            local_files_only=False,  # 允许在线下载模型
        )

        # 模拟下载进度更新
        progress_steps = [40, 60, 80, 90]
        for i, progress in enumerate(progress_steps):
            download_manager.update_task(
                task_id,
                {
                    "progress": progress,
                    "current_step": f"正在下载模型文件... ({i+1}/{len(progress_steps)})",
                },
            )
            await asyncio.sleep(1)

        logger.info(f"FasterWhisper {model_size} 模型下载完成")

        # 清理模型实例以释放内存
        del model

    except ImportError:
        raise RuntimeError("faster-whisper 未安装，请运行: pip install faster-whisper")
    except Exception as e:
        logger.error(f"FasterWhisper 模型下载失败: {e}")
        raise RuntimeError(f"FasterWhisper 模型下载失败: {e}")


async def download_sensevoice_model(
    task_id: str, model_name: str, model_info: Dict[str, Any]
):
    """下载SenseVoice模型"""
    try:
        # 更新进度
        download_manager.update_task(
            task_id,
            {"progress": 10, "current_step": "正在准备SenseVoice模型下载..."},
        )

        # 获取仓库ID
        repo_id = model_info.get("repo", "iic/SenseVoiceSmall")

        # 方法1: 优先使用ModelScope + FunASR (推荐)
        try:
            logger.info("尝试使用FunASR + ModelScope下载SenseVoice模型")

            # 检查FunASR是否可用
            try:
                from funasr import AutoModel as FunASRAutoModel

                download_manager.update_task(
                    task_id,
                    {
                        "progress": 30,
                        "current_step": "正在通过FunASR下载SenseVoice模型...",
                    },
                )

                # 使用FunASR下载SenseVoice (按照官方demo)
                model = FunASRAutoModel(
                    model=repo_id,
                    trust_remote_code=True,
                    vad_model="fsmn-vad",
                    vad_kwargs={"max_single_segment_time": 30000},
                    cache_dir="./data/models/funasr_cache",
                    device="cpu",  # 默认使用CPU，可根据需要改为cuda:0
                )

                download_manager.update_task(
                    task_id,
                    {
                        "progress": 90,
                        "current_step": "SenseVoice模型下载完成，正在验证...",
                    },
                )

                logger.info(f"SenseVoice {model_name} 模型通过FunASR下载完成")
                return

            except ImportError:
                logger.warning("FunASR库未安装，尝试其他方法")
                raise

        except Exception as e:
            logger.warning(f"FunASR下载失败: {e}")

        # 方法2: 使用ModelScope直接下载
        try:
            logger.info("尝试使用ModelScope直接下载")
            from modelscope import snapshot_download

            download_manager.update_task(
                task_id,
                {"progress": 40, "current_step": "正在通过ModelScope下载模型文件..."},
            )

            # 直接下载模型文件
            model_dir = snapshot_download(
                repo_id, cache_dir="./data/models/modelscope_cache", revision="master"
            )

            download_manager.update_task(
                task_id,
                {"progress": 90, "current_step": "模型文件下载完成，正在验证..."},
            )

            logger.info(
                f"SenseVoice {model_name} 模型文件通过ModelScope下载完成: {model_dir}"
            )
            return

        except ImportError:
            logger.warning("ModelScope库未安装")
        except Exception as e:
            logger.warning(f"ModelScope直接下载失败: {e}")

        # 方法3: 手动下载模型文件 (最后备选)
        try:
            logger.info("尝试手动下载SenseVoice模型文件")
            import requests
            import zipfile
            from pathlib import Path

            # 创建模型目录
            model_dir = Path("./data/models/sensevoice")
            model_dir.mkdir(parents=True, exist_ok=True)

            download_manager.update_task(
                task_id,
                {"progress": 50, "current_step": "正在从GitHub下载模型文件..."},
            )

            # SenseVoice的GitHub Release URL (如果可用)
            # 这里可以根据实际情况调整下载链接
            download_urls = [
                "https://github.com/FunAudioLLM/SenseVoice/releases/download/v1.0/model.onnx",  # 示例
            ]

            success = False
            for url in download_urls:
                try:
                    response = requests.get(url, stream=True, timeout=30)
                    response.raise_for_status()

                    filename = model_dir / url.split("/")[-1]
                    with open(filename, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                    logger.info(f"下载文件成功: {filename}")
                    success = True
                    break
                except Exception as e:
                    logger.warning(f"从 {url} 下载失败: {e}")
                    continue

            if success:
                download_manager.update_task(
                    task_id,
                    {"progress": 90, "current_step": "模型文件下载完成..."},
                )
                logger.info(f"SenseVoice {model_name} 模型文件手动下载完成")
                return
            else:
                raise RuntimeError("所有下载方法都失败")

        except Exception as e:
            logger.error(f"手动下载也失败: {e}")

        # 如果所有方法都失败，给出安装建议
        raise RuntimeError(
            "SenseVoice模型下载失败。建议安装FunASR库：pip install funasr modelscope"
        )

    except Exception as e:
        logger.error(f"SenseVoice模型下载失败: {e}")
        raise


async def download_dolphin_model(
    task_id: str, model_name: str, model_info: Dict[str, Any]
):
    """下载Dolphin模型"""
    try:
        models_path = get_model_storage_path()
        dolphin_path = models_path / "dolphin"
        dolphin_path.mkdir(parents=True, exist_ok=True)

        model_file = dolphin_path / f"{model_name}.pt"

        if "url" in model_info:
            # 从URL下载
            url = model_info["url"]

            download_manager.update_task(
                task_id,
                {"progress": 10, "current_step": "正在连接下载服务器..."},
            )

            response = requests.get(url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded_size = 0

            with open(model_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if total_size > 0:
                            progress = 10 + int((downloaded_size / total_size) * 80)
                            download_manager.update_task(
                                task_id,
                                {
                                    "progress": progress,
                                    "current_step": f"正在下载... ({downloaded_size}/{total_size} bytes)",
                                },
                            )

            logger.info(f"Dolphin {model_name} 模型下载完成: {model_file}")
        else:
            # 如果没有URL，创建一个占位文件（用于测试）
            with open(model_file, "w") as f:
                f.write(f"# Dolphin {model_name} model placeholder\n")

            logger.info(f"Dolphin {model_name} 占位文件创建完成")

    except Exception as e:
        raise RuntimeError(f"Dolphin模型下载失败: {e}")
