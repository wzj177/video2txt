#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能帧提取服务
支持视频关键帧提取和音频可视化生成
"""

import os
import cv2
import logging
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import datetime

logger = logging.getLogger(__name__)


class FrameExtractor:
    """智能帧提取器"""

    def __init__(self, output_dir: str = "data/outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_video_duration(self, video_path: str) -> float:
        """
        获取视频文件的实际时长（秒）

        Args:
            video_path: 视频文件路径

        Returns:
            视频时长（秒），失败时返回0
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                logger.error(f"无法打开视频文件: {video_path}")
                return 0

            # 获取总帧数和帧率
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            cap.release()

            if fps > 0:
                duration = total_frames / fps
                logger.debug(
                    f"视频时长: {duration:.2f}秒 (总帧数: {total_frames}, FPS: {fps:.2f})"
                )
                return duration
            else:
                logger.error(f"无法获取视频帧率: {video_path}")
                return 0

        except Exception as e:
            logger.error(f"获取视频时长失败: {e}")
            return 0

    def extract_frame_at(
        self, video_path: str, time_seconds: float, output_path: str
    ) -> bool:
        """在指定时间点提取视频帧 - 优化版本，提高图片质量"""
        try:
            cap = cv2.VideoCapture(video_path)
            cap.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
            ret, frame = cap.read()
            if ret:
                # 提高图片质量到95%
                cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            cap.release()
            return ret
        except Exception as e:
            logger.error(f"提取帧失败: {e}")
            return False

    def calculate_optimal_frame_interval(
        self,
        video_duration: float,
        subtitles: List[Dict[str, Any]] = None,
        target_frames: int = 15,
    ) -> float:
        """
        智能计算最优关键帧间隔 - 结合视频时长和字幕内容综合分析

        Args:
            video_duration: 视频时长（秒）
            subtitles: 字幕列表，用于分析内容密度
            target_frames: 目标关键帧数量

        Returns:
            optimal_interval: 最优间隔（秒）
        """
        # 🔧 修复除零错误：确保视频时长大于0
        if video_duration <= 0:
            logger.warning(f"视频时长无效: {video_duration}，使用默认间隔")
            return 5.0  # 默认5秒间隔

        # 基础间隔计算（基于视频时长）- 优化版，确保合理的帧数
        if video_duration <= 60:  # 1分钟内超短视频
            # 确保至少有6-10帧，间隔不超过10秒
            min_frames = max(6, min(10, int(video_duration / 6)))
            base_interval = min(10, video_duration / min_frames)
        elif video_duration <= 300:  # 5分钟内短视频
            # 确保至少有10-15帧
            min_frames = max(10, min(15, int(video_duration / 20)))
            base_interval = max(8, video_duration / min_frames)
        elif video_duration <= 1800:  # 30分钟内中等视频
            # 确保至少有15-20帧
            min_frames = max(15, min(20, int(video_duration / 60)))
            base_interval = max(20, video_duration / min_frames)
        elif video_duration <= 3600:  # 1小时内长视频
            # 确保至少有20-25帧
            min_frames = max(20, min(25, int(video_duration / 120)))
            base_interval = max(30, video_duration / min_frames)
        else:  # 超长视频
            # 确保至少有25-30帧
            min_frames = max(25, min(30, int(video_duration / 180)))
            base_interval = max(60, video_duration / min_frames)

        # 如果没有字幕信息，返回基础间隔
        if not subtitles or len(subtitles) == 0:
            return base_interval

        # 分析字幕密度和内容复杂度
        subtitle_density = len(subtitles) / max(
            video_duration, 1.0
        )  # 每秒字幕数量，避免除零

        # 计算平均字幕长度和内容复杂度
        total_content_length = sum(len(sub.get("content", "")) for sub in subtitles)
        avg_content_length = total_content_length / len(subtitles) if subtitles else 0

        # 识别重要内容关键词密度
        important_keywords = [
            "重要",
            "关键",
            "核心",
            "主要",
            "首先",
            "其次",
            "最后",
            "注意",
            "记住",
            "总结",
            "结论",
            "方法",
            "技巧",
            "步骤",
            "原理",
            "概念",
            "定义",
            "特点",
            "要点",
            "问题",
            "解决",
            "分析",
            "举例",
            "比如",
        ]

        keyword_count = 0
        for sub in subtitles:
            content = sub.get("content", "")
            keyword_count += sum(
                1 for keyword in important_keywords if keyword in content
            )

        keyword_density = keyword_count / len(subtitles) if subtitles else 0

        # 根据内容密度调整间隔
        density_factor = 1.0

        # 高密度内容（教学视频、技术讲解等）需要更多帧
        if subtitle_density > 0.8 and avg_content_length > 15:  # 密集且详细的内容
            density_factor = 0.7  # 减少间隔，增加帧数
        elif subtitle_density > 0.5 and keyword_density > 0.3:  # 中等密度但重要内容多
            density_factor = 0.8
        elif subtitle_density < 0.2 or avg_content_length < 8:  # 稀疏或简短内容
            density_factor = 1.3  # 增加间隔，减少帧数

        # 应用密度调整
        optimized_interval = base_interval * density_factor

        # 确保合理的边界值 - 优化版，保证最小帧数
        # 根据视频时长动态调整最小帧数要求
        if video_duration <= 60:
            min_required_frames = 6
        elif video_duration <= 300:
            min_required_frames = 10
        elif video_duration <= 1800:
            min_required_frames = 15
        else:
            min_required_frames = 20

        min_interval = max(
            3, max(video_duration, 1.0) / (min_required_frames * 1.5)
        )  # 确保最小帧数，避免除零
        max_interval = min(
            60, max(video_duration, 1.0) / max(3, min_required_frames // 2)
        )  # 最大间隔，避免除零

        final_interval = max(min_interval, min(max_interval, optimized_interval))

        return round(final_interval, 1)

    def is_meaningful_content(self, content: str, time_pos: float) -> bool:
        """判断内容是否有意义，用于封面帧选择"""
        content = content.strip()

        # 内容长度过短直接跳过
        if len(content) < 5:
            return False

        # 纯粹的语气词或无意义词汇
        meaningless_words = ["嗯", "呃", "啊", "哦", "嗯嗯", "好", "对", "是的"]
        if content in meaningless_words:
            return False

        # 常见但无关紧要的开场白（但不完全排除，因为有些教学视频直接进入主题）
        weak_openings = ["大家好", "欢迎大家", "今天我们", "hello", "hi"]
        has_weak_opening = any(opening in content for opening in weak_openings)

        # 如果是弱开场白但内容较长，仍然可以作为封面帧
        if has_weak_opening and len(content) < 15:
            return False

        # 检查是否包含实质性内容关键词
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
        ]

        has_content_keyword = any(keyword in content for keyword in content_keywords)

        # 如果时间很早（前10秒）且有实质内容，优先选择
        if time_pos <= 10 and (has_content_keyword or len(content) >= 15):
            return True

        # 其他情况按内容质量判断
        return len(content) >= 10 and (has_content_keyword or not has_weak_opening)

    def extract_frames_from_subtitles(
        self,
        video_path: str,
        subtitles: List[Dict[str, Any]],
        frame_output_dir: str,
        verbose: bool = False,
        min_interval: Optional[float] = None,
        force_interval: Optional[float] = None,  # 🎯 新增：强制间隔参数
    ) -> Tuple[List[Tuple[str, datetime.timedelta]], Optional[str]]:
        """
        根据字幕时间点批量提取关键帧 - 优化版智能选择封面帧和后续关键帧

        Args:
            video_path: 视频文件路径
            subtitles: 字幕列表，每个元素包含start、end、content等字段
            frame_output_dir: 帧输出目录
            verbose: 是否详细输出
            min_interval: 最小间隔时间（秒）

        Returns:
            selected_frames: 选中的帧列表 [(帧文件名, 时间戳)]
            cover_frame: 封面帧文件名
        """
        os.makedirs(frame_output_dir, exist_ok=True)

        if not subtitles:
            return [], None

        # 🎯 直接从视频文件获取时长，而不是依赖SRT
        video_duration = self._get_video_duration(video_path)

        if video_duration <= 0:
            logger.error(f"无法获取视频时长: {video_path}")
            return [], None

        # 🎯 优先使用强制间隔，否则使用动态计算
        if force_interval is not None:
            min_interval = force_interval
            logger.info(f"🎯 使用强制间隔: {force_interval}秒")
        elif min_interval is None:
            min_interval = self.calculate_optimal_frame_interval(
                video_duration, subtitles
            )

        if verbose:
            logger.info(f"🖼️ 开始智能提取关键帧到: {frame_output_dir}")
            logger.info(
                f"   视频时长: {video_duration/60:.1f}分钟，字幕数量: {len(subtitles)}"
            )
            if subtitles:
                subtitle_density = len(subtitles) / max(video_duration, 1.0)  # 避免除零
                logger.info(f"   字幕密度: {subtitle_density:.2f}条/秒")
            logger.info(f"   智能间隔: {min_interval}秒")
            logger.info(
                f"   预计关键帧数量: {int(max(video_duration, 1.0) // min_interval) + 1}"
            )

        selected_frames = []
        last_frame_time = None
        cover_frame = None

        # 寻找封面帧 - 更智能的策略
        cover_candidates = []  # 候选封面帧列表

        for i, sub in enumerate(subtitles):
            current_time = sub["start"].total_seconds()
            content = sub["content"].strip()

            # 只在前60秒内寻找封面帧
            if current_time > 60:
                break

            if self.is_meaningful_content(content, current_time):
                cover_candidates.append((current_time, content, i))

        # 选择最佳封面帧
        if cover_candidates:
            # 优先选择前15秒内的内容，如果没有则选择前30秒，最后选择前60秒
            best_candidate = None

            # 第一优先级：前15秒内的实质内容
            early_candidates = [c for c in cover_candidates if c[0] <= 15]
            if early_candidates:
                # 选择内容最丰富的
                best_candidate = max(early_candidates, key=lambda x: len(x[1]))
            else:
                # 第二优先级：前30秒内的内容
                medium_candidates = [c for c in cover_candidates if c[0] <= 30]
                if medium_candidates:
                    best_candidate = max(medium_candidates, key=lambda x: len(x[1]))
                else:
                    # 第三优先级：前60秒内的内容
                    best_candidate = max(cover_candidates, key=lambda x: len(x[1]))

            if best_candidate:
                current_time, content, sub_index = best_candidate
                minutes = int(current_time) // 60
                seconds = int(current_time) % 60
                frame_name = f"{minutes:02d}_{seconds:02d}.jpg"
                frame_path = os.path.join(frame_output_dir, frame_name)

                if self.extract_frame_at(video_path, current_time, frame_path):
                    cover_frame = frame_name
                    selected_frames.append((frame_name, subtitles[sub_index]["start"]))
                    last_frame_time = current_time
                    if verbose:
                        logger.info(
                            f"   📌 封面帧: {frame_name} (时间: {current_time:.0f}s, 内容: {content[:30]}...)"
                        )

        # 如果没有找到合适的封面帧，使用第一个有内容的字幕
        if cover_frame is None and subtitles:
            first_sub = subtitles[0]
            current_time = first_sub["start"].total_seconds()
            content = first_sub["content"].strip()

            minutes = int(current_time) // 60
            seconds = int(current_time) % 60
            frame_name = f"{minutes:02d}_{seconds:02d}.jpg"
            frame_path = os.path.join(frame_output_dir, frame_name)

            if self.extract_frame_at(video_path, current_time, frame_path):
                cover_frame = frame_name
                selected_frames.append((frame_name, first_sub["start"]))
                last_frame_time = current_time
                if verbose:
                    logger.info(
                        f"   📌 默认封面帧: {frame_name} (内容: {content[:30]}...)"
                    )

        # 继续提取后续关键帧
        for i, sub in enumerate(subtitles):
            current_time = sub["start"].total_seconds()

            # 跳过已经作为封面帧的字幕
            if last_frame_time is not None and abs(current_time - last_frame_time) < 5:
                continue

            # 检查是否达到时间间隔要求
            if (
                last_frame_time is None
                or current_time - last_frame_time >= min_interval
            ):
                # 检查内容重要性（包含关键词的优先）
                important_keywords = [
                    "重要",
                    "关键",
                    "核心",
                    "主要",
                    "首先",
                    "其次",
                    "最后",
                    "注意",
                    "记住",
                    "总结",
                    "结论",
                    "方法",
                    "技巧",
                    "步骤",
                    "但是",
                    "然而",
                    "因此",
                    "所以",
                    "比如",
                    "例如",
                    "那么",
                    "接下来",
                    "现在",
                    "下面",
                    "这里",
                    "这个时候",
                    "特别",
                    "尤其",
                    "务必",
                    "一定要",
                    "千万",
                    "切记",
                    "提醒",
                    "强调",
                ]

                content = sub["content"].strip()
                is_important = any(keyword in content for keyword in important_keywords)

                # 重要内容立即提取，普通内容需要达到时间间隔
                should_extract = False
                if is_important:
                    should_extract = True
                elif (
                    last_frame_time is None
                    or current_time - last_frame_time >= min_interval
                ):
                    should_extract = True

                if should_extract:
                    # 每个SRT片段提取2帧的优化策略
                    start_time = sub["start"].total_seconds()
                    end_time = (
                        sub["end"].total_seconds() if "end" in sub else start_time + 5
                    )
                    segment_duration = end_time - start_time

                    # 根据片段长度决定提取策略
                    frame_times = []
                    if segment_duration >= 4.0:  # 片段长度>=4秒时提取2帧
                        # 第1帧：片段开始后1秒处
                        frame1_time = start_time + 1.0
                        # 第2帧：片段结束前1秒处
                        frame2_time = max(end_time - 1.0, frame1_time + 2.0)
                        frame_times = [frame1_time, frame2_time]
                    elif segment_duration >= 2.0:  # 片段长度>=2秒时提取2帧
                        # 第1帧：片段开始后0.5秒
                        frame1_time = start_time + 0.5
                        # 第2帧：片段结束前0.5秒
                        frame2_time = max(end_time - 0.5, frame1_time + 1.0)
                        frame_times = [frame1_time, frame2_time]
                    else:  # 短片段只取1帧（中间位置）
                        frame_times = [start_time + segment_duration / 2]

                    # 提取所有计划的帧
                    extracted_count = 0
                    for j, frame_time in enumerate(frame_times):
                        minutes = int(frame_time) // 60
                        seconds = int(frame_time) % 60
                        milliseconds = int((frame_time % 1) * 100)

                        # 为每个片段的多帧添加序号
                        if len(frame_times) > 1:
                            frame_name = f"{minutes:02d}_{seconds:02d}_{milliseconds:02d}_{j+1}.jpg"
                        else:
                            frame_name = f"{minutes:02d}_{seconds:02d}.jpg"

                        frame_path = os.path.join(frame_output_dir, frame_name)

                        if self.extract_frame_at(video_path, frame_time, frame_path):
                            selected_frames.append((frame_name, sub["start"]))
                            extracted_count += 1
                            if verbose:
                                importance_mark = "⭐" if is_important else "⏰"
                                frame_pos = f"帧{j+1}" if len(frame_times) > 1 else "帧"
                                logger.info(
                                    f"   提取关键帧 {importance_mark} {frame_pos}: {frame_name} (时间: {frame_time:.1f}s)"
                                )

                    # 更新最后提取时间为最后一帧的时间
                    if extracted_count > 0:
                        last_frame_time = frame_times[-1]

        if verbose:
            logger.info(
                f"✅ 共提取 {len(selected_frames)} 个优化关键帧 (原始字幕: {len(subtitles)})"
            )
            if cover_frame:
                logger.info(f"   🎯 封面帧: {cover_frame}")

        return selected_frames, cover_frame

    def extract_frames_by_interval(
        self,
        video_path: str,
        subtitles: List[Dict[str, Any]],
        frame_output_dir: str,
        interval: float = 2.0,
        verbose: bool = False,
    ) -> Tuple[List[Tuple[str, datetime.timedelta]], Optional[str]]:
        """
        🎯 按固定间隔提取关键帧 - 简化版本，确保稳定的帧数量

        Args:
            video_path: 视频文件路径
            subtitles: 字幕列表（可选，不用于时长计算）
            frame_output_dir: 帧输出目录
            interval: 提取间隔（秒），默认2秒
            verbose: 是否详细输出

        Returns:
            selected_frames: 选中的帧列表 [(帧文件名, 时间戳)]
            cover_frame: 封面帧文件名
        """
        os.makedirs(frame_output_dir, exist_ok=True)

        # 🎯 直接从视频文件获取时长，而不是依赖SRT
        video_duration = self._get_video_duration(video_path)

        if video_duration <= 0:
            logger.error(f"无法获取视频时长: {video_path}")
            return [], None

        if verbose:
            logger.info(f"🎯 开始固定间隔提取关键帧到: {frame_output_dir}")
            logger.info(f"   视频时长: {video_duration/60:.1f}分钟")
            logger.info(f"   提取间隔: {interval}秒，从第2秒开始")
            logger.info(
                f"   预计关键帧数量: {int((video_duration - 2) // interval) + 1}"
            )

        selected_frames = []
        cover_frame = None

        # 按固定间隔提取帧，从第2秒开始（跳过开头的黑屏或无内容画面）
        current_time = 2.0  # 🎯 从2秒开始，跳过0秒的黑屏
        frame_index = 0

        while current_time <= video_duration:
            minutes = int(current_time) // 60
            seconds = int(current_time) % 60
            milliseconds = int((current_time % 1) * 100)

            # 生成帧文件名（所有帧都使用统一格式）
            frame_name = f"{minutes:02d}_{seconds:02d}.jpg"

            frame_path = os.path.join(frame_output_dir, frame_name)

            # 提取帧
            if self.extract_frame_at(video_path, current_time, frame_path):
                # 创建时间戳对象
                timestamp = datetime.timedelta(seconds=current_time)
                selected_frames.append((frame_name, timestamp))

                # 第一个成功提取的帧作为封面帧
                if cover_frame is None:
                    cover_frame = frame_name

                if verbose:
                    logger.info(
                        f"   ✅ 提取帧 {frame_index + 1}: {frame_name} (时间: {current_time:.1f}s)"
                    )

                frame_index += 1
            else:
                if verbose:
                    logger.warning(
                        f"   ❌ 提取帧失败: {frame_name} (时间: {current_time:.1f}s)"
                    )

            # 下一个时间点
            current_time += interval

        if verbose:
            logger.info(f"✅ 固定间隔提取完成: 共提取 {len(selected_frames)} 个关键帧")
            if cover_frame:
                logger.info(f"   🎯 封面帧: {cover_frame}")

        return selected_frames, cover_frame

    def generate_audio_visualizations(
        self, audio_path: str, frame_dir: str, verbose: bool = False
    ) -> Tuple[List[Tuple[str, Optional[datetime.timedelta]]], Optional[str]]:
        """为音频文件创建可视化图像"""
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            import librosa
            import soundfile as sf
        except ImportError:
            logger.warning("⚠️ 需要安装matplotlib、librosa、soundfile来生成音频可视化")
            return [], None

        os.makedirs(frame_dir, exist_ok=True)

        if verbose:
            logger.info("🎵 正在为音频文件生成可视化图像...")

        # 生成波形图
        waveform_path = os.path.join(frame_dir, "waveform.jpg")
        waveform_success = self._generate_audio_waveform(audio_path, waveform_path)

        # 生成频谱图
        spectrogram_path = os.path.join(frame_dir, "spectrogram.jpg")
        spectrogram_success = self._generate_audio_spectrogram(
            audio_path, spectrogram_path
        )

        # 返回生成的图像列表
        generated_images = []
        if waveform_success:
            generated_images.append(("waveform.jpg", None))
            if verbose:
                logger.info("   ✅ 波形图生成完成")
        if spectrogram_success:
            generated_images.append(("spectrogram.jpg", None))
            if verbose:
                logger.info("   ✅ 频谱图生成完成")

        if not generated_images and verbose:
            logger.warning("   ⚠️ 未能生成音频可视化图像")

        return generated_images, "waveform.jpg" if waveform_success else None

    def _generate_audio_waveform(self, audio_path: str, output_path: str) -> bool:
        """为音频文件生成波形图"""
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            import librosa

            plt.rcParams["font.sans-serif"] = ["SimHei", "Arial Unicode MS"]
            plt.rcParams["axes.unicode_minus"] = False
            plt.rcParams["figure.figsize"] = (12, 8)

            # 加载音频文件
            y, sr = librosa.load(audio_path, duration=None)

            # 创建波形图
            plt.figure(figsize=(12, 4))
            time = np.linspace(0, len(y) / sr, len(y))
            plt.plot(time, y, alpha=0.6)
            plt.xlabel("时间 (秒)")
            plt.ylabel("幅度")
            plt.title("音频波形图")
            plt.grid(True, alpha=0.3)

            # 保存图像
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()

            return True
        except Exception as e:
            logger.error(f"生成波形图失败: {e}")
            return False

    def _generate_audio_spectrogram(self, audio_path: str, output_path: str) -> bool:
        """为音频文件生成频谱图"""
        try:
            import matplotlib.pyplot as plt
            import numpy as np
            import librosa

            # 加载音频文件
            y, sr = librosa.load(audio_path, duration=None)

            # 计算梅尔频谱图
            S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
            S_dB = librosa.power_to_db(S, ref=np.max)

            # 创建频谱图
            plt.figure(figsize=(12, 6))
            librosa.display.specshow(S_dB, sr=sr, x_axis="time", y_axis="mel")
            plt.colorbar(format="%+2.0f dB")
            plt.title("音频频谱图")
            plt.tight_layout()

            # 保存图像
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()

            return True
        except Exception as e:
            logger.error(f"生成频谱图失败: {e}")
            return False


# 便捷函数
def create_frame_extractor(output_dir: str = "data/outputs") -> FrameExtractor:
    """创建帧提取器实例"""
    return FrameExtractor(output_dir)


def extract_video_frames(
    video_path: str,
    subtitles: List[Dict[str, Any]],
    output_dir: str,
    verbose: bool = False,
) -> Tuple[List[Tuple[str, datetime.timedelta]], Optional[str]]:
    """提取视频关键帧的便捷函数"""
    extractor = create_frame_extractor()
    return extractor.extract_frames_from_subtitles(
        video_path, subtitles, output_dir, verbose
    )


def generate_audio_visuals(
    audio_path: str, output_dir: str, verbose: bool = False
) -> Tuple[List[Tuple[str, Optional[datetime.timedelta]]], Optional[str]]:
    """生成音频可视化的便捷函数"""
    extractor = create_frame_extractor()
    return extractor.generate_audio_visualizations(audio_path, output_dir, verbose)
