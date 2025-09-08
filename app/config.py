#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
听语AI - 应用配置
"""

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 静态文件目录
STATIC_DIR = PROJECT_ROOT / "public"
ASSETS_DIR = STATIC_DIR / "assets"
PAGES_DIR = STATIC_DIR / "pages"

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "outputs"
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = PROJECT_ROOT / "cache"

# 服务器配置
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 19080

# 确保目录存在
for directory in [OUTPUT_DIR, UPLOAD_DIR, CACHE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
