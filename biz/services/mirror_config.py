#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 国内镜像配置
"""

import os
import logging

logger = logging.getLogger(__name__)


class MirrorConfig:
    """镜像配置管理"""

    # 国内HuggingFace镜像列表
    HUGGINGFACE_MIRRORS = [
        "https://hf-mirror.com",  # HF-Mirror 清华镜像 (推荐)
        "https://huggingface.co",  # 原始地址
    ]

    # ModelScope配置
    MODELSCOPE_CONFIG = {
        "cache_dir": "./data/models/modelscope_cache",
        "trust_remote_code": True,
    }

    # HuggingFace配置
    HUGGINGFACE_CONFIG = {
        "cache_dir": "./data/models/huggingface_cache",
        "trust_remote_code": True,
    }

    @staticmethod
    def setup_huggingface_mirror():
        """设置HuggingFace镜像"""
        try:
            # 设置环境变量
            os.environ["HF_ENDPOINT"] = MirrorConfig.HUGGINGFACE_MIRRORS[0]
            logger.info(f"已设置HuggingFace镜像: {MirrorConfig.HUGGINGFACE_MIRRORS[0]}")
            return True
        except Exception as e:
            logger.error(f"设置HuggingFace镜像失败: {e}")
            return False

    @staticmethod
    def check_modelscope_available():
        """检查ModelScope是否可用"""
        try:
            import modelscope

            logger.info("ModelScope库已安装")
            return True
        except ImportError:
            logger.warning("ModelScope库未安装，建议安装以获得更好的国内访问体验")
            return False

    @staticmethod
    def get_installation_guide():
        """获取安装指南"""
        return {
            "modelscope": {
                "command": "pip install modelscope",
                "description": "阿里云魔搭社区，国内访问最稳定",
                "homepage": "https://modelscope.cn",
            },
            "transformers_with_mirror": {
                "command": "pip install transformers torch",
                "description": "配合HF-Mirror镜像使用",
                "mirror_setup": "export HF_ENDPOINT=https://hf-mirror.com",
            },
        }


# 全局配置实例
mirror_config = MirrorConfig()
