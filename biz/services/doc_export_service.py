#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
word导出服务
使用pandoc将Markdown文件转换为word
"""

import logging
import os
import subprocess
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class DocExportService:
    """word导出服务类"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent.parent
        self.outputs_dir = self.project_root / "data" / "outputs"

    async def export_md_to_word(self, task_id: str, file_name: str) -> Dict[str, Any]:
        """
        将MD文件导出为word

        Args:
            task_id: 任务ID
            file_name: MD文件名（包含扩展名）

        Returns:
            Dict包含成功状态和结果信息
        """
        try:
            # 验证文件名
            if not file_name.endswith(".md"):
                return {"success": False, "error": "只支持.md文件导出为word"}

            # 构建文件路径
            task_output_dir = self.outputs_dir / task_id
            md_file_path = task_output_dir / file_name

            # 检查MD文件是否存在
            if not md_file_path.exists():
                return {"success": False, "error": f"Markdown文件不存在: {file_name}"}

            # 生成word文件名（保持相同的基本名称）
            word_file_name = file_name.replace(".md", ".docx")
            word_file_path = task_output_dir / word_file_name

            # 如果文件已存在，则直接返回
            if word_file_path.exists():
                return {
                    "success": True,
                    "data": {
                        "word_file_name": word_file_name,
                        "word_file_path": str(word_file_path),
                        "download_url": f"/api/tasks/video/{task_id}/files/{word_file_name}",
                        "file_size": (
                            word_file_path.stat().st_size
                            if word_file_path.exists()
                            else 0
                        )
                    }
                }

            # 检查pandoc是否可用
            pandoc_available = await self._check_pandoc_available()
            if not pandoc_available:
                return {"success": False, "error": "Pandoc未安装或不可用，无法导出word"}

            # 使用pandoc转换MD到word
            success = await self._convert_md_to_word(md_file_path, word_file_path)

            if success:
                return {
                    "success": True,
                    "data": {
                        "word_file_name": word_file_name,
                        "word_file_path": str(word_file_path),
                        "download_url": f"/api/tasks/video/{task_id}/files/{word_file_name}",
                        "file_size": (
                            word_file_path.stat().st_size
                            if word_file_path.exists()
                            else 0
                        ),
                    },
                }
            else:
                return {"success": False, "error": "word转换失败"}

        except Exception as e:
            logger.error(f"word导出过程中发生错误: {e}")
            return {"success": False, "error": f"word导出失败: {str(e)}"}

    async def _check_pandoc_available(self) -> bool:
        """检查pandoc是否可用"""
        try:
            # 运行pandoc --version来检查是否安装
            process = await asyncio.create_subprocess_exec(
                self.get_pandoc_path(),
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.warning(f"检查pandoc可用性失败: {e}")
            return False

    def get_pandoc_path(self):
        """
        获取 pandoc 可执行文件路径
        - 开发环境：使用系统 PATH 中的 pandoc
        - 打包后（Windows）：使用内嵌的 pandoc.exe
        """
        if getattr(sys, 'frozen', False):
            # PyInstaller 打包环境
            if os.name == 'nt':
                return os.path.join(sys._MEIPASS, 'pandoc.exe')
            else:
                # macOS / Linux 打包（如果你未来支持）
                return os.path.join(sys._MEIPASS, 'pandoc')
        else:
            # 开发环境
            return 'pandoc'

    def get_reference_doc_path(self):
        if getattr(sys, 'frozen', False):
            ref_path = Path(sys._MEIPASS) / "data" / "templates" / "tingyu-reference.docx"
        else:
            ref_path = Path(__file__).parent.parent.parent / "data" / "templates" / "tingyu-reference.docx"

        if not ref_path.exists():
            raise FileNotFoundError(f"参考样式模板不存在: {ref_path}")
        return ref_path

    async def _convert_md_to_word(self, md_file_path: Path, word_file_path: Path) -> bool:
        """
        使用pandoc将Markdown转换为word

        Args:
            md_file_path: 输入的MD文件路径
            word_file_path: 输出的word文件路径

        Returns:
            转换是否成功
        """
        try:
            # 构建pandoc命令
            cmd = [
                self.get_pandoc_path(),
                str(md_file_path),
                "-o",
                str(word_file_path.with_suffix('.docx'))
            ]
            # cmd = [
            #     self.get_pandoc_path(),
            #     str(md_file_path),
            #     "-o",
            #     str(word_file_path),
            #     "--word-engine=xelatex",  # 使用XeLaTeX引擎，支持中文
            #     "--template=eisvogel",  # 使用eisvogel模板（如果可用）
            #     "-V",
            #     "CJKmainfont=PingFang SC",  # 设置中文字体
            #     "-V",
            #     "geometry:margin=1in",  # 设置页边距
            #     "--toc",  # 生成目录
            #     "--toc-depth=3",  # 目录深度
            #     "--number-sections",  # 章节编号
            #     "-V",
            #     "fontsize=12pt",  # 字体大小
            #     "-V",
            #     "linestretch=1.2",  # 行间距
            # ]

            logger.info(f"执行pandoc命令: {' '.join(cmd)}")

            # 异步执行pandoc命令
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(md_file_path.parent),
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"word转换成功: {word_file_path}")
                return True
            else:
                logger.error(f"pandoc转换失败，返回码: {process.returncode}")
                logger.error(f"stderr: {stderr.decode('utf-8', errors='ignore')}")

                # 如果使用模板失败，尝试基本转换
                return await self._convert_md_to_word_basic(md_file_path, word_file_path)

        except Exception as e:
            logger.error(f"pandoc转换过程中发生异常: {e}")
            return False

    async def _convert_md_to_word_basic(
        self, md_file_path: Path, word_file_path: Path
    ) -> bool:
        """
        使用基本pandoc命令进行转换（不依赖模板）

        Args:
            md_file_path: 输入的MD文件路径
            word_file_path: 输出的word文件路径

        Returns:
            转换是否成功
        """
        try:
            # 简化的pandoc命令
            cmd = [
                "pandoc",
                str(md_file_path),
                "-o",
                str(word_file_path),
                "--word-engine=xelatex",  # 使用XeLaTeX引擎
                "-V",
                "CJKmainfont=PingFang SC",  # 中文字体
                "-V",
                "geometry:margin=1in",  # 页边距
                "--toc",  # 目录
                "-V",
                "fontsize=12pt",  # 字体大小
            ]

            logger.info(f"执行基本pandoc命令: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(md_file_path.parent),
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"基本word转换成功: {word_file_path}")
                return True
            else:
                logger.error(f"基本pandoc转换也失败，返回码: {process.returncode}")
                logger.error(f"stderr: {stderr.decode('utf-8', errors='ignore')}")

                # 最后尝试最简单的转换
                return await self._convert_md_to_word_minimal(
                    md_file_path, word_file_path
                )

        except Exception as e:
            logger.error(f"基本pandoc转换过程中发生异常: {e}")
            return False

    async def _convert_md_to_word_minimal(
        self, md_file_path: Path, word_file_path: Path
    ) -> bool:
        """
        最简单的pandoc转换（最大兼容性）

        Args:
            md_file_path: 输入的MD文件路径
            word_file_path: 输出的word文件路径

        Returns:
            转换是否成功
        """
        try:
            # 最简单的命令
            cmd = ["pandoc", str(md_file_path), "-o", str(word_file_path)]

            logger.info(f"执行最简pandoc命令: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"最简word转换成功: {word_file_path}")
                return True
            else:
                logger.error(f"最简pandoc转换失败，返回码: {process.returncode}")
                logger.error(f"stderr: {stderr.decode('utf-8', errors='ignore')}")
                return False

        except Exception as e:
            logger.error(f"最简pandoc转换过程中发生异常: {e}")
            return False


# 创建全局实例
word_export_service = DocExportService()
