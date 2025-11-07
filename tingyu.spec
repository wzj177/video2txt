# tingyu.spec
# PyInstaller configuration for 听语AI (TingYu AI)

# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# 项目根目录（spec 文件所在目录）
project_root = os.path.abspath(".")

# 入口脚本路径
main_script = os.path.join(project_root, "app", "main.py")

# 二进制文件（如 pandoc.exe）
binaries = [
    (os.path.join(project_root, "tools", "pandoc.exe"), "."),  # 打包到根目录
]

# 静态资源和配置文件（非二进制）
datas = [
    # public 静态资源
    (os.path.join(project_root, "public"), "public"),
    # config 配置目录（你的代码会动态写 settings.json）
    (os.path.join(project_root, "config"), "config"),
    # 注意：data/outputs 是运行时生成的，不需要打包
]

# 隐藏导入（如果你用了动态导入，比如 biz.tasks.*）
hiddenimports = [
    "biz.tasks.video_tasks",
    "biz.tasks.meeting_tasks",
    "biz.queue.task_manager",
    "biz.routes.pages",
    "biz.routes.system_api",
    "biz.routes.video_api",
    "biz.routes.meeting_api",
    "biz.routes.model_api",
    "biz.routes.settings_api",
    "biz.routes.notification_api",
    "biz.routes.voice_analysis_api",
    "biz.middleware.exception_handler",
    "biz.database.connection",
]

block_cipher = None

a = Analysis(
    [main_script],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="tingyu_ai",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # 启用 UPX 压缩（减小体积）
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # 开发阶段建议 True，看到日志；发布可设为 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)