#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧-时间段精确映射器
根据视频时长和帧提取策略，为每个SRT时间段精确匹配对应的帧图
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameSegmentMapper:
    """帧-时间段精确映射器"""

    def __init__(self):
        self.frame_interval = 2.0  # 每2秒一帧
        logger.info("🎯 帧-时间段映射器初始化完成")

    def generate_enhanced_transcript(
        self,
        transcript_data: Dict[str, Any],
        frame_info: Dict[str, Any],
        output_path: str = None,
    ) -> Dict[str, Any]:
        """
        生成增强版转录JSON，为每个segment添加对应的frame

        Args:
            transcript_data: 原始转录数据
            frame_info: 帧信息
            output_path: 输出路径（可选）

        Returns:
            增强版转录数据
        """
        try:
            # 深拷贝原始数据
            enhanced_data = transcript_data.copy()

            # 获取帧列表
            frames = frame_info.get("frames", [])

            # 🔍 调试日志
            logger.info(
                f"🔍 映射器调试: frame_info键={list(frame_info.keys())}, frames数量={len(frames)}"
            )
            if frame_info:
                logger.info(f"🔍 frame_info样例: {str(frame_info)[:200]}...")

            if not frames:
                logger.warning("📸 没有可用的帧信息，将生成无帧版本")
                return enhanced_data

            # 构建时间 -> 帧文件名的映射
            time_to_frame = self._build_time_frame_mapping(frames)

            # 为每个segment添加对应的frame - 改进版映射策略
            segments = enhanced_data.get("segments", [])
            enhanced_segments = []

            # 🎯 新的智能映射策略：确保帧的合理分布
            used_frames = set()  # 追踪已使用的帧，避免重复

            for i, segment in enumerate(segments):
                enhanced_segment = segment.copy()

                # 计算segment的中间时间点
                start_time = segment.get("start", 0)
                end_time = segment.get("end", start_time + 6)
                mid_time = (start_time + end_time) / 2

                # 🎯 改进的帧选择策略
                selected_frame = self._select_optimal_frame(
                    mid_time, time_to_frame, used_frames, i, len(segments)
                )

                if selected_frame:
                    enhanced_segment["frame"] = f"keyframes/{selected_frame}"
                    used_frames.add(selected_frame)
                    logger.debug(
                        f"🎯 时间段 {start_time:.1f}s-{end_time:.1f}s (中点{mid_time:.1f}s) → {selected_frame}"
                    )
                else:
                    # 如果没找到对应帧，使用封面帧或第一帧
                    cover_frame = frame_info.get("cover_frame")
                    if cover_frame:
                        enhanced_segment["frame"] = (
                            f"keyframes/{Path(cover_frame).name}"
                        )
                    elif frames:
                        enhanced_segment["frame"] = f"keyframes/{Path(frames[0]).name}"

                enhanced_segments.append(enhanced_segment)

            enhanced_data["segments"] = enhanced_segments

            # 添加帧映射统计信息
            enhanced_data["frame_mapping_info"] = {
                "total_segments": len(enhanced_segments),
                "mapped_segments": len([s for s in enhanced_segments if "frame" in s]),
                "frame_interval": self.frame_interval,
                "available_frames": len(frames),
            }

            # 保存到文件
            if output_path:
                self._save_enhanced_transcript(enhanced_data, output_path)

            logger.info(
                f"✅ 增强版转录生成完成：{len(enhanced_segments)}个时间段，{len(frames)}个可用帧"
            )
            return enhanced_data

        except Exception as e:
            logger.error(f"❌ 生成增强版转录失败: {e}")
            return transcript_data

    def _build_time_frame_mapping(self, frames: List) -> Dict[float, str]:
        """构建时间 -> 帧文件名的映射"""
        time_to_frame = {}

        for frame in frames:
            if isinstance(frame, tuple) and len(frame) == 2:
                # 帧提取器返回的格式：(frame_name, timestamp)
                frame_name, timestamp = frame
                if hasattr(timestamp, "total_seconds"):
                    # timedelta对象
                    frame_time = timestamp.total_seconds()
                else:
                    # 可能是数字
                    frame_time = float(timestamp) if timestamp else 0

                time_to_frame[frame_time] = frame_name

            elif isinstance(frame, str):
                # 从文件名解析时间：00_02.jpg → 2.0秒
                frame_path = Path(frame)
                frame_name = frame_path.name

                # 解析格式：mm_ss.jpg
                try:
                    time_part = frame_name.split(".")[0]  # 去掉扩展名
                    if "_" in time_part:
                        minutes, seconds = time_part.split("_")
                        total_seconds = int(minutes) * 60 + int(seconds)
                        time_to_frame[float(total_seconds)] = frame_name
                        logger.debug(f"📊 解析帧: {frame_name} → {total_seconds}s")
                    else:
                        # 如果不是标准格式，尝试直接解析数字
                        logger.warning(f"⚠️ 非标准帧文件名格式: {frame_name}")
                except Exception as e:
                    logger.warning(f"⚠️ 解析帧文件名失败: {frame_name}, {e}")
                    continue

            elif isinstance(frame, dict):
                # 如果是字典格式，尝试从中提取信息
                frame_time = frame.get("timestamp") or frame.get("time", 0)
                frame_name = frame.get("filename") or frame.get("name", "")
                if frame_name and frame_time is not None:
                    time_to_frame[float(frame_time)] = frame_name

        # 🎯 调试信息：显示映射结果
        logger.info(f"📊 构建时间-帧映射：{len(time_to_frame)}个帧")
        if time_to_frame:
            sorted_mapping = sorted(time_to_frame.items())
            logger.info(
                f"📊 帧时间范围: {sorted_mapping[0][0]}s - {sorted_mapping[-1][0]}s"
            )
            if len(sorted_mapping) <= 10:
                for time_sec, frame_name in sorted_mapping:
                    logger.debug(f"   {time_sec}s → {frame_name}")
            else:
                # 只显示前几个和后几个
                for time_sec, frame_name in sorted_mapping[:3]:
                    logger.debug(f"   {time_sec}s → {frame_name}")
                logger.debug(f"   ... ({len(sorted_mapping)-6}个帧) ...")
                for time_sec, frame_name in sorted_mapping[-3:]:
                    logger.debug(f"   {time_sec}s → {frame_name}")

        return time_to_frame

    def _select_optimal_frame(
        self,
        target_time: float,
        time_to_frame: Dict[float, str],
        used_frames: set,
        segment_index: int,
        total_segments: int,
    ) -> Optional[str]:
        """
        智能选择最优帧 - 确保帧的合理分布

        Args:
            target_time: 目标时间点
            time_to_frame: 时间->帧文件名映射
            used_frames: 已使用的帧文件名集合
            segment_index: 当前segment索引
            total_segments: 总segment数量
        """
        if not time_to_frame:
            return None

        # 🎯 策略1：优先选择未使用且最接近的帧
        available_frames = {
            t: f for t, f in time_to_frame.items() if f not in used_frames
        }

        if available_frames:
            # 找到最接近的未使用帧
            closest_time = min(
                available_frames.keys(), key=lambda t: abs(t - target_time)
            )
            if abs(closest_time - target_time) <= 5.0:  # 5秒内的帧都可以接受
                return available_frames[closest_time]

        # 🎯 策略2：如果所有接近的帧都被使用了，使用智能分配
        # 根据segment在整个视频中的相对位置选择帧
        if time_to_frame:
            frame_times = sorted(time_to_frame.keys())

            # 根据segment的相对位置计算应该使用第几个帧
            relative_position = (
                segment_index / max(1, total_segments - 1) if total_segments > 1 else 0
            )
            target_frame_index = int(relative_position * (len(frame_times) - 1))

            # 确保索引有效
            target_frame_index = max(0, min(target_frame_index, len(frame_times) - 1))
            selected_time = frame_times[target_frame_index]

            logger.debug(
                f"🎯 智能分配: segment {segment_index}/{total_segments} → 帧索引{target_frame_index} → 时间{selected_time}s"
            )

            return time_to_frame[selected_time]

        return None

    def _find_closest_frame(
        self, target_time: float, time_to_frame: Dict[float, str]
    ) -> Optional[str]:
        """找到最接近目标时间的帧（保留向后兼容）"""
        if not time_to_frame:
            return None

        # 找到最接近的时间点
        closest_time = min(time_to_frame.keys(), key=lambda t: abs(t - target_time))

        # 如果时间差超过3秒，可能不合适
        if abs(closest_time - target_time) > 3.0:
            logger.debug(
                f"⚠️ 时间差较大: 目标{target_time:.1f}s vs 最近帧{closest_time:.1f}s"
            )

        return time_to_frame[closest_time]

    def _save_enhanced_transcript(
        self, enhanced_data: Dict[str, Any], output_path: str
    ):
        """保存增强版转录到文件"""
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(enhanced_data, f, ensure_ascii=False, indent=2)

            logger.info(f"💾 增强版转录已保存: {output_file}")

        except Exception as e:
            logger.error(f"❌ 保存增强版转录失败: {e}")

    def get_segment_frame_summary(self, enhanced_data: Dict[str, Any]) -> str:
        """获取时间段-帧图映射摘要"""
        segments = enhanced_data.get("segments", [])
        summary_lines = ["### 🎯 时间段-帧图精确映射"]

        for i, segment in enumerate(segments[:10]):  # 只显示前10个
            start = segment.get("start", 0)
            end = segment.get("end", 0)
            text = segment.get("text", "")[:30] + "..."
            frame = segment.get("frame", "无帧")

            summary_lines.append(f"- **{start:.1f}s-{end:.1f}s**: {text} → `{frame}`")

        if len(segments) > 10:
            summary_lines.append(f"- ... 还有 {len(segments) - 10} 个时间段")

        return "\n".join(summary_lines)


def create_frame_segment_mapper() -> FrameSegmentMapper:
    """创建帧-时间段映射器实例"""
    return FrameSegmentMapper()


# 使用示例
if __name__ == "__main__":
    # 测试用例
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 示例数据
    sample_transcript = {
        "text": "测试文本",
        "segments": [
            {"start": 0.0, "end": 6.45, "text": "第一段文本"},
            {"start": 6.45, "end": 12.9, "text": "第二段文本"},
        ],
    }

    sample_frame_info = {
        "frames": ["00_02.jpg", "00_04.jpg", "00_06.jpg", "00_08.jpg"],
        "cover_frame": "00_02.jpg",
    }

    mapper = create_frame_segment_mapper()
    enhanced = mapper.generate_enhanced_transcript(sample_transcript, sample_frame_info)

    print("增强版转录示例:")
    print(json.dumps(enhanced, ensure_ascii=False, indent=2))
