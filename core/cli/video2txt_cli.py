#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Video2Text CLI - 音视频智能处理命令行工具
支持批量处理、多种输出格式、AI分析、网络URL等完整功能

使用示例：
  # 基本音频转录
  python -m src.cli.video2txt_cli -i "/path/to/audio.m4a"
  
  # 网络URL处理（支持直链和Bilibili）
  python -m src.cli.video2txt_cli -i "https://example.com/video.mp4"
  python -m src.cli.video2txt_cli -i "https://www.bilibili.com/video/BV1234567890"
  
  # 完整学习材料生成
  python -m src.cli.video2txt_cli -i "/path/to/video.mp4" \
    --flashcards --note_card --note_xmind --note_mmap \
    --api_key=sk-xxx --api_base=https://api.openai.com/v1 \
    --gpt_model=gpt-4 --voice_mode=auto
    
  # 批量处理
  python -m src.cli.video2txt_cli -i "/path/to/videos/" --batch
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import ssl
import tempfile
import shutil
import requests
from hashlib import md5
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from tqdm import tqdm
import srt
import cv2
import numpy as np

# 信任自签名证书（绕过 SSL 验证）
ssl._create_default_https_context = ssl._create_unverified_context

# 确保项目根目录在Python路径中
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 导入核心模块
from src.core.voice_recognition_core import voice_core, initialize_voice_recognition
from src.adapters.ai_client_openai import OpenAIClientWrapper
from src.adapters.ai_client_ollama import OllamaClient

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class Video2TextCLI:
    """AI Video2Text 命令行处理器"""

    def __init__(self):
        self.start_time = None
        self.stats = {
            "files_processed": 0,
            "total_duration": 0,
            "errors": 0,
            "outputs_generated": [],
        }

        # 支持的文件格式
        self.supported_formats = {
            "video": [".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"],
            "audio": [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"],
        }

    def setup_logging(self, verbose: bool = False):
        """设置日志级别"""
        level = logging.DEBUG if verbose else logging.INFO
        logging.getLogger().setLevel(level)
        logger.setLevel(level)

    def check_file_support(self, file_path: str) -> tuple[bool, str]:
        """检查文件是否支持"""
        path = Path(file_path)
        if not path.exists():
            return False, "file_not_found"

        suffix = path.suffix.lower()

        for format_type, extensions in self.supported_formats.items():
            if suffix in extensions:
                return True, format_type

        return False, "unsupported"

    def is_url(self, input_path: str) -> bool:
        """检查输入是否为URL"""
        return input_path.startswith(("http://", "https://"))

    def get_temp_video_path(self, url: str = None) -> str:
        """获取临时视频文件路径"""
        if url is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"temp_{timestamp}.mp4"
            return os.path.abspath(filename)
        else:
            # 对于URL，计算MD5并放到data/uploads目录下
            url_md5 = md5(url.encode("utf-8")).hexdigest()
            uploads_dir = Path("data/uploads")
            video_cache_dir = uploads_dir / url_md5
            video_cache_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{url_md5}.mp4"
            return str(video_cache_dir / filename)

    def download_video_to_tempfile(
        self, temp_file: str, url: str, headers: dict = None
    ) -> str:
        """从指定 URL 下载视频到本地临时文件，支持进度条显示"""
        logger.info(f"📡 正在请求视频资源：{url}")

        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()

        # 获取文件总大小（字节）
        total_size = int(response.headers.get("content-length", 0))

        # 使用 tqdm 显示进度条
        with open(temp_file, "wb") as f, tqdm(
            desc=f"📥 下载中",
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            ncols=80,
        ) as pbar:

            downloaded = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 每次读取 1MB
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    pbar.update(len(chunk))

        logger.info(f"✅ 下载完成：{temp_file}")
        return temp_file

    def download_bilibili_url_video(self, video_url: str, headers: dict = None) -> str:
        """从Bilibili视频直链下载视频文件"""
        if headers is None:
            headers = {
                "Referer": "https://www.bilibili.com/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "cookie": "buvid3=A2E5752C-5256-BD1E-0CCA-32759D5BA08155742infoc; b_nut=1732976055; _uuid=FF568286-E715-1694-768F-EE2B9C3152DA56119infoc; buvid4=B176089E-6E08-C5DD-029D-4CA98F56169956463-024113014-9Ulxqnpl0tZBiU5lCrbNuzNVSLkrvvvCDAVu1W47qrY9iit%2Bvc; buvid_fp=96fe3fafbe3a068784791dc533a68869; rpdid=|(J~R~|||~Rm0J'u~JJuR~uu|",
            }

        return self.download_video_to_tempfile(
            self.get_temp_video_path(video_url), video_url, headers=headers
        )

    def download_url_video(self, url: str) -> str:
        """根据URL类型选择合适的下载方法"""
        logger.info(f"🔗 检测到网络URL输入：{url}")

        # 检查是否已经缓存
        temp_file = self.get_temp_video_path(url)
        if os.path.exists(temp_file):
            logger.info(f"💾 使用缓存文件：{temp_file}")
            return temp_file

        if "bilibili.com" in url or "b23.tv" in url:
            return self.download_bilibili_url_video(url)
        else:
            # 通用URL下载
            return self.download_video_to_tempfile(temp_file, url)

    def extract_audio_from_video(
        self, video_path: str, output_dir: str
    ) -> Optional[str]:
        """从视频中提取音频"""
        try:
            import ffmpeg

            video_path = Path(video_path)
            audio_path = Path(output_dir) / f"{video_path.stem}_audio.wav"

            logger.info(f"🎬 从视频提取音频: {video_path.name}")

            # 使用ffmpeg提取音频
            (
                ffmpeg.input(str(video_path))
                .output(str(audio_path), acodec="pcm_s16le", ac=1, ar="16000")
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            if audio_path.exists():
                logger.info(f"✅ 音频提取成功: {audio_path}")
                return str(audio_path)
            else:
                logger.error("❌ 音频文件未生成")
                return None

        except Exception as e:
            logger.error(f"❌ 音频提取失败: {e}")
            return None

    def transcribe_audio(
        self, audio_path: str, voice_mode: str = "auto"
    ) -> Optional[Dict]:
        """转录音频文件"""
        try:
            logger.info(f"🎤 开始转录: {Path(audio_path).name}")

            # 使用语音识别核心
            result = voice_core.transcribe(audio_path, language="auto")

            if result and result.get("text"):
                logger.info(f"✅ 转录成功，文本长度: {len(result['text'])}")
                return result
            else:
                logger.error("❌ 转录返回空结果")
                return None

        except Exception as e:
            logger.error(f"❌ 转录失败: {e}")
            return None

    def extract_keyframes_with_subtitles(
        self,
        video_path: str,
        output_dir: str,
        transcript_data: Dict,
        min_interval: int = None,
    ) -> tuple[List[str], str]:
        """基于字幕智能提取关键帧，包括封面帧选择 - 基于迭代2逻辑优化"""
        try:
            import cv2

            logger.info(f"🖼️ 智能提取关键帧: {Path(video_path).name}")

            frames_dir = Path(output_dir) / "keyframes"
            frames_dir.mkdir(exist_ok=True)

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error("❌ 无法打开视频文件")
                return [], None

            # 获取视频信息
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            # 动态计算最优间隔
            if min_interval is None:
                min_interval = self.calculate_optimal_frame_interval(duration)

            logger.info(
                f"   视频时长: {duration/60:.1f}分钟，动态间隔: {min_interval}秒"
            )
            logger.info(f"   预计关键帧数量: {int(duration // min_interval) + 1}")

            extracted_frames = []
            cover_frame = None
            last_frame_time = None

            segments = transcript_data.get("segments", [])

            # 智能封面帧选择
            cover_candidates = []
            for segment in segments:
                start_time = segment.get("start", 0)
                text = segment.get("text", "").strip()

                # 前60秒内寻找有意义的内容
                if start_time > 60:
                    break

                if self.is_meaningful_content(text, start_time):
                    cover_candidates.append((start_time, text))

            # 选择最佳封面帧
            if cover_candidates:
                # 优先选择前15秒内的内容
                early_candidates = [c for c in cover_candidates if c[0] <= 15]
                if early_candidates:
                    best_time, content = max(early_candidates, key=lambda x: len(x[1]))
                else:
                    # 第二优先级：前30秒内的内容
                    medium_candidates = [c for c in cover_candidates if c[0] <= 30]
                    if medium_candidates:
                        best_time, content = max(
                            medium_candidates, key=lambda x: len(x[1])
                        )
                    else:
                        best_time, content = max(
                            cover_candidates, key=lambda x: len(x[1])
                        )

                # 提取封面帧
                minutes = int(best_time) // 60
                seconds = int(best_time) % 60
                cover_filename = f"{minutes:02d}_{seconds:02d}.jpg"
                cover_path = frames_dir / cover_filename

                if self.extract_frame_at_time(cap, best_time, str(cover_path)):
                    cover_frame = cover_filename
                    extracted_frames.append(str(cover_path))
                    last_frame_time = best_time
                    logger.info(
                        f"   📌 封面帧: {cover_filename} (内容: {content[:30]}...)"
                    )

            # 如果没有找到合适的封面帧，使用第一个有内容的字幕
            if cover_frame is None and segments:
                first_segment = segments[0]
                best_time = first_segment.get("start", 0)
                content = first_segment.get("text", "").strip()

                minutes = int(best_time) // 60
                seconds = int(best_time) % 60
                cover_filename = f"{minutes:02d}_{seconds:02d}.jpg"
                cover_path = frames_dir / cover_filename

                if self.extract_frame_at_time(cap, best_time, str(cover_path)):
                    cover_frame = cover_filename
                    extracted_frames.append(str(cover_path))
                    last_frame_time = best_time
                    logger.info(f"   📌 备用封面帧: {cover_filename}")

            # 继续提取后续关键帧
            for segment in segments:
                start_time = segment.get("start", 0)
                text = segment.get("text", "").strip()

                # 跳过已经作为封面帧的时间点
                if last_frame_time and abs(start_time - last_frame_time) < 5:
                    continue

                # 检查时间间隔
                if (
                    last_frame_time is None
                    or start_time - last_frame_time >= min_interval
                ):
                    # 检查内容重要性
                    important_keywords = [
                        "重要",
                        "关键",
                        "核心",
                        "主要",
                        "首先",
                        "其次",
                        "最后",
                        "然后",
                        "注意",
                        "记住",
                        "总结",
                        "方法",
                        "技巧",
                        "步骤",
                        "特别",
                        "接下来",
                        "现在",
                        "这里",
                        "这个",
                        "下面",
                        "看到",
                        "可以",
                        "需要",
                        "应该",
                        "讲解",
                        "介绍",
                        "分析",
                        "说明",
                        "解释",
                        "学习",
                        "问题",
                        "解决",
                    ]

                    is_important = any(
                        keyword in text for keyword in important_keywords
                    )

                    # 内容长度也是重要性指标
                    content_rich = len(text.strip()) >= 15

                    should_extract = (
                        is_important
                        or content_rich
                        or (
                            last_frame_time
                            and start_time - last_frame_time >= min_interval * 1.5
                        )
                    )

                    if should_extract:
                        minutes = int(start_time) // 60
                        seconds = int(start_time) % 60
                        frame_filename = f"{minutes:02d}_{seconds:02d}.jpg"
                        frame_path = frames_dir / frame_filename

                        if self.extract_frame_at_time(cap, start_time, str(frame_path)):
                            extracted_frames.append(str(frame_path))
                            last_frame_time = start_time
                            importance_mark = (
                                "⭐" if is_important else "📝" if content_rich else "⏰"
                            )
                            logger.info(
                                f"   提取关键帧 {importance_mark}: {frame_filename} ({text[:20]}...)"
                            )

            cap.release()

            logger.info(f"✅ 智能关键帧提取完成，共 {len(extracted_frames)} 个关键帧")
            if cover_frame:
                logger.info(f"   🎯 封面帧: {cover_frame}")

            return extracted_frames, cover_frame

        except Exception as e:
            logger.error(f"❌ 关键帧提取失败: {e}")
            return [], None

    def calculate_optimal_frame_interval(self, video_duration: float) -> int:
        """根据视频时长动态计算最优关键帧间隔"""
        # 目标：获得合理数量的关键帧（6-12帧）
        min_frames, max_frames = 6, 12
        min_interval, max_interval = 15, 180  # 最小15秒，最大3分钟间隔

        # 根据视频时长计算最适宜的帧数
        if video_duration <= 180:  # 3分钟以内
            target_frames = max(min_frames, min(8, int(video_duration / 20)))
        elif video_duration <= 900:  # 15分钟以内
            target_frames = max(6, min(10, int(video_duration / 90)))
        elif video_duration <= 3600:  # 1小时以内
            target_frames = max(8, min(max_frames, int(video_duration / 300)))
        else:  # 超过1小时
            target_frames = max(10, min(15, int(video_duration / 400)))

        # 计算间隔
        interval = int(video_duration / target_frames)

        # 限制在合理范围内
        return max(min_interval, min(max_interval, interval))

    def is_meaningful_content(self, content: str, time_pos: float) -> bool:
        """判断内容是否有意义，用于封面帧选择 - 基于迭代2逻辑优化"""
        content = content.strip()

        # 内容长度过短直接跳过
        if len(content) < 5:
            return False

        # 纯粹的语气词或无意义词汇
        meaningless_words = [
            "嗯",
            "呃",
            "啊",
            "哦",
            "嗯嗯",
            "好",
            "对",
            "是的",
            "那个",
            "这个",
        ]
        if content in meaningless_words:
            return False

        # 常见开场白处理
        weak_openings = [
            "大家好",
            "欢迎大家",
            "今天我们",
            "hello",
            "hi",
            "各位",
            "朋友们",
        ]
        has_weak_opening = any(opening in content for opening in weak_openings)

        # 如果是弱开场白但内容较长，仍然可以作为封面帧
        if has_weak_opening and len(content) < 15:
            return False

        # 检查实质性内容关键词
        content_keywords = [
            "讲解",
            "介绍",
            "分析",
            "说明",
            "解释",
            "学习",
            "教学",
            "课程",
            "知识",
            "方法",
            "技巧",
            "原理",
            "概念",
            "定义",
            "特点",
            "要点",
            "首先",
            "第一",
            "接下来",
            "现在",
            "咱们",
            "我们来看",
            "下面",
            "重要",
            "关键",
            "核心",
            "主要",
            "注意",
            "问题",
            "解决",
            "操作",
            "步骤",
            "流程",
            "过程",
            "演示",
            "展示",
            "实践",
            "应用",
            "使用",
        ]

        has_content_keyword = any(keyword in content for keyword in content_keywords)

        # 如果时间很早（前10秒）且有实质内容，优先选择
        if time_pos <= 10 and (has_content_keyword or len(content) >= 15):
            return True

        # 其他情况按内容质量判断
        return len(content) >= 10 and (has_content_keyword or not has_weak_opening)

    def extract_frame_at_time(self, cap, time_seconds: float, output_path: str) -> bool:
        """在指定时间点提取视频帧"""
        try:
            import cv2

            cap.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
            ret, frame = cap.read()
            if ret:
                # 提高图片质量到95%
                cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                return True
            return False
        except Exception as e:
            logger.error(f"❌ 帧提取失败: {e}")
            return False

    def extract_keyframes(
        self, video_path: str, output_dir: str, num_frames: int = 8
    ) -> List[str]:
        """简单关键帧提取（兼容性方法）"""
        try:
            import cv2

            logger.info(f"🖼️ 提取关键帧: {Path(video_path).name}")

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error("❌ 无法打开视频文件")
                return []

            # 获取视频信息
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            duration = total_frames / fps if fps > 0 else 0

            # 计算关键帧间隔
            frame_interval = max(1, total_frames // num_frames)

            frames_dir = Path(output_dir) / "keyframes"
            frames_dir.mkdir(exist_ok=True)

            extracted_frames = []

            for i in range(0, total_frames, frame_interval):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()

                if ret:
                    timestamp = i / fps if fps > 0 else i
                    frame_filename = f"frame_{i:06d}_{timestamp:.2f}s.jpg"
                    frame_path = frames_dir / frame_filename

                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    extracted_frames.append(str(frame_path))

            cap.release()

            logger.info(f"✅ 关键帧提取完成，共 {len(extracted_frames)} 帧")
            return extracted_frames

        except Exception as e:
            logger.error(f"❌ 关键帧提取失败: {e}")
            return []

    async def generate_ai_content(
        self,
        transcript: str,
        transcript_data: Dict,
        keyframes: List[str],
        file_md5: str,
        cover_frame: str,
        args: argparse.Namespace,
    ) -> Dict[str, Any]:
        """生成AI分析内容 - 基于迭代2的高质量逻辑"""
        results = {}

        # 初始化AI客户端
        ai_client = None

        if args.api_key and args.api_base:
            # 使用外部API
            ai_client = OpenAIClientWrapper(
                api_key=args.api_key,
                api_base=args.api_base,
                model=args.gpt_model or "gpt-3.5-turbo",
            )
            logger.info(f"🤖 使用外部AI: {args.gpt_model}")
        else:
            # 使用本地Ollama
            try:
                ai_client = OllamaClient(model="qwen:1.8b")
                logger.info("🤖 使用本地Ollama AI")
            except Exception as e:
                logger.warning(f"⚠️ Ollama不可用: {e}")

        if not ai_client:
            logger.warning("⚠️ 无AI客户端，跳过智能分析")
            return results

        try:
            # 首先生成内容主题分析（迭代2的逻辑）
            theme_analysis = await self.analyze_content_theme(ai_client, transcript)
            results["theme"] = theme_analysis

            # 生成思维导图（优先生成，用于指导内容卡片）
            if args.note_xmind or args.note_mmap:
                logger.info("🧠 生成思维导图...")
                mindmap_content = await self.generate_mindmap(
                    ai_client, transcript_data, theme_analysis
                )
                results["mindmap"] = mindmap_content
                logger.info("✅ 思维导图生成完成")

            # 基于思维导图生成内容卡片
            if args.note_card:
                logger.info("📝 生成内容卡片...")
                content_card = await self.generate_content_card(
                    ai_client,
                    transcript,
                    theme_analysis,
                    results.get("mindmap"),
                    keyframes,
                    file_md5,
                    cover_frame,
                )
                results["content_card"] = content_card
                logger.info("✅ 内容卡片生成完成")

            # 生成高质量闪卡
            if args.flashcards:
                logger.info("🎯 生成学习闪卡...")
                flashcards = await self.generate_high_quality_flashcards(
                    ai_client, transcript, results.get("mindmap")
                )
                results["flashcards"] = flashcards
                logger.info("✅ 闪卡生成完成")

        except Exception as e:
            logger.error(f"❌ AI内容生成失败: {e}")

        return results

    async def analyze_content_theme(self, ai_client, transcript: str) -> str:
        """分析视频主题、类型和用途 - 为后续生成提供上下文"""
        prompt = f"""
# 任务
你是一位专业的视频内容分析师，请快速分析以下视频内容的核心主题、类型和用途。

# 分析维度
1. **内容主题**：视频讲述的核心主题是什么？
2. **视频类型**：教学视频/讲座/实操演示/理论解释/案例分析等
3. **目标受众**：学生/专业人士/初学者/进阶学习者等
4. **知识领域**：数学/编程/商业/生活技能等具体领域
5. **教学风格**：理论为主/实践为主/案例驱动/逐步深入等

# 输出格式
## 视频核心信息
- **主题**：[简洁的主题描述，不超过20字]
- **类型**：[视频类型]
- **领域**：[知识领域]

- **受众**：[目标受众]
- **风格**：[教学风格]

## 内容特征
- **难度等级**：初级/中级/高级
- **内容密度**：基础概念/深度分析/综合应用
- **实用性**：理论知识/实际应用/考试导向

## 生成建议
为后续内容生成提供3个关键指导原则：
1. [针对该类型视频的内容组织建议]
2. [适合该受众的表达方式建议]  
3. [体现该领域特色的重点方向]

# 视频内容（前3000字符）
{transcript[:3000]}
"""

        if hasattr(ai_client, "chat"):
            if asyncio.iscoroutinefunction(ai_client.chat):
                return await ai_client.chat(prompt)
            else:
                return ai_client.chat(prompt)
        return ""

    async def generate_mindmap(
        self, ai_client, transcript_data: Dict, theme_analysis: str
    ) -> str:
        """生成思维导图 - 使用迭代2的markmap格式"""
        # 构建带时间戳的文本
        timed_text = ""
        if transcript_data.get("segments"):
            for segment in transcript_data["segments"]:
                start_time = segment.get("start", 0)
                text = segment.get("text", "")
                minutes = int(start_time // 60)
                seconds = int(start_time % 60)
                timed_text += f"[{minutes:02d}:{seconds:02d}] {text}\n"

        # 两步生成法：先提取大纲，再优化格式
        step1_prompt = f"""
# 角色
你是一位专业的知识架构师，擅长将视频内容转化为清晰的思维导图结构。

## 内容主题上下文
{theme_analysis}

# 任务
请根据以下带时间戳的视频字幕，创建一个结构清晰、层次分明的思维导图大纲。

# 输出要求
1. 使用Markdown无序列表格式（- 和空格缩进表示层级）
2. 每个节点应是简洁的关键词或短语（不超过10个字）
3. 在重要节点末尾添加时间戳，格式为 `MM:SS`（例如 `01:23`）
4. 保持逻辑层次：主题 → 章节 → 要点 → 细节（最多4级）
5. 合并相似内容，但保留重要的知识点

# 输出格式示例
# 视频主题
- 基础概念
  - 定义解释 `01:23`
  - 重要特征 `02:45`
    - 特征一 `03:10`
    - 特征二 `03:30`
- 实践应用
  - 方法一 `05:20`
    - 步骤详解 `06:15`
  - 方法二 `08:30`

# 视频字幕内容
{timed_text[:25000]}
""".strip()

        if hasattr(ai_client, "chat"):
            if asyncio.iscoroutinefunction(ai_client.chat):
                outline = await ai_client.chat(step1_prompt)
            else:
                outline = ai_client.chat(step1_prompt)
        else:
            return ""

        # 第二步：优化为Markmap兼容格式
        step2_prompt = f"""
# 任务
你是一位Markdown格式专家，负责将以下思维导图大纲优化为标准Markmap兼容格式。

# 输出要求
1. 严格使用Markdown无序列表
2. 每级缩进使用2个空格
3. 时间戳统一为 `MM:SS` 格式（例如 `01:23`）
4. 每行一个节点，不跨行
5. 节点文本简洁，不超过15个字
6. 保留完整的知识结构层次
7. 确保语法正确，便于Markmap渲染

# 待优化内容
{outline}
""".strip()

        if hasattr(ai_client, "chat"):
            if asyncio.iscoroutinefunction(ai_client.chat):
                return await ai_client.chat(step2_prompt)
            else:
                return ai_client.chat(step2_prompt)
        return outline

    async def generate_content_card(
        self,
        ai_client,
        transcript: str,
        theme_analysis: str,
        mindmap_content: str,
        keyframes: List[str],
        file_md5: str,
        cover_frame: str,
    ) -> str:
        """生成内容卡片 - 基于迭代2的高质量逻辑"""

        # 构建图片策略
        image_strategy = ""
        if keyframes:
            total_frames = len(keyframes)
            cover_info = f"封面帧: {cover_frame}" if cover_frame else "未指定封面帧"

            image_strategy = f"""

## 📌 智能图片分配策略
- 总共有 {total_frames} 张有效关键帧可用
- {cover_info}
- 图片路径格式：![](keyframes/帧文件名.jpg)
- 可用帧文件：{', '.join([Path(f).name for f in keyframes[:8]])}...

### 图片分配规则：
1. **开篇封面**：{f"使用 {cover_frame} 作为内容开头的封面图" if cover_frame else "使用第一个有效帧作为封面"}
2. **章节配图**：每个主要章节根据内容长度智能分配图片
   - 短章节（<300字）：1张图片
   - 中等章节（300-600字）：2张图片  
   - 长章节（>600字）：3-4张图片
3. **图片选择原则**：
   - 优先选择与该章节时间点接近的帧
   - 确保图片在整个内容中均匀分布
4. **封面使用**：在文章开头使用封面帧营造良好的第一印象

### 示例格式：
![](keyframes/{cover_frame if cover_frame else "frame_000001_0.50s.jpg"})
"""

        # 结构对齐要求
        structure_guide = ""
        if mindmap_content:
            structure_guide = f"""

## 🗂️ 结构对齐要求
以下是视频的思维导图结构，请严格按照此结构组织内容卡片：

{mindmap_content[:1500]}

### 结构转换规则：
1. **一级标题对应**：思维导图的每个一级要点对应内容卡片的一个## 章节
2. **内容整合**：将思维导图的二级、三级要点整合成该章节的段落内容
3. **保持完整性**：确保思维导图中的所有要点都在内容卡片中体现
4. **逻辑连贯**：每个章节内部保持逻辑连贯，形成完整的知识块
"""

        prompt = f"""
# 角色设定
你是一位资深的教育内容专家，擅长将教学视频转化为结构化、高价值的知识卡片。

# 核心任务
基于提供的思维导图结构，生成与之完全对应的内容卡片，确保结构一致性和内容完整性。

## 🎯 内容主题上下文
{theme_analysis}

{structure_guide}

## 内容质量要求
1. **结构严格对应**：每个章节必须与思维导图的一级要点完全对应
2. **内容深度挖掘**：将思维导图的细分要点展开为详细段落
3. **知识完整性**：覆盖思维导图中的所有知识点，不遗漏
4. **逻辑连贯性**：每个章节内部逻辑清晰，前后呼应

## 文体规范
- **开篇**：用「# 标题」概括视频核心价值
- **摘要**：用「## 摘要」概括视频核心内容
- **章节**：用「## 章节名」对应思维导图一级要点
- **内容**：
  - 每个章节包含**核心概念**、**方法技巧**、**应用案例**
  - 重要概念用**粗体**强调
  - 关键步骤用数字列表
  - 适当使用▪️符号突出要点
- **总结** 用「## 总结」总结整个视频表达的中心思想或主旨
- **思考** 用「## 思考」总结视频中值得思考的内容并提出问题让用户思考

{image_strategy}

## 特殊要求
- 确保章节数量与思维导图一级要点数量完全一致
- 每个章节的内容要充实，避免空洞概括
- 合理分配图片，让视觉效果丰富但不冗余

# 视频完整内容
{transcript[:25000]}

# 输出要求
生成完整的知识卡片，确保：
1. 结构与思维导图完全对应
2. 内容详实，体现教学价值
3. 图片分配合理，视觉效果佳
4. 总结部分体现整体学习价值

请直接输出完整内容，不要解释说明。
""".strip()

        if hasattr(ai_client, "chat"):
            if asyncio.iscoroutinefunction(ai_client.chat):
                return await ai_client.chat(prompt)
            else:
                return ai_client.chat(prompt)
        return ""

    async def generate_high_quality_flashcards(
        self, ai_client, transcript: str, mindmap_content: str = None
    ) -> List[Dict]:
        """生成高质量学习闪卡 - 基于迭代2的逻辑"""

        # 构建上下文信息
        context_info = ""
        if mindmap_content:
            context_info = f"""
## 思维导图结构参考
以下是内容的思维导图结构，可用于提取关键概念：

{mindmap_content[:1000]}
"""

        prompt = f"""
# 任务
你是一位专业的学习设计师，擅长从教学内容中提取关键概念制作高质量学习闪卡。

{context_info}

# 闪卡设计原则
1. **概念清晰**：每张卡片只包含一个核心概念
2. **问答精准**：问题明确，答案简短但完整  
3. **难度递进**：从基础概念到应用理解
4. **实用导向**：优先选择可应用的知识点
5. **记忆友好**：利于长期记忆和理解

# 闪卡类型
- **概念卡**：基础概念定义
- **应用卡**：方法和技巧应用
- **对比卡**：相似概念的区别
- **流程卡**：步骤和流程记忆
- **案例卡**：具体案例理解

# 输出格式
生成15-25张闪卡，每张卡片格式如下：

## 闪卡 01 - [卡片类型]
**正面**: [问题或概念名称]
**背面**: [详细解答或定义]
**标签**: #概念 #基础 #应用

# 特殊格式说明
- 对于复杂概念，背面可以使用要点列表
- 重要术语使用**粗体**标注
- 必要时可以包含简短例子

# 源内容
{transcript[:20000]}

请生成高质量的学习闪卡：
"""

        if hasattr(ai_client, "chat"):
            if asyncio.iscoroutinefunction(ai_client.chat):
                flashcards_text = await ai_client.chat(prompt)
            else:
                flashcards_text = ai_client.chat(prompt)

            # 解析闪卡文本为结构化数据
            flashcards = []
            import re

            # 匹配闪卡格式
            pattern = r"## 闪卡 \d+ - (.+?)\n\*\*正面\*\*: (.+?)\n\*\*背面\*\*: (.+?)\n\*\*标签\*\*: (.+?)(?=\n\n|\n##|\Z)"
            matches = re.findall(pattern, flashcards_text, re.DOTALL)

            for i, (card_type, front, back, tags) in enumerate(matches, 1):
                flashcards.append(
                    {
                        "id": i,
                        "category": card_type.strip(),
                        "question": front.strip(),
                        "answer": back.strip(),
                        "tags": tags.strip(),
                        "type": "基础" if i <= 8 else ("进阶" if i <= 16 else "应用"),
                    }
                )

            return flashcards

        return []

    def save_outputs(
        self,
        output_dir: str,
        transcript_data: Dict,
        ai_content: Dict,
        keyframes: List[str],
        file_md5: str,
        cover_frame: str,
        args: argparse.Namespace,
    ) -> List[str]:
        """保存所有输出文件 - 使用中文文件名"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []

        # 保存基础转录
        transcript_file = output_dir / "原始转录.json"
        with open(transcript_file, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)
        saved_files.append(str(transcript_file))

        # 保存纯文本
        text_file = output_dir / "原始转录.txt"
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(transcript_data.get("text", ""))
        saved_files.append(str(text_file))

        # 保存SRT字幕
        if transcript_data.get("segments"):
            srt_file = output_dir / "字幕文件.srt"
            with open(srt_file, "w", encoding="utf-8") as f:
                for i, segment in enumerate(transcript_data["segments"], 1):
                    start_time = self.seconds_to_srt_time(segment.get("start", 0))
                    end_time = self.seconds_to_srt_time(segment.get("end", 0))
                    f.write(f"{i}\n{start_time} --> {end_time}\n{segment['text']}\n\n")
            saved_files.append(str(srt_file))

        # 保存内容卡片
        if args.note_card and ai_content.get("content_card"):
            content_card_file = output_dir / "内容卡片.md"
            with open(content_card_file, "w", encoding="utf-8") as f:
                f.write(ai_content["content_card"])
            saved_files.append(str(content_card_file))

        # 保存思维导图
        if (args.note_xmind or args.note_mmap) and ai_content.get("mindmap"):
            # Markdown格式思维导图 (mmap格式)
            md_mindmap_file = output_dir / "思维导图.md"
            with open(md_mindmap_file, "w", encoding="utf-8") as f:
                f.write("# 思维导图\n\n")
                f.write("```mmap\n")
                f.write(ai_content["mindmap"])
                f.write("\n```")
            saved_files.append(str(md_mindmap_file))

            # XMind兼容格式
            if args.note_xmind:
                xmind_file = output_dir / "思维导图.mm"
                self.generate_freemind_xml(ai_content["mindmap"], xmind_file)
                saved_files.append(str(xmind_file))

        # 生成学习闪卡
        if args.flashcards and ai_content.get("flashcards"):
            # 获取关键帧用于闪卡图片
            keyframe_files = []
            frames_dir = output_dir / "keyframes"
            if frames_dir.exists():
                keyframe_files = list(frames_dir.glob("*.jpg"))
                keyframe_files.sort()

            # Markdown格式闪卡（带图片）
            md_flashcard_file = output_dir / "学习闪卡.md"
            with open(md_flashcard_file, "w", encoding="utf-8") as f:
                f.write("# 学习闪卡\n\n")
                f.write(
                    "> 💡 **提示**: 这些学习闪卡包含了视频的关键概念和要点，配有相关的关键帧图片帮助记忆。\n\n"
                )

                for i, card in enumerate(ai_content["flashcards"], 1):
                    f.write(f"## 闪卡 {i:02d} - {card.get('category', '概念卡')}\n\n")

                    # 添加相关图片（如果有）
                    if keyframe_files and i <= len(keyframe_files):
                        img_index = min(i - 1, len(keyframe_files) - 1)
                        img_path = keyframe_files[img_index]
                        relative_img_path = f"keyframes/{img_path.name}"
                        f.write(f"### 📸 相关图片\n")
                        f.write(f"![关键帧{i}]({relative_img_path})\n\n")

                    f.write(f"### ❓ 问题\n")
                    f.write(f"{card.get('question', '')}\n\n")
                    f.write(f"### ✅ 答案\n")
                    f.write(f"{card.get('answer', '')}\n\n")
                    f.write(f"### 🏷️ 标签\n")
                    f.write(f"{card.get('tags', '#学习')}\n\n")
                    f.write("---\n\n")
            saved_files.append(str(md_flashcard_file))

            # Anki格式闪卡（支持HTML和图片）
            anki_file = output_dir / "学习闪卡-Anki格式.csv"
            with open(anki_file, "w", encoding="utf-8", newline="") as f:
                import csv

                writer = csv.writer(f, quoting=csv.QUOTE_ALL)

                # Anki标准字段头
                writer.writerow(["Front", "Back", "Tags"])

                for i, card in enumerate(ai_content["flashcards"], 1):
                    question = card.get("question", "")
                    answer = card.get("answer", "")
                    tags = card.get("tags", "学习")
                    category = card.get("category", "概念卡")

                    # 构建前面（问题）- 支持HTML格式
                    front_html = f"<div class='question'>{question}</div>"

                    # 添加图片到前面（如果有）
                    if keyframe_files and i <= len(keyframe_files):
                        img_index = min(i - 1, len(keyframe_files) - 1)
                        img_path = keyframe_files[img_index]
                        img_name = img_path.name
                        front_html += f"<br><img src='{img_name}' style='max-width: 400px; border-radius: 8px;'>"

                    # 构建背面（答案）- 支持HTML格式
                    back_html = f"<div class='answer'>{answer}</div>"
                    back_html += f"<div class='category' style='margin-top: 10px; font-size: 0.9em; color: #666;'>分类: {category}</div>"

                    # 处理标签
                    if not tags.startswith("#"):
                        tags = f"#{tags}"

                    writer.writerow([front_html, back_html, tags])

            saved_files.append(str(anki_file))

            # 创建Anki导入说明文件
            anki_guide_file = output_dir / "Anki导入说明.md"
            with open(anki_guide_file, "w", encoding="utf-8") as f:
                f.write("# Anki导入说明\n\n")
                f.write("## 📋 如何导入到Anki\n\n")
                f.write("1. **打开Anki应用**\n")
                f.write("2. **创建新牌组**（建议命名为视频标题）\n")
                f.write("3. **导入文件**:\n")
                f.write("   - 点击 `文件` > `导入`\n")
                f.write(f"   - 选择 `学习闪卡-Anki格式.csv` 文件\n")
                f.write(
                    "   - 确认字段映射：`正面` → `Front`, `背面` → `Back`, `标签` → `Tags`\n"
                )
                f.write("4. **导入图片**（如果需要）:\n")
                f.write("   - 将 `keyframes` 文件夹中的图片复制到Anki媒体文件夹\n")
                f.write(
                    "   - Windows: `%APPDATA%\\Anki2\\用户名\\collection.media\\`\n"
                )
                f.write(
                    "   - macOS: `~/Library/Application Support/Anki2/用户名/collection.media/`\n\n"
                )
                f.write("## ⚙️ 推荐设置\n\n")
                f.write("- **新卡片顺序**: 按添加顺序\n")
                f.write("- **复习间隔**: 1 4 10 天\n")
                f.write("- **毕业间隔**: 4 天\n")
                f.write("- **简单间隔**: 7 天\n\n")
                f.write("## 🎨 卡片样式优化\n\n")
                f.write("建议在Anki中添加以下CSS样式到卡片模板：\n\n")
                f.write("```css\n")
                f.write(".question {\n")
                f.write("  font-size: 1.2em;\n")
                f.write("  font-weight: bold;\n")
                f.write("  margin-bottom: 15px;\n")
                f.write("}\n\n")
                f.write(".answer {\n")
                f.write("  font-size: 1.1em;\n")
                f.write("  line-height: 1.5;\n")
                f.write("}\n\n")
                f.write(".category {\n")
                f.write("  background: #f0f0f0;\n")
                f.write("  padding: 5px 10px;\n")
                f.write("  border-radius: 15px;\n")
                f.write("  display: inline-block;\n")
                f.write("}\n")
                f.write("```\n")

            saved_files.append(str(anki_guide_file))

        # 保存AI分析结果
        if ai_content:
            ai_file = output_dir / "AI分析结果.json"
            with open(ai_file, "w", encoding="utf-8") as f:
                json.dump(ai_content, f, ensure_ascii=False, indent=2)
            saved_files.append(str(ai_file))

        # 生成处理报告
        report_file = output_dir / "处理报告.md"
        self.generate_report(
            report_file,
            transcript_data,
            ai_content,
            keyframes,
            saved_files,
            cover_frame,
        )
        saved_files.append(str(report_file))

        return saved_files

    def seconds_to_srt_time(self, seconds: float) -> str:
        """转换秒数为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

    def generate_freemind_xml(self, content: str, output_file: Path):
        """生成FreeMind XML格式思维导图"""
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<map version="freeplane 1.9.13">
    <node CREATED="0" ID="root" MODIFIED="0" TEXT="音视频内容总结">
        <node CREATED="0" ID="content" MODIFIED="0" TEXT="主要内容">
            <node CREATED="0" ID="summary" MODIFIED="0" TEXT="{content[:200]}..."/>
        </node>
        <node CREATED="0" ID="keywords" MODIFIED="0" TEXT="关键词">
            <node CREATED="0" ID="key1" MODIFIED="0" TEXT="待提取"/>
        </node>
    </node>
</map>"""

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(xml_content)

    def generate_report(
        self,
        report_file: Path,
        transcript_data: Dict,
        ai_content: Dict,
        keyframes: List[str],
        saved_files: List[str],
        cover_frame: str = None,
    ):
        """生成处理报告"""
        report_content = f"""# 音视频处理报告

## 基本信息
- 处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 语音模型: {transcript_data.get('model', 'Unknown')}
- 设备: {transcript_data.get('device', 'Unknown')}
- 处理耗时: {transcript_data.get('processing_time', 0):.2f}秒

## 转录结果
- 文本长度: {len(transcript_data.get('text', ''))} 字符
- 分段数量: {len(transcript_data.get('segments', []))} 段
- 语言: {transcript_data.get('language', 'auto')}

## 关键帧信息
- 提取数量: {len(keyframes)} 帧
"""

        if cover_frame:
            report_content += f"- 封面帧: {cover_frame}\n"

        report_content += f"\n## AI分析内容\n"
        if ai_content.get("theme"):
            report_content += f"- 主题分析: ✅\n"
        if ai_content.get("mindmap"):
            report_content += f"- 思维导图: ✅\n"
        if ai_content.get("content_card"):
            report_content += f"- 内容卡片: ✅\n"
        if ai_content.get("flashcards"):
            report_content += f"- 学习闪卡: {len(ai_content['flashcards'])} 张\n"

        report_content += f"\n## 生成文件\n"
        for file in saved_files:
            file_path = Path(file)
            file_size = file_path.stat().st_size if file_path.exists() else 0
            report_content += f"- {file_path.name}: {file_size} bytes\n"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

    async def process_single_file(
        self, input_path: str, output_dir: str, args: argparse.Namespace
    ) -> bool:
        """处理单个文件 - 集成迭代2的高质量逻辑"""
        try:
            # 处理URL输入
            original_input = input_path
            temp_file_to_cleanup = None

            if self.is_url(input_path):
                logger.info(f"🌐 处理网络URL: {input_path}")
                try:
                    input_path = self.download_url_video(input_path)
                    temp_file_to_cleanup = input_path  # 标记下载的临时文件
                except Exception as e:
                    logger.error(f"❌ URL下载失败: {e}")
                    self.stats["errors"] += 1
                    return False

            logger.info(f"📁 处理文件: {Path(input_path).name}")

            # 检查文件支持
            supported, file_type = self.check_file_support(input_path)
            if not supported:
                logger.error(f"❌ 不支持的文件类型: {input_path}")
                self.stats["errors"] += 1
                return False

            # 计算文件MD5（用于缓存和图片路径）
            import hashlib

            # 对于URL，使用原始URL计算MD5；对于本地文件，使用文件路径
            input_for_md5 = (
                original_input if self.is_url(original_input) else input_path
            )
            file_md5 = hashlib.md5(input_for_md5.encode()).hexdigest()[:16]

            # 创建输出目录（使用当前日期）
            current_date = datetime.now().strftime("%m%d")
            file_output_dir = Path(output_dir) / current_date / Path(input_path).stem
            file_output_dir.mkdir(parents=True, exist_ok=True)

            # 音频处理
            audio_path = input_path
            keyframes = []
            cover_frame = None

            if file_type == "video":
                # 从视频提取音频
                audio_path = self.extract_audio_from_video(
                    input_path, str(file_output_dir)
                )
                if not audio_path:
                    logger.error("❌ 音频提取失败")
                    self.stats["errors"] += 1
                    return False

            # 语音转录
            transcript_data = self.transcribe_audio(audio_path, args.voice_mode)
            if not transcript_data:
                logger.error("❌ 转录失败")
                self.stats["errors"] += 1
                return False

            # 视频关键帧提取（基于字幕智能提取）
            if file_type == "video" and not args.no_keyframes:
                if transcript_data.get("segments"):
                    # 使用智能提取方法
                    keyframes, cover_frame = self.extract_keyframes_with_subtitles(
                        input_path, str(file_output_dir), transcript_data
                    )
                else:
                    # 回退到简单提取
                    keyframes = self.extract_keyframes(input_path, str(file_output_dir))

            # AI分析
            ai_content = {}
            if any([args.flashcards, args.note_card, args.note_xmind, args.note_mmap]):
                ai_content = await self.generate_ai_content(
                    transcript_data["text"],
                    transcript_data,
                    keyframes,
                    file_md5,
                    cover_frame,
                    args,
                )

            # 保存输出
            saved_files = self.save_outputs(
                str(file_output_dir),
                transcript_data,
                ai_content,
                keyframes,
                file_md5,
                cover_frame,
                args,
            )

            self.stats["files_processed"] += 1
            self.stats["outputs_generated"].extend(saved_files)

            logger.info(f"✅ 文件处理完成: {len(saved_files)} 个输出文件")
            return True

        except Exception as e:
            logger.error(f"❌ 文件处理失败: {e}")
            self.stats["errors"] += 1
            return False
        finally:
            # 清理下载的临时文件（但保留缓存文件）
            if temp_file_to_cleanup and not temp_file_to_cleanup.startswith(
                str(Path("data/uploads"))
            ):
                try:
                    if os.path.exists(temp_file_to_cleanup):
                        os.remove(temp_file_to_cleanup)
                        logger.debug(f"🗑️ 清理临时文件: {temp_file_to_cleanup}")
                except Exception as cleanup_error:
                    logger.warning(f"⚠️ 临时文件清理失败: {cleanup_error}")

    async def process_batch(
        self, input_path: str, output_dir: str, args: argparse.Namespace
    ):
        """批量处理"""
        # 检查是否为URL
        if self.is_url(input_path):
            # URL处理 - 直接作为单文件处理
            logger.info(f"🌐 检测到URL输入，开始处理...")
            await self.process_single_file(input_path, output_dir, args)
            return

        input_path = Path(input_path)

        if input_path.is_file():
            # 单文件处理
            await self.process_single_file(str(input_path), output_dir, args)
        elif input_path.is_dir():
            # 目录批量处理
            files = []
            for format_type, extensions in self.supported_formats.items():
                for ext in extensions:
                    files.extend(input_path.glob(f"*{ext}"))
                    files.extend(input_path.glob(f"**/*{ext}"))

            if not files:
                logger.warning("⚠️ 未找到支持的文件")
                return

            logger.info(f"📦 发现 {len(files)} 个文件，开始批量处理")

            for file_path in files:
                await self.process_single_file(str(file_path), output_dir, args)

                # 进度显示
                progress = (
                    (self.stats["files_processed"] + self.stats["errors"])
                    / len(files)
                    * 100
                )
                logger.info(f"📊 批量处理进度: {progress:.1f}%")

        else:
            logger.error(f"❌ 输入路径不存在或不是有效的URL: {input_path}")
            logger.error(f"❌ 输入路径无效: {input_path}")

    def print_final_stats(self):
        """打印最终统计"""
        total_time = time.time() - self.start_time if self.start_time else 0

        print("\n" + "=" * 60)
        print("🎯 处理完成统计")
        print("=" * 60)
        print(f"📁 处理文件数: {self.stats['files_processed']}")
        print(f"❌ 错误数量: {self.stats['errors']}")
        print(f"📄 生成文件数: {len(self.stats['outputs_generated'])}")
        print(f"⏱️ 总耗时: {total_time:.2f}秒")

        if self.stats["outputs_generated"]:
            print(f"\n📂 输出文件示例:")
            for file in self.stats["outputs_generated"][:5]:
                print(f"  - {Path(file).name}")
            if len(self.stats["outputs_generated"]) > 5:
                print(f"  ... 还有 {len(self.stats['outputs_generated']) - 5} 个文件")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="AI Video2Text - 智能音视频处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本转录
  python -m src.cli.video2txt_cli -i "/path/to/audio.m4a"
  
  # 完整学习材料生成
  python -m src.cli.video2txt_cli -i "/path/to/video.mp4" \\
    --flashcards --note_xmind \\
    --api_key=sk-xxx --gpt_model=gpt-4
    
  # 批量处理
  python -m src.cli.video2txt_cli -i "/path/to/videos/" --batch
        """,
    )

    # 基本参数
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="输入文件、目录路径或网络URL（支持直链和Bilibili）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="data/outputs",
        help="输出目录路径 (默认: data/outputs)",
    )

    # 语音识别参数
    # "dolphin", "sensevoice", "faster_whisper", "whisper
    parser.add_argument(
        "--voice_mode",
        default="auto",
        choices=["auto", "whisper", "sensevoice", "dolphin", "faster_whisper"],
        help="语音识别模式 (默认: auto)",
    )
    parser.add_argument(
        "--whisper_model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper模型大小 (默认: small)",
    )

    # AI分析参数
    parser.add_argument("--api_key", help="AI API密钥")
    parser.add_argument("--api_base", help="AI API基础URL")
    parser.add_argument(
        "--gpt_model", default="gpt-3.5-turbo", help="AI模型名称 (默认: gpt-3.5-turbo)"
    )

    # 输出格式参数
    parser.add_argument("--flashcards", action="store_true", help="生成学习闪卡")
    parser.add_argument("--note_card", action="store_true", help="生成内容卡片")
    parser.add_argument("--note_xmind", action="store_true", help="生成XMind思维导图")
    parser.add_argument("--note_mmap", action="store_true", help="生成思维导图")

    # 处理选项
    parser.add_argument("--batch", action="store_true", help="批量处理模式")
    parser.add_argument("--no_keyframes", action="store_true", help="跳过关键帧提取")
    parser.add_argument("--verbose", action="store_true", help="详细输出模式")

    return parser


async def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 创建CLI实例
    cli = Video2TextCLI()
    cli.setup_logging(args.verbose)
    cli.start_time = time.time()

    # 打印启动信息
    print("🚀 AI Video2Text CLI v3.0")
    print("=" * 50)
    # 初始化语音识别
    logger.info("🔧 初始化语音识别核心...")
    if not initialize_voice_recognition(args.voice_mode):
        logger.error("❌ 语音识别初始化失败")
        return 1

    logger.info("✅ 语音识别初始化成功")

    # 处理输入
    try:
        await cli.process_batch(args.input, args.output, args)
        cli.print_final_stats()
        return 0

    except KeyboardInterrupt:
        logger.info("⚠️ 用户中断处理")
        return 1
    except Exception as e:
        logger.error(f"❌ 处理过程出错: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
