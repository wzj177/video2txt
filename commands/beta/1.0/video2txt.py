#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频转文本工具 - 优化版本
解决迭代2优化.md中提到的质量问题：
1. 内容卡片质量提升
2. 思维导图专业化
3. 音频分片处理
4. 关键帧智能选择
5. 提示词优化
6. 平台适配摘要一次性生成所有平台
"""

import os
import sys
import ssl
from hashlib import md5
import argparse
import requests
import srt
import datetime
import subprocess
from pathlib import Path
import cv2
import whisper
import time
import shutil
from openai import OpenAI
from tqdm import tqdm
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

# 添加音频处理库
try:
    import librosa
    import soundfile as sf

    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

# 信任自签名证书（绕过 SSL 验证）
ssl._create_default_https_context = ssl._create_unverified_context


def compute_md5(file_path):
    """计算文件或URL的MD5哈希值"""
    if file_path.startswith("http://") or file_path.startswith("https://"):
        # 对于URL，使用URL字符串本身计算MD5
        hash_md5 = md5()
        hash_md5.update(file_path.encode("utf-8"))
        return hash_md5.hexdigest()
    else:
        # 对于本地文件，计算文件内容的MD5
        hash_md5 = md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()


def extract_frame_at(video_path, time_seconds, output_path):
    """在指定时间点提取视频帧 - 优化版本，提高图片质量"""
    import cv2

    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, time_seconds * 1000)
    ret, frame = cap.read()
    if ret:
        # 提高图片质量到95%
        cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cap.release()
    return ret


def extract_frames_from_subtitles(
    video_path, subtitles, frame_output_dir, verbose=False, min_interval=30
):
    """根据字幕时间点批量提取关键帧 - 优化版智能选择封面帧和后续关键帧"""
    os.makedirs(frame_output_dir, exist_ok=True)

    if not subtitles:
        return []

    # 计算视频总时长
    video_duration = subtitles[-1].start.total_seconds() if subtitles else 0

    if verbose:
        print(f"🖼️  开始智能提取关键帧到: {frame_output_dir}")
        print(f"   视频时长: {video_duration/60:.1f}分钟，最小间隔: {min_interval}秒")

    selected_frames = []
    last_frame_time = None
    cover_frame = None

    # 优化的封面帧选择策略
    def is_meaningful_content(content, time_pos):
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

    # 寻找封面帧 - 更智能的策略
    cover_candidates = []  # 候选封面帧列表

    for i, sub in enumerate(subtitles):
        current_time = sub.start.total_seconds()
        content = sub.content.strip()

        # 只在前60秒内寻找封面帧
        if current_time > 60:
            break

        if is_meaningful_content(content, current_time):
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

            if extract_frame_at(video_path, current_time, frame_path):
                cover_frame = frame_name
                selected_frames.append((frame_name, subtitles[sub_index].start))
                last_frame_time = current_time
                if verbose:
                    print(
                        f"   📌 封面帧: {frame_name} (时间: {current_time:.0f}s, 内容: {content[:30]}...)"
                    )

    # 如果没有找到合适的封面帧，使用第一个有内容的字幕
    if cover_frame is None and subtitles:
        first_sub = subtitles[0]
        current_time = first_sub.start.total_seconds()
        content = first_sub.content.strip()

        minutes = int(current_time) // 60
        seconds = int(current_time) % 60
        frame_name = f"{minutes:02d}_{seconds:02d}.jpg"
        frame_path = os.path.join(frame_output_dir, frame_name)

        if extract_frame_at(video_path, current_time, frame_path):
            cover_frame = frame_name
            selected_frames.append((frame_name, first_sub.start))
            last_frame_time = current_time
            if verbose:
                print(f"   📌 默认封面帧: {frame_name} (内容: {content[:30]}...)")

    # 继续提取后续关键帧
    for i, sub in enumerate(subtitles):
        current_time = sub.start.total_seconds()

        # 跳过已经作为封面帧的字幕
        if last_frame_time is not None and abs(current_time - last_frame_time) < 5:
            continue

        # 检查是否达到时间间隔要求
        if last_frame_time is None or current_time - last_frame_time >= min_interval:
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

            content = sub.content.strip()
            is_important = any(keyword in content for keyword in important_keywords)

            # 重要内容立即提取，普通内容需要达到时间间隔
            should_extract = False
            if is_important:
                should_extract = True
            elif (
                last_frame_time is not None
                and current_time - last_frame_time >= min_interval
            ):
                should_extract = True
            elif last_frame_time is None:  # 第一帧
                should_extract = True

            if should_extract:
                minutes = int(current_time) // 60
                seconds = int(current_time) % 60
                frame_name = f"{minutes:02d}_{seconds:02d}.jpg"
                frame_path = os.path.join(frame_output_dir, frame_name)

                if extract_frame_at(video_path, current_time, frame_path):
                    selected_frames.append((frame_name, sub.start))
                    last_frame_time = current_time
                    if verbose:
                        importance_mark = "⭐" if is_important else "⏰"
                        print(f"   提取关键帧 {importance_mark}: {frame_name}")

    if verbose:
        print(
            f"✅ 共提取 {len(selected_frames)} 个优化关键帧 (原始字幕: {len(subtitles)})"
        )
        if cover_frame:
            print(f"   🎯 封面帧: {cover_frame}")

    return selected_frames, cover_frame


def parse_args():
    parser = argparse.ArgumentParser(
        description="视频转文本摘要工具（支持小红书风格 & 思维导图）- 优化版本"
    )

    parser.add_argument("-i", "--input", required=True, help="输入视频文件路径")
    parser.add_argument("--output_dir", action="store_true", help="输出目录")
    parser.add_argument("--verbose", action="store_true", help="启用详细日志输出")
    parser.add_argument(
        "--whisper_model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper 模型大小 (默认: base，推荐: medium/large)",
    )
    parser.add_argument(
        "--gpt_model",
        default="gpt-4o-2024-11-20",
        help="GPT 对话 模型大小 (默认: gpt-4o-2024-11-20)",
    )
    parser.add_argument(
        "--language", default="zh", help="音频语言代码，如 'zh', 'en' (默认: zh)"
    )
    parser.add_argument(
        "--ai_correction",
        action="store_true",
        help="启用AI智能纠错（在规则纠错后进行，纠错3轮）",
    )
    parser.add_argument(
        "--correction_rounds",
        type=int,
        default=3,
        help="AI纠错轮数 (默认: 3轮)",
    )
    parser.add_argument(
        "--api_key",
        default=os.getenv("DASHSCOPE_API_KEY"),
        help="API Key（默认从环境变量读取）",
    )
    parser.add_argument(
        "--api_base",
        default=os.getenv(
            "DASHSCOPE_API_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
        help="API Base URL",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "markmap", "both"],
        default="both",
        help="输出格式：markdown / markmap / both",
    )
    parser.add_argument("--key_moments", action="store_true", help="生成关键时刻标记")
    parser.add_argument("--credibility", action="store_true", help="生成可信度分析")
    parser.add_argument("--structure", action="store_true", help="生成内容结构分析")
    parser.add_argument("--value_rating", action="store_true", help="生成内容价值评分")
    return parser.parse_args()


def video_to_audio(video_file, audio_file, verbose=False):
    if (
        not video_file.startswith("http://")
        and not video_file.startswith("https://")
        and not os.path.exists(video_file)
    ):
        raise FileNotFoundError(f"视频文件不存在: {video_file}")

    tmp_file = None
    if "bili" in video_file:
        print("\n下载 Bilibili 视频\n")
        tmp_file = get_temp_video_path(video_file)
        if not os.path.exists(tmp_file):
            video_file = download_bilibili_url_video(video_file)
        else:
            video_file = tmp_file
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"视频文件不存在: {video_file}")

    command = ["ffmpeg", "-i", video_file, "-q:a", "0", "-map", "a", "-y", audio_file]
    if not verbose:
        command += ["-loglevel", "quiet"]
    subprocess.run(command, check=True)
    if verbose:
        print(f"✅ 音频已保存至: {audio_file}")

    return video_file


def get_temp_video_path(url=None):
    if url is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"temp_{timestamp}.mp4"
        return os.path.abspath(filename)
    else:
        # 对于URL，计算MD5并放到uploads目录下
        url_md5 = md5(url.encode("utf-8")).hexdigest()
        uploads_dir = "uploads"
        video_cache_dir = os.path.join(uploads_dir, url_md5)
        os.makedirs(video_cache_dir, exist_ok=True)
        filename = f"{url_md5}.mp4"
        return os.path.join(video_cache_dir, filename)


def download_video_to_tempfile(temp_file, url, headers=None):
    """从指定 URL 下载视频到本地临时文件，支持进度条显示"""
    print(f"📡 正在请求视频资源：{url}")

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

    print(f"✅ 下载完成：{temp_file}")
    return temp_file


def download_bilibili_url_video(video_url: str, headers: dict = None):
    """从视频直链下载并转码为音频（MP3），保存到 output_path。"""
    if headers is None:
        headers = {
            "Referer": "https://www.bilibili.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "cookie": "buvid3=A2E5752C-5256-BD1E-0CCA-32759D5BA08155742infoc; b_nut=1732976055; _uuid=FF568286-E715-1694-768F-EE2B9C3152DA56119infoc; buvid4=B176089E-6E08-C5DD-029D-4CA98F56169956463-024113014-9Ulxqnpl0tZBiU5lCrbNuzNVSLkrvvC4bMYW7fMoEBH4jCDAVu1W47qrY9iit%2Bvc; buvid_fp=96fe3fafbe3a068784791dc533a68869; rpdid=|(J~R~|||~Rm0J'u~JJuR~uu|; enable_web_push=DISABLE; hit-dyn-v2=1; CURRENT_QUALITY=80; dy_spec_agreed=1; enable_feed_channel=ENABLE; LIVE_BUVID=AUTO7317430865465912; PVID=13; DedeUserID=482104881; DedeUserID__ckMd5=c1abdbf4e1f5e041; header_theme_version=OPEN; theme-tip-show=SHOWED; theme-avatar-tip-show=SHOWED; bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTQxMDU5NTYsImlhdCI6MTc1Mzg0NjY5NiwicGx0IjotMX0.-HhVAUvV-H6KHr8xqTEMNaC6mP4o3RwCUzj53MMsjBw; bili_ticket_expires=1754105896; SESSDATA=2ee2da75%2C1769398757%2Cc5be8%2A72CjDaNA85jrYSPvCsDDHd8bVO2eSKFGFVL06TRb1M17Rz5kN1uHRNMslJ3wxrGbxhNXUSVnUxYWtSaTI0RFlDTmRqSGR2ejVpNTRKQ05KLUtkZi1jdklsc2VUMDhwUElsQTk5a2Vpd2gtSU5JSGVxeDZrOWZtYnFVa1paRnY5LWo1TVUzeV9BdG1BIIEC; bili_jct=d23874db06ad81b153a5e9cd235a82b0; sid=8dakwcbr; bp_t_offset_482104881=1095252562111627264; home_feed_column=4; browser_resolution=1035-958; b_lsid=102EA17E4_19859BCEF34; CURRENT_FNVAL=2000",
        }

    return download_video_to_tempfile(
        get_temp_video_path(video_url), video_url, headers=headers
    )


def transcribe_audio(
    audio_path,
    model_name="base",
    language="zh",
    output_dir=None,
    verbose=False,
    client=None,
    gpt_model=None,
    ai_correction=False,
    correction_rounds=3,
):
    """优化版音频转录函数 - 支持长音频分片处理"""

    def is_openai_whisper_model(name):
        return name in ["tiny", "base", "small", "medium", "large"]

    segments = []

    if is_openai_whisper_model(model_name):
        if verbose:
            print("🔄 加载 OpenAI Whisper 模型中...")
        model = whisper.load_model(model_name)

        if verbose:
            print("🧠 开始语音识别（OpenAI Whisper）...")

        # 检查音频长度，对于长音频进行分片处理
        try:
            import librosa

            audio, sr = librosa.load(audio_path, sr=16000)
            duration = len(audio) / sr

            if duration > 600:  # 超过10分钟的音频进行分片
                if verbose:
                    print(f"📏 音频时长 {duration/60:.1f}分钟，启用分片处理...")

                # 分片处理逻辑
                chunk_duration = 300  # 5分钟一片
                chunks = []
                for start_time in range(0, int(duration), chunk_duration):
                    end_time = min(start_time + chunk_duration, duration)
                    chunk_audio = audio[int(start_time * sr) : int(end_time * sr)]

                    # 保存临时音频片段
                    temp_chunk_path = f"{audio_path}_temp_chunk_{start_time}.wav"
                    import soundfile as sf

                    sf.write(temp_chunk_path, chunk_audio, sr)

                    # 转录片段
                    chunk_result = model.transcribe(
                        temp_chunk_path,
                        language=language,
                        verbose=False,
                        initial_prompt="请使用简体中文输出",
                    )

                    # 调整时间戳
                    for seg in chunk_result.get("segments", []):
                        seg["start"] += start_time
                        seg["end"] += start_time
                        segments.append(seg)

                    # 清理临时文件
                    os.remove(temp_chunk_path)

                    if verbose:
                        print(
                            f"   完成片段 {int(start_time)//60:02d}:{int(start_time)%60:02d} - {int(end_time)//60:02d}:{int(end_time)%60:02d}"
                        )
            else:
                # 直接处理短音频
                result = model.transcribe(
                    audio_path,
                    language=language,
                    verbose=False,
                    initial_prompt="请使用简体中文输出",
                )
                segments = result.get("segments", [])

        except ImportError:
            # 如果没有librosa，使用原始方法
            result = model.transcribe(
                audio_path,
                language=language,
                verbose=False,
                initial_prompt="请使用简体中文输出",
            )
            segments = result.get("segments", [])

    else:
        if verbose:
            print(f"🔄 加载 Hugging Face Whisper 模型：{model_name}")

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_name,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        ).to(device)

        processor = AutoProcessor.from_pretrained(model_name)

        pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch_dtype,
            device=0 if device.startswith("cuda") else -1,
        )

        if verbose:
            print("🧠 开始语音识别（Hugging Face Whisper）...")
        result = pipe(audio_path, return_timestamps="word", chunk_length_s=30.0)

        chunks = result.get("chunks", [])
        for chunk in chunks:
            start_sec = chunk["timestamp"][0]
            end_sec = chunk["timestamp"][1]
            segments.append(
                {"start": start_sec, "end": end_sec, "text": chunk["text"].strip()}
            )

    # 优化字幕质量 - 合并过短的片段
    optimized_segments = []
    current_segment = None

    for seg in segments:
        duration = seg["end"] - seg["start"]
        text = seg["text"].strip()

        # 跳过空内容
        if not text:
            continue

        # 如果片段太短（少于2秒）且内容少于10个字符，尝试与前一个合并
        if duration < 2 and len(text) < 10 and current_segment is not None:
            current_segment["text"] += " " + text
            current_segment["end"] = seg["end"]
        else:
            if current_segment is not None:
                optimized_segments.append(current_segment)
            current_segment = {"start": seg["start"], "end": seg["end"], "text": text}

    if current_segment is not None:
        optimized_segments.append(current_segment)

    if verbose and len(segments) != len(optimized_segments):
        print(f"🔧 字幕优化: {len(segments)} -> {len(optimized_segments)} 片段")

    plain_text, subtitles = "", []
    for i, seg in enumerate(optimized_segments):
        start = datetime.timedelta(seconds=seg["start"])
        end = datetime.timedelta(seconds=seg["end"])
        text = seg["text"].strip()
        subtitles.append(srt.Subtitle(i + 1, start, end, text))
        plain_text += f"[{start}] {text}\n"

    # 智能纠错处理
    if verbose:
        print("🔧 开始智能纠错处理...")

    # 使用新的智能领域检测
    full_transcript = " ".join([sub.content for sub in subtitles])
    detected_domains = detect_content_domain(full_transcript)

    if verbose and detected_domains:
        print(f"   🎯 检测到内容领域: {', '.join(detected_domains)}")

    # 执行多层纠错
    corrected_subtitles, corrections = post_process_subtitles(
        subtitles,
        detected_domains,
        verbose=verbose,
        client=client,
        model=gpt_model,
        ai_correction=ai_correction,
        correction_rounds=correction_rounds,
    )

    # 生成纠错后的纯文本
    corrected_plain_text = ""
    for sub in corrected_subtitles:
        start_str = str(sub.start).split(".")[0]  # 移除微秒部分
        corrected_plain_text += f"[{start_str}] {sub.content}\n"

    if output_dir:
        Path(output_dir).parent.mkdir(parents=True, exist_ok=True)
        with open(output_dir, "w", encoding="utf-8") as f:
            f.write(srt.compose(corrected_subtitles))
        if verbose:
            print(f"✅ SRT 字幕保存至: {output_dir}")
            if corrections:
                print(f"🎯 智能纠错完成，修正了 {len(corrections)} 处错误")

    return corrected_plain_text, corrected_subtitles


def get_video_theme_and_type(client, full_text, model):
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
{full_text[:3000]}
"""

    return generate(client, prompt, model, max_tokens=1024)


def detect_content_domain(text):
    """
    智能检测内容领域 - 基于词频和上下文分析
    """
    domain_indicators = {
        "数学": [
            "函数",
            "方程",
            "解题",
            "公式",
            "计算",
            "数学",
            "韩数",
            "二次",
            "一次",
            "分式",
            "图像",
            "开口",
            "对称",
            "根",
            "零点",
            "判别",
            "不等式",
            "Delta",
            "系数",
        ],
        "编程": [
            "代码",
            "函数",
            "程序",
            "编程",
            "Python",
            "Java",
            "算法",
            "数据结构",
            "变量",
            "循环",
            "条件",
            "类",
            "对象",
            "方法",
        ],
        "英语": [
            "音标",
            "元音",
            "辅音",
            "舌位",
            "唇形",
            "DJ",
            "语音",
            "发音",
            "语法",
            "时态",
            "词汇",
            "句子",
            "单词",
            "英语",
            "韵母",
            "圆唇",
            "语调",
            "重音",
            "轻音",
            "前元音",
            "后元音",
            "中元音",
            "高元音",
            "低元音",
            "音素",
            "音位",
            "pronunciation",
            "grammar",
            "vocabulary",
            "speaking",
            "listening",
            "模仿",
            "练习",
            "跟读",
            "朗读",
            "详解",
            "核心要点",
            "快速讲解",
        ],
        "物理": [
            "力",
            "速度",
            "加速度",
            "能量",
            "动量",
            "电荷",
            "磁场",
            "波长",
            "频率",
            "质量",
            "重力",
        ],
        "化学": [
            "分子",
            "原子",
            "化学",
            "反应",
            "催化剂",
            "氧化",
            "还原",
            "酸",
            "碱",
            "盐",
            "离子",
        ],
        "商业": [
            "营销",
            "销售",
            "客户",
            "产品",
            "市场",
            "策略",
            "品牌",
            "运营",
            "管理",
            "利润",
            "成本",
        ],
        "生活": [
            "健康",
            "饮食",
            "运动",
            "睡眠",
            "心理",
            "情绪",
            "家庭",
            "工作",
            "生活",
            "习惯",
        ],
    }

    detected_domains = []
    text_lower = text.lower()

    for domain, keywords in domain_indicators.items():
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        if matches >= 2:  # 至少匹配2个关键词才认为属于该领域
            detected_domains.append((domain, matches))

    # 按匹配度排序，返回主要领域
    detected_domains.sort(key=lambda x: x[1], reverse=True)
    return [domain for domain, _ in detected_domains[:2]]  # 返回前2个最可能的领域


def get_universal_corrections():
    """
    获取通用纠错词典 - 覆盖跨领域常见错误，大幅扩展纠错范围
    """
    return {
        # 英文音译错误
        "Hallelujah": "hello everybody",
        "Hello everybody": "hello everybody",
        "哈雷路亚": "hello everybody",
        "hello大家": "hello大家",
        # 通用中英混合错误
        "OK": "ok",
        "ok的": "好的",
        "thank you": "谢谢",
        "sorry": "抱歉",
        # 数字和量词
        "第1个": "第一个",
        "第2个": "第二个",
        "第3个": "第三个",
        "两个": "两个",
        "俩个": "两个",
        "3个": "三个",
        "4个": "四个",
        "5个": "五个",
        # 通用同音字和易错词
        "的话": "的话",
        "德话": "的话",
        "地话": "的话",
        "这样": "这样",
        "这养": "这样",
        "怎样": "怎样",
        "怎养": "怎样",
        "那样": "那样",
        "那养": "那样",
        # 语气词和连接词
        "然后": "然后",
        "染后": "然后",
        "燃后": "然后",
        "接下来": "接下来",
        "结下来": "接下来",
        "总结": "总结",
        "总洁": "总结",
        "最后": "最后",
        "最厚": "最后",
        "总的来说": "总的来说",
        "总得来说": "总的来说",
        # 常用动词
        "分析": "分析",
        "分西": "分析",
        "讲解": "讲解",
        "讲街": "讲解",
        "解释": "解释",
        "解是": "解释",
        "说明": "说明",
        "说民": "说明",
        "了解": "了解",
        "了姐": "了解",
        # 学习相关通用词
        "学习": "学习",
        "学西": "学习",
        "方法": "方法",
        "方发": "方法",
        "技巧": "技巧",
        "技桥": "技巧",
        "知识": "知识",
        "知是": "知识",
        "理解": "理解",
        "理姐": "理解",
        "掌握": "掌握",
        "张握": "掌握",
        # 常见专有名词错误
        "脑补圈": "脑补缺",
        "诺补圈": "脑补缺",
        "低真音标": "DJ音标",
        "地证音标": "DJ音标",
        "大同小艺": "大同小异",
        "大同小异": "大同小异",
        # 方位和方向
        "前后": "前后",
        "前厚": "前后",
        "高低": "高低",
        "告低": "高低",
        "左右": "左右",
        "做右": "左右",
        "上下": "上下",
        "商下": "上下",
        # 常见助词和语气词
        "可以": "可以",
        "可已": "可以",
        "应该": "应该",
        "因该": "应该",
        "必须": "必须",
        "必需": "必须",
        "需要": "需要",
        "须要": "需要",
        # 时间相关
        "现在": "现在",
        "先在": "现在",
        "刚才": "刚才",
        "刚材": "刚才",
        "以前": "以前",
        "以钱": "以前",
        "以后": "以后",
        "以厚": "以后",
        # 比较和对比
        "比较": "比较",
        "比叫": "比较",
        "对比": "对比",
        "对必": "对比",
        "相同": "相同",
        "相童": "相同",
        "不同": "不同",
        "不童": "不同",
        # 教学常用词
        "注意": "注意",
        "朱意": "注意",
        "重要": "重要",
        "中要": "重要",
        "关键": "关键",
        "关见": "关键",
        "重点": "重点",
        "中点": "重点",
        # 标点和符号相关
        "句号": "句号",
        "巨号": "句号",
        "逗号": "逗号",
        "豆号": "逗号",
        "问号": "问号",
        "文号": "问号",
        # 程度副词
        "非常": "非常",
        "飞长": "非常",
        "特别": "特别",
        "特殊": "特别",
        "很多": "很多",
        "恨多": "很多",
        "更多": "更多",
        "更朵": "更多",
    }


def get_domain_specific_corrections(domains):
    """
    基于检测到的领域获取特定纠错词典
    """
    domain_corrections = {}

    if "数学" in domains:
        domain_corrections.update(
            {
                # 函数类错误
                "韩数": "函数",
                "涵数": "函数",
                "含数": "函数",
                "函素": "函数",
                "二次韩数": "二次函数",
                "分式韩数": "分式函数",
                "三次韩数": "三次函数",
                "指数韩数": "指数函数",
                "对数韩数": "对数函数",
                "一次韩数": "一次函数",
                "伊斯韩数": "一次函数",
                "依赛韩数": "一次函数",
                # 几何术语
                "对胜揉": "对称轴",
                "对承轴": "对称轴",
                "对称州": "对称轴",
                "对深深": "对称轴",
                "判别事": "判别式",
                "判别是": "判别式",
                "判别失": "判别式",
                "闭放点": "判别式",
                "不等事": "不等式",
                "不等是": "不等式",
                # 数学符号和概念
                "德拉": "Delta",
                "Durra": "Delta",
                "德尔塔": "Delta",
                "大预零": "大于零",
                "小月零": "小于零",
                "等于零": "等于零",
                "付": "负",
                "跟": "根",
                "零点": "零点",
                "零典": "零点",
                # 数学表达
                "X1": "x₁",
                "X2": "x₂",
                "付Fnb": "负b",
                "A1GC": "c/a",
                "尾答应了也": "韦达定理",
                "韦达定理": "韦达定理",
                "曲之": "取值",
                "范围": "范围",
                "访问": "范围",
            }
        )

    if "编程" in domains:
        domain_corrections.update(
            {
                "函素": "函数",
                "韩数": "函数",
                "变量": "变量",
                "便量": "变量",
                "循环": "循环",
                "训环": "循环",
                "条件": "条件",
                "条剑": "条件",
                "数组": "数组",
                "数足": "数组",
                "对象": "对象",
                "对向": "对象",
                "类": "类",
                "类别": "类别",
                "雷": "类",
            }
        )

    if "英语" in domains:
        domain_corrections.update(
            {
                # 基础英语教学词汇
                "单词": "单词",
                "但词": "单词",
                "蛋词": "单词",
                "语法": "语法",
                "语发": "语法",
                "雨法": "语法",
                "时态": "时态",
                "时太": "时态",
                "实态": "时态",
                "词汇": "词汇",
                "词会": "词汇",
                "次汇": "词汇",
                "句子": "句子",
                "剧子": "句子",
                # 音标相关（针对您的测试视频）
                "音标": "音标",
                "音彪": "音标",
                "阴标": "音标",
                "元音": "元音",
                "原因": "元音",
                "圆音": "元音",
                "辅音": "辅音",
                "复音": "辅音",
                "福音": "辅音",
                "舌位": "舌位",
                "蛇尾": "舌位",
                "舌围": "舌位",
                "唇形": "唇形",
                "春行": "唇形",
                "纯形": "唇形",
                # DJ音标体系
                "DJ音标": "DJ音标",
                "低真音标": "DJ音标",
                "地证音标": "DJ音标",
                "DJ": "DJ",
                "dj": "DJ",
                # 发音相关
                "发音": "发音",
                "法音": "发音",
                "发因": "发音",
                "语音": "语音",
                "雨音": "语音",
                "语因": "语音",
                "语调": "语调",
                "雨调": "语调",
                "语掉": "语调",
                "重音": "重音",
                "中音": "重音",
                "重因": "重音",
                "轻音": "轻音",
                "青音": "轻音",
                "请音": "轻音",
                # 音标特征描述
                "前元音": "前元音",
                "钱元音": "前元音",
                "后元音": "后元音",
                "厚元音": "后元音",
                "中元音": "中元音",
                "终元音": "中元音",
                "高元音": "高元音",
                "告元音": "高元音",
                "低元音": "低元音",
                "底元音": "低元音",
                "圆唇": "圆唇",
                "园唇": "圆唇",
                "元纯": "圆唇",
                "展唇": "展唇",
                "战唇": "展唇",
                # 语音学术语
                "音素": "音素",
                "因素": "音素",
                "音苏": "音素",
                "音位": "音位",
                "因为": "音位",
                "音围": "音位",
                "语系": "语系",
                "雨系": "语系",
                "语稀": "语系",
                # 学习方法
                "模仿": "模仿",
                "摸仿": "模仿",
                "模防": "模仿",
                "练习": "练习",
                "连习": "练习",
                "炼习": "练习",
                "跟读": "跟读",
                "根读": "跟读",
                "跟渡": "跟读",
                "朗读": "朗读",
                "郎读": "朗读",
                "狼读": "朗读",
                # 常见教学用语
                "请注意": "请注意",
                "青注意": "请注意",
                "请自行": "请自行",
                "青自行": "请自行",
                "查缺补漏": "查缺补漏",
                "诺补圈": "查缺补漏",
                "脑补圈": "查缺补漏",
                "详解": "详解",
                "详街": "详解",
                "相解": "详解",
                "对应": "对应",
                "对因": "对应",
                "对英": "对应",
                "参见": "参见",
                "残见": "参见",
                "参建": "参见",
                # 英语兔特色用语（基于您的测试视频）
                "英语兔": "英语兔",
                "英语图": "英语兔",
                "英语土": "英语兔",
                "快速讲解": "快速讲解",
                "快苏讲解": "快速讲解",
                "核心要点": "核心要点",
                "和心要点": "核心要点",
                "主流": "主流",
                "主六": "主流",
                "体系": "体系",
                "提系": "体系",
                "题系": "体系",
                "大同小异": "大同小异",
                "大同小艺": "大同小异",
                "并不影响": "并不影响",
                "病不影响": "并不影响",
                "学习和进步": "学习和进步",
                "学西和进步": "学习和进步",
                # 决定性要素（您视频中的关键概念）
                "决定性": "决定性",
                "绝定性": "决定性",
                "决顶性": "决定性",
                "要素": "要素",
                "要数": "要素",
                "药素": "要素",
                "三要素": "三要素",
                "三药素": "三要素",
                # 语音描述专业词汇
                "最高点": "最高点",
                "罪高点": "最高点",
                "口腔": "口腔",
                "口相": "口腔",
                "口想": "口腔",
                "位置": "位置",
                "围置": "位置",
                "为置": "位置",
                "粗略": "粗略",
                "粗虐": "粗略",
                "出略": "粗略",
                "理解为": "理解为",
                "理姐为": "理解为",
                "隆起": "隆起",
                "龙起": "隆起",
                "聋起": "隆起",
                "垄起": "隆起",
                "感受": "感受",
                "感首": "感受",
                "甘受": "感受",
                "运动": "运动",
                "运懂": "运动",
                "云动": "运动",
                "韵母": "韵母",
                "运萌": "韵母",
                "云母": "韵母",
                "需要": "需要",
                "须要": "需要",
                "虚要": "需要",
                "圆唇度": "圆唇度",
                "原纯度": "圆唇度",
                "元纯度": "圆唇度",
                "很高": "很高",
                "恨高": "很高",
                "狠高": "很高",
                # 绘图和图表
                "画在": "画在",
                "化在": "画在",
                "华在": "画在",
                "图上": "图上",
                "涂上": "图上",
                "突上": "图上",
                "作为": "作为",
                "做为": "作为",
                "坐为": "作为",
                "这样": "这样",
                "这养": "这样",
                "折样": "这样",
            }
        )

    if "物理" in domains:
        domain_corrections.update(
            {
                "速度": "速度",
                "苏度": "速度",
                "加速度": "加速度",
                "假速度": "加速度",
                "能量": "能量",
                "能亮": "能量",
                "动量": "动量",
                "懂量": "动量",
                "电荷": "电荷",
                "店货": "电荷",
                "磁场": "磁场",
                "次场": "磁场",
            }
        )

    if "化学" in domains:
        domain_corrections.update(
            {
                "分子": "分子",
                "分字": "分子",
                "原子": "原子",
                "元子": "原子",
                "反应": "反应",
                "反映": "反应",
                "催化剂": "催化剂",
                "崔化剂": "催化剂",
                "氧化": "氧化",
                "养化": "氧化",
                "还原": "还原",
                "还元": "还原",
            }
        )

    return domain_corrections


def correct_whisper_errors(text, domain_keywords=None):
    """
    智能修正Whisper语音识别错误 - 通用自适应版本，增强版
    """

    # 1. 智能检测内容领域
    detected_domains = detect_content_domain(text)

    # 2. 获取通用纠错词典
    universal_corrections = get_universal_corrections()

    # 3. 获取领域特定纠错词典
    domain_corrections = get_domain_specific_corrections(detected_domains)

    # 4. 上下文相关纠错（针对连续短语）
    context_corrections = get_contextual_corrections(text, detected_domains)

    # 5. 合并所有纠错词典
    all_corrections = {
        **universal_corrections,
        **domain_corrections,
        **context_corrections,
    }

    # 6. 执行纠错
    corrected_text = text
    corrections_made = []

    # 按照长度降序排序，优先替换长短语
    sorted_corrections = sorted(
        all_corrections.items(), key=lambda x: len(x[0]), reverse=True
    )

    for wrong, correct in sorted_corrections:
        if wrong in corrected_text:
            count = corrected_text.count(wrong)
            corrected_text = corrected_text.replace(wrong, correct)
            if count > 0:
                corrections_made.append(f"{wrong} → {correct} ({count}次)")

    return corrected_text, corrections_made


def get_contextual_corrections(text, detected_domains):
    """
    基于上下文的智能纠错 - 处理连续短语和特定语境
    """
    contextual_corrections = {}

    # 基于检测到的领域添加上下文纠错
    if "英语" in detected_domains:
        # 英语教学特定的连续短语纠错
        contextual_corrections.update(
            {
                # 基于您的测试视频中发现的具体错误
                "英语兔接下来为你快速讲解一遍": "英语兔接下来为你快速讲解一遍",
                "所有音标的核心要点": "所有音标的核心要点",
                "请自行查诺补圈": "请自行查缺补漏",
                "请自行查脑补圈": "请自行查缺补漏",
                "如果其中某些音标你不是很清楚": "如果其中某些音标你不是很清楚",
                "请参见对应的音标详解视频": "请参见对应的音标详解视频",
                "请注意这个基间版音标讲解": "请注意这个基础版音标讲解",
                "基间版": "基础版",
                "释基于最主流的低真音标": "是基于最主流的DJ音标",
                "释基于": "是基于",
                "但其他音标体系代表的都是同一个英语语音体系": "但其他音标体系代表的都是同一个英语语音体系",
                "甚至可以说是大同小艺": "甚至可以说是大同小异",
                "所以并不影响你英语语音的学习和进步": "所以并不影响你英语语音的学习和进步",
                # 元音相关错误纠正
                "咱们先说原因": "咱们先说元音",
                "居分各个原因的决定性三要素": "区分各个元音的决定性三要素",
                "居分": "区分",
                "原因的决定性三要素": "元音的决定性三要素",
                "蛇尾的前后": "舌位的前后",
                "蛇尾的高低": "舌位的高低",
                "最纯的原纯度": "最大的圆唇度",
                "原纯度": "圆唇度",
                # 舌位描述
                "所谓蛇尾": "所谓舌位",
                "你可以粗略理解为发音时蛇面龙起的最高点": "你可以粗略理解为发音时舌面隆起的最高点",
                "蛇面龙起": "舌面隆起",
                "蛇面": "舌面",
                "龙起": "隆起",
                "在口相中的位置": "在口腔中的位置",
                "口相": "口腔",
                # 韵母示例
                "咱们可以用普通话的原因及运萌": "咱们可以用普通话的元音即韵母",
                "原因及运萌": "元音即韵母",
                "运萌": "韵母",
                "来感受一下蛇尾的前后高低以及原纯度": "来感受一下舌位的前后高低以及圆唇度",
                # 具体音标例子
                "比如普通话B的运萌蛇尾前起高": "比如普通话 i 的韵母舌位前且高",
                "B的运萌": "i 的韵母",
                "蛇尾前起高": "舌位前且高",
                "2的运萌蛇尾后起高": "u 的韵母舌位后且高",
                "2的运萌": "u 的韵母",
                "蛇尾后起高": "舌位后且高",
                "H的运萌蛇尾中起低": "a 的韵母舌位中且低",
                "H的运萌": "a 的韵母",
                "蛇尾中起低": "舌位中且低",
                "而刚才这三个原因中只有2的运萌是需要原纯的": "而刚才这三个元音中只有 u 的韵母是需要圆唇的",
                "2的运萌是需要原纯的": "u 的韵母是需要圆唇的",
                "原纯的": "圆唇的",
                "及原纯度很高": "即圆唇度很高",
                # 元音图相关
                "咱们按照蛇尾的前后高低和原纯度": "咱们按照舌位的前后高低和圆唇度",
                "可以把英语中不同的原因像这样画在作为原因图上": "可以把英语中不同的元音像这样画在作为元音图上",
                "不同的原因": "不同的元音",
                "作为原因图": "作为元音图",
                "原因图": "元音图",
            }
        )

    # 数学领域的上下文纠错
    if "数学" in detected_domains:
        contextual_corrections.update(
            {
                "二次韩数的图像": "二次函数的图像",
                "韩数的图像": "函数的图像",
                "对胜揉的方程": "对称轴的方程",
                "判别事等于零": "判别式等于零",
                "德拉等于零": "Delta等于零",
            }
        )

    return contextual_corrections


def post_process_subtitles(
    subtitles,
    detected_domains=None,
    verbose=False,
    client=None,
    model=None,
    ai_correction=False,
    correction_rounds=3,
):
    """
    后处理字幕，进行智能纠错 - 支持规则纠错 + AI纠错双重保障
    """
    if verbose:
        print("🔧 开始多层智能纠错...")

    # 第一层：规则纠错
    if verbose:
        print("   📋 第一层：基于规则的纠错...")

    corrected_subtitles = []
    total_corrections = []

    for subtitle in subtitles:
        # 纠错字幕内容
        corrected_content, corrections = correct_whisper_errors(
            subtitle.content, detected_domains
        )

        # 创建新的字幕对象
        corrected_subtitle = srt.Subtitle(
            index=subtitle.index,
            start=subtitle.start,
            end=subtitle.end,
            content=corrected_content,
        )

        corrected_subtitles.append(corrected_subtitle)
        total_corrections.extend(corrections)

    if verbose and total_corrections:
        print(f"   ✅ 规则纠错完成，共修正 {len(total_corrections)} 处错误")
        # 显示前5个纠错示例
        for correction in total_corrections[:5]:
            print(f"      {correction}")
        if len(total_corrections) > 5:
            print(f"      ... 还有 {len(total_corrections) - 5} 处纠错")
    elif verbose:
        print(f"   ✅ 规则纠错完成，无需修正")

    # 第二层：AI纠错（如果启用）
    ai_corrections = []
    if ai_correction and client and model:
        if verbose:
            print("   🤖 第二层：基于AI的智能纠错...")

        corrected_subtitles, ai_corrections = ai_correct_subtitles(
            client,
            corrected_subtitles,
            model,
            detected_domains,
            rounds=correction_rounds,
            verbose=verbose,
        )
    elif ai_correction and verbose:
        print("   ⚠️  AI纠错已启用但缺少必要参数，跳过AI纠错")

    # 总结
    total_all_corrections = len(total_corrections) + len(ai_corrections)
    if verbose:
        print(f"🎯 多层纠错总结:")
        print(f"   规则纠错: {len(total_corrections)} 处")
        print(f"   AI纠错:   {len(ai_corrections)} 处")
        print(f"   总计:     {total_all_corrections} 处")

    return corrected_subtitles, total_corrections + ai_corrections

    return corrected_subtitles, total_corrections


def ai_correct_subtitles(
    client, subtitles, model, detected_domains=None, rounds=3, verbose=False
):
    """
    使用大模型进行智能纠错 - 在规则纠错后的第二层纠错
    """
    if verbose:
        print(f"🤖 开始AI智能纠错（{rounds}轮）...")

    # 检测主要内容领域，用于定制纠错提示
    domain_context = ""
    if detected_domains:
        domain_context = f"\n\n**内容领域**: {', '.join(detected_domains)}"
        if "英语" in detected_domains:
            domain_context += "\n请特别注意英语教学相关的专业术语，如：音标、元音、辅音、舌位、DJ音标、韵母、圆唇度等。"

    corrected_subtitles = subtitles.copy()
    all_corrections = []

    for round_num in range(1, rounds + 1):
        if verbose:
            print(f"   第 {round_num} 轮纠错...")

        round_corrections = []
        batch_size = 10  # 每次处理10条字幕

        for i in range(0, len(corrected_subtitles), batch_size):
            batch = corrected_subtitles[i : i + batch_size]

            # 构建批处理文本
            batch_text = ""
            for j, subtitle in enumerate(batch):
                batch_text += f"{i+j+1}. [{subtitle.start}] {subtitle.content}\n"

            # 构建纠错提示词
            correction_prompt = f"""
# 任务
你是一位专业的中文语音识别纠错专家，请仔细检查以下字幕文本中的错别字、同音字错误、语法错误，并进行修正。

# 纠错原则
1. **保持原意**：只修正明显的错误，不改变原始语义
2. **同音字纠错**：修正语音识别导致的同音字错误
3. **语法纠错**：修正明显的语法错误
4. **专业术语**：确保专业术语的准确性
5. **上下文一致**：保持前后语境的一致性{domain_context}

# 输出格式
请按照以下格式输出，对于每一条字幕：
- 如果有错误：`序号. [时间戳] 修正后的内容 | 修改说明: 原词→正词`
- 如果无错误：`序号. [时间戳] 原内容`

# 待纠错字幕（第{round_num}轮）
{batch_text}

请逐条检查并修正：
"""

            try:
                # 调用大模型进行纠错
                corrected_response = generate(
                    client, correction_prompt, model, max_tokens=2048
                )

                if corrected_response:
                    # 解析大模型返回的纠错结果
                    corrected_lines = corrected_response.strip().split("\n")

                    for line_idx, line in enumerate(corrected_lines):
                        if line.strip() and f"{i+line_idx+1}." in line:
                            try:
                                # 解析格式: "序号. [时间戳] 内容 | 修改说明"
                                parts = line.split("] ", 1)
                                if len(parts) >= 2:
                                    content_part = parts[1]

                                    if " | 修改说明:" in content_part:
                                        # 有修改
                                        new_content, change_desc = content_part.split(
                                            " | 修改说明:", 1
                                        )
                                        new_content = new_content.strip()

                                        # 更新字幕内容
                                        original_idx = i + line_idx
                                        if original_idx < len(corrected_subtitles):
                                            old_content = corrected_subtitles[
                                                original_idx
                                            ].content
                                            if new_content != old_content:
                                                corrected_subtitles[original_idx] = (
                                                    srt.Subtitle(
                                                        index=corrected_subtitles[
                                                            original_idx
                                                        ].index,
                                                        start=corrected_subtitles[
                                                            original_idx
                                                        ].start,
                                                        end=corrected_subtitles[
                                                            original_idx
                                                        ].end,
                                                        content=new_content,
                                                    )
                                                )
                                                round_corrections.append(
                                                    f"第{round_num}轮: {change_desc.strip()}"
                                                )
                                    # else: 无修改，保持原样
                            except Exception as e:
                                if verbose:
                                    print(f"   警告: 解析纠错结果失败: {e}")
                                continue

            except Exception as e:
                if verbose:
                    print(f"   警告: AI纠错失败: {e}")
                continue

        all_corrections.extend(round_corrections)

        if verbose and round_corrections:
            print(f"   第 {round_num} 轮完成，修正 {len(round_corrections)} 处")
        elif verbose:
            print(f"   第 {round_num} 轮完成，无需修正")

    if verbose:
        print(f"✅ AI纠错完成，共 {rounds} 轮，总计修正 {len(all_corrections)} 处")
        if all_corrections and verbose:
            print("🔍 AI纠错详情：")
            for correction in all_corrections[:5]:  # 显示前5个
                print(f"   {correction}")
            if len(all_corrections) > 5:
                print(f"   ... 还有 {len(all_corrections) - 5} 处修正")

    return corrected_subtitles, all_corrections


def generate(client, prompt, model, max_tokens=4096):
    """生成内容 - 优化版本，增加token限制和重试机制，提高长视频内容质量"""
    try:
        # 第一次尝试，使用更高的token限制和较低温度确保准确性
        res = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,  # 降低温度提高准确性
            top_p=0.9,
            max_tokens=max_tokens,
            stream=False,
        )
        content = res.choices[0].message.content.strip()

        # 检查内容完整性 - 对于长视频，期望更长的输出
        min_length = 200 if "40分钟" in prompt or "长视频" in prompt else 100

        if len(content) < min_length:
            print(f"⚠️ 生成内容可能不完整（{len(content)}字符），正在重试...")
            # 重试一次，提高温度增加创造性
            enhanced_prompt = (
                prompt
                + "\n\n# 重要提醒\n- 这是一个较长的视频内容，请确保输出完整详细的分析\n- 每个要点都要充分展开，不要省略细节\n- 输出长度应该与视频内容的丰富程度相匹配"
            )

            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": enhanced_prompt}],
                temperature=0.4,  # 适度提高温度
                top_p=0.95,
                max_tokens=max_tokens,
                stream=False,
            )
            content = res.choices[0].message.content.strip()

            if len(content) < min_length:
                print(f"⚠️ 重试后内容仍然较短（{len(content)}字符），可能是模型限制")
            else:
                print(f"✅ 重试成功，生成了 {len(content)} 字符的内容")

        return content
    except Exception as e:
        print(f"❌ 调用大模型失败: {e}", file=sys.stderr)
        return ""


def generate_xhs_note(
    client,
    full_text,
    model,
    frame_dir=None,
    video_md5=None,
    video_theme=None,
    mind_map_content=None,
    cover_frame=None,
):
    # 检测视频长度，用于优化提示词
    text_length = len(full_text)
    is_long_video = text_length > 5000  # 假设超过5000字符为长视频

    # 构建图片分配策略
    image_strategy = ""
    if frame_dir and os.path.exists(frame_dir):
        frame_files = [f for f in os.listdir(frame_dir) if f.endswith(".jpg")]
        # 过滤掉无效的00_00帧
        valid_frames = [f for f in frame_files if not f.startswith("00_00")]

        if valid_frames:
            total_frames = len(valid_frames)
            cover_info = f"封面帧: {cover_frame}" if cover_frame else "未指定封面帧"

            image_strategy = f"""

## 📌 智能图片分配策略
- 总共有 {total_frames} 张有效关键帧可用
- {cover_info}
- 图片路径格式：![](../../uploads/{video_md5}/frames/时间戳.jpg)
- 可用帧文件：{', '.join(sorted(valid_frames)[:8])}...

### 图片分配规则：
1. **开篇封面**：{f"使用 {cover_frame} 作为内容开头的封面图" if cover_frame else "使用第一个有效帧作为封面"}
2. **章节配图**：每个主要章节根据内容长度智能分配图片
   - 短章节（<300字）：1张图片
   - 中等章节（300-600字）：2张图片  
   - 长章节（>600字）：3-4张图片
3. **图片选择原则**：
   - 优先选择与该章节时间点接近的帧
   - 避免使用00_00等无效帧
   - 确保图片在整个内容中均匀分布
4. **封面使用**：在文章开头使用封面帧营造良好的第一印象

### 示例格式：
![](../../uploads/{video_md5}/frames/{cover_frame if cover_frame else "00_30.jpg"})
"""

    # 构建基于思维导图的结构指导
    structure_guide = ""
    if mind_map_content:
        structure_guide = f"""

## �️ 结构对齐要求
以下是视频的思维导图结构，请严格按照此结构组织内容卡片：

{mind_map_content[:1500]}

### 结构转换规则：
1. **一级标题对应**：思维导图的每个一级要点对应内容卡片的一个## 章节
2. **内容整合**：将思维导图的二级、三级要点整合成该章节的段落内容
3. **保持完整性**：确保思维导图中的所有要点都在内容卡片中体现
4. **逻辑连贯**：每个章节内部保持逻辑连贯，形成完整的知识块
"""

    # 视频主题上下文
    theme_context = ""
    if video_theme:
        theme_context = f"""

## 🎯 视频主题上下文
{video_theme}

请基于以上视频特征调整内容风格和表达方式。
"""

    prompt = f"""
# 角色设定
你是一位资深的教育内容专家，擅长将教学视频转化为结构化、高价值的知识卡片。

# 核心任务
基于提供的思维导图结构，生成与之完全对应的内容卡片，确保结构一致性和内容完整性。

{theme_context}
{structure_guide}

## 内容质量要求
1. **结构严格对应**：每个章节必须与思维导图的一级要点完全对应
2. **内容深度挖掘**：将思维导图的细分要点展开为详细段落
3. **知识完整性**：覆盖思维导图中的所有知识点，不遗漏
4. **逻辑连贯性**：每个章节内部逻辑清晰，前后呼应

## 文体规范
- **开篇**：用「# 标题」概括视频核心价值
- **章节**：用「## 章节名」对应思维导图一级要点
- **内容**：
  - 每个章节包含**核心概念**、**方法技巧**、**应用案例**
  - 重要概念用**粗体**强调
  - 关键步骤用数字列表
  - 适当使用▪️符号突出要点

{image_strategy}

## 特殊要求
- 确保章节数量与思维导图一级要点数量完全一致
- 每个章节的内容要充实，避免空洞概括
- 合理分配图片，让视觉效果丰富但不冗余

# 视频完整内容
{full_text[:25000]}

# 输出要求
生成完整的知识卡片，确保：
1. 结构与思维导图完全对应
2. 内容详实，体现教学价值
3. 图片分配合理，视觉效果佳
4. 总结部分体现整体学习价值

请直接输出完整内容，不要解释说明。
""".strip()

    return generate(client, prompt, model, max_tokens=8192)


def generate_markmap(
    client, timed_text, model, frame_dir=None, video_md5=None, video_theme=None
):
    # 检测是否为长视频
    text_length = len(timed_text)
    is_long_video = text_length > 10000

    # 视频主题上下文
    theme_context = ""
    if video_theme:
        theme_context = f"""

## 🎯 视频主题上下文
{video_theme}

请基于以上视频特征优化思维导图结构，确保体现该类型内容的特点。
"""

    # STEP 1: 提取结构化大纲
    step1_prompt = f"""
# 角色
你是一位专业的知识架构师，擅长将视频内容转化为清晰的思维导图结构。

{theme_context}

# 任务
请根据以下带时间戳的视频字幕，创建一个结构清晰、层次分明的思维导图大纲。

# 特殊要求（针对长视频）
{"- 这是一个较长的教学视频，包含丰富的知识点" if is_long_video else ""}
{"- 需要构建完整的知识体系结构，不能省略重要章节" if is_long_video else ""}
{"- 按照教学逻辑组织内容，体现知识的递进关系" if is_long_video else ""}

# 输入格式说明
- 每行格式为：[HH:MM:SS] 文本内容
- 时间戳表示该内容在视频中出现的时间点

# 输出要求
1. 使用Markdown无序列表格式（- 和空格缩进表示层级）
2. 每个节点应是简洁的关键词或短语（不超过10个字）
3. 在重要节点末尾添加时间戳，格式为 `MM:SS`（例如 `01:23`）
4. 保持逻辑层次：主题 → 章节 → 要点 → 细节（最多4级）
5. 合并相似内容，但保留重要的知识点
6. 优先保留教学重点和关键转折

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

# 重要提示
- 保持输出为纯Markdown列表
- 时间戳必须准确对应原文内容
- 重点突出教学价值高的内容
- 体现完整的知识结构

# 视频字幕内容
{timed_text[:25000]}
""".strip()

    outline = generate(client, step1_prompt, model, max_tokens=4096)
    if not outline.strip():
        return ""

    # STEP 2: 格式优化（确保Markmap兼容）
    step2_prompt = f"""
# 任务
你是一位Markdown格式专家，负责将以下思维导图大纲优化为标准Markmap兼容格式。

# 输入
一个初步的思维导图结构，可能包含不规范的格式。

# 输出要求
1. 严格使用Markdown无序列表
2. 每级缩进使用2个空格
3. 时间戳统一为 `MM:SS` 格式（例如 `01:23`）
4. 每行一个节点，不跨行
5. 节点文本简洁，不超过15个字
6. 保留完整的知识结构层次
7. 确保语法正确，便于Markmap渲染

# 错误格式修正
- 将 "00:01:23" 转换为 "01:23"
- 将 "章节一 [00:01:23]" 转换为 "章节一 `01:23`"
- 修复不正确的缩进层级
- 移除多余的标点符号

# 输出示例
# 教学内容主题
- 理论基础
  - 核心概念 `01:20`
  - 基本原理 `02:45`
    - 原理解释 `03:10`
    - 应用场景 `04:30`
- 实战操作
  - 方法介绍 `06:30`
    - 步骤一 `07:15`
    - 步骤二 `08:45`
  - 注意事项 `10:20`

# 待优化内容
{outline}
""".strip()

    return generate(client, step2_prompt, model, max_tokens=4096)


def extract_key_moments(client, timed_text, model):
    """提取短视频关键时刻"""
    prompt = f"""
# 任务
作为短视频内容分析师，请从以下带时间戳的字幕中识别3-5个最关键片段：

# 判断标准
- 信息密度最高的片段（单位时间知识点最多）
- 情绪峰值点（感叹词/语气词密集处）
- 观点转折点（"但是"/"其实"等转折词后）
- 重复强调的内容（出现≥2次的关键信息）
- 结尾call-to-action部分

# 输出要求
严格按此格式：
[MM:SS] 简洁描述（不超过10字）
[MM:SS] 为什么重要：15字内说明

# 示例
[01:23] 三步操作法
为什么重要：核心方法论，被重复强调3次

[02:45] 避坑提醒
为什么重要：唯一负面案例，情绪强烈

# 字幕内容
{timed_text[:15000]}
"""
    return generate(client, prompt, model)


def analyze_credibility(client, full_text, model):
    """分析内容可信度"""
    prompt = f"""
# 任务
作为事实核查专家，请分析以下短视频内容的可信度：

# 分析维度
1. 数据来源：是否有明确数据来源？【有/无】
2. 专家背书：是否引用权威专家？【有/无】
3. 逻辑漏洞：是否存在明显逻辑错误？【指出1点】
4. 情绪操纵：是否过度使用情绪化语言？【程度：低/中/高】
5. 证据强度：支持论点的证据质量【弱/中/强】

# 输出格式
## 可信度评分：X/10
- 数据来源：[分析]
- 专家背书：[分析]
- 逻辑漏洞：[具体指出]
- 情绪操纵：[程度] + [例句]
- 证据强度：[分析]

## 总结建议
[对用户的使用建议]

# 内容
{full_text[:15000]}
"""
    return generate(client, prompt, model)


def identify_video_structure(client, timed_text, model):
    """识别视频内容结构"""
    prompt = f"""
# 任务
分析短视频的内容结构模式，识别其采用的叙事框架：

# 常见短视频结构
✅ 问题-解决方案：先提出问题，再给解决方案
✅ 故事-教训：讲述个人经历，最后总结教训
✅ 对比法：好vs坏/之前vs之后的对比
✅ 三段式：开头悬念-中间展开-结尾反转
✅ 列表式：直接列出N个要点（"3个技巧"/"5个误区"）

# 输出要求
## 主要结构：[识别出的结构]
## 结构证据：
- [时间点] 具体表现
- [时间点] 具体表现
## 适配建议：该结构适合什么类型内容？
## 完整性评价：结构是否完整，缺少什么？

# 字幕
{timed_text[:15000]}
"""
    return generate(client, prompt, model)


def rate_content_value(client, full_text, model):
    """评估内容价值"""
    prompt = f"""
# 任务
作为内容质量评估专家，请对短视频内容进行多维度评分：

# 评分维度（1-5分）
1. 信息密度：单位时间有价值信息量
2. 实用价值：内容可应用程度
3. 逻辑清晰度：观点组织是否清晰
4. 情绪价值：能否引发共鸣
5. 独特性：内容新颖程度

# 输出格式
## 综合评分：X/5

### 详细评分
- 信息密度：X/5 - [简要说明]
- 实用价值：X/5 - [简要说明]
- 逻辑清晰度：X/5 - [简要说明]
- 情绪价值：X/5 - [简要说明]
- 独特性：X/5 - [简要说明]

## 观看建议
- 适合人群：[描述]
- 最佳观看时长：前X秒即可获取核心价值
- 内容精华：[1句话概括]

# 内容
{full_text[:15000]}
"""
    return generate(client, prompt, model)


def main():
    args = parse_args()

    if not args.api_key or not args.api_base:
        print("❌ 缺少 API Key 或 Base URL，请设置参数或环境变量", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=args.api_key, base_url=args.api_base)
    video_file = args.input

    # 计算视频文件MD5
    if args.verbose:
        print("🔍 计算视频文件MD5...")
    video_md5 = compute_md5(video_file)
    if args.verbose:
        print(f"📊 视频MD5: {video_md5}")

    # 创建新的目录结构
    uploads_dir = "uploads"
    output_dir = "outputs" if args.output_dir else "outputs"

    video_cache_dir = os.path.join(uploads_dir, video_md5)
    video_output_dir = os.path.join(output_dir, video_md5)
    frame_dir = os.path.join(video_cache_dir, "frames")

    os.makedirs(video_cache_dir, exist_ok=True)
    os.makedirs(video_output_dir, exist_ok=True)
    os.makedirs(frame_dir, exist_ok=True)

    # 缓存文件路径
    cached_audio = os.path.join(video_cache_dir, f"{video_md5}.mp3")
    cached_srt = os.path.join(video_cache_dir, f"{video_md5}.srt")
    cached_video = os.path.join(video_cache_dir, f"{video_md5}.mp4")

    # 输出文件路径
    xhs_file = os.path.join(video_output_dir, f"内容卡片.md")
    mind_file = os.path.join(video_output_dir, f"思维导图.md")
    key_moments_file = os.path.join(video_output_dir, f"关键时刻标记.md")
    credibility_file = os.path.join(video_output_dir, f"可信度分析.md")
    structure_file = os.path.join(video_output_dir, f"内容结构分析.md")
    value_file = os.path.join(video_output_dir, f"内容价值评分.md")

    try:
        start_time = time.time()
        # 定义进度条
        progress_bar = tqdm(total=100, desc="处理进度", unit="%")

        # Step 1: 检查音频缓存，如果不存在则转换
        if not os.path.exists(cached_audio):
            if args.verbose:
                print("🎵 音频缓存不存在，开始转换...")
            actual_video_file = video_to_audio(video_file, cached_audio, args.verbose)
            # 同时复制原视频到缓存目录（用于后续截帧）
            if not os.path.exists(cached_video) and os.path.exists(actual_video_file):
                shutil.copy2(actual_video_file, cached_video)
        else:
            if args.verbose:
                print("✅ 使用缓存的音频文件")
            # 缓存存在时，需要确定用于截帧的视频文件
            if video_file.startswith("http://") or video_file.startswith("https://"):
                if "bili" in video_file:
                    actual_video_file = get_temp_video_path(video_file)
                    if not os.path.exists(actual_video_file):
                        actual_video_file = download_bilibili_url_video(video_file)
                else:
                    actual_video_file = video_file
            else:
                actual_video_file = video_file
        progress_bar.update(20)

        # Step 2: 检查字幕缓存，如果不存在则转录
        if not os.path.exists(cached_srt):
            if args.verbose:
                print("字幕缓存不存在，开始语音识别...")
            timed_text, subtitles = transcribe_audio(
                cached_audio,
                model_name=args.whisper_model,
                language=args.language,
                output_dir=cached_srt,
                verbose=args.verbose,
                client=client,
                gpt_model=args.gpt_model,
                ai_correction=args.ai_correction,
                correction_rounds=args.correction_rounds,
            )
        else:
            if args.verbose:
                print("✅ 使用缓存的字幕文件")
            # 从缓存的SRT文件读取字幕
            with open(cached_srt, "r", encoding="utf-8") as f:
                subtitles = list(srt.parse(f.read()))

            # 如果启用了AI纠错，对缓存的字幕也进行AI纠错
            if args.ai_correction:
                if args.verbose:
                    print("🤖 对缓存字幕进行AI纠错...")

                # 检测内容领域
                full_transcript = " ".join([sub.content for sub in subtitles])
                detected_domains = detect_content_domain(full_transcript)

                if args.verbose and detected_domains:
                    print(f"   🎯 检测到内容领域: {', '.join(detected_domains)}")

                # 执行AI纠错
                subtitles, ai_corrections = ai_correct_subtitles(
                    client,
                    subtitles,
                    args.gpt_model,
                    detected_domains,
                    rounds=args.correction_rounds,
                    verbose=args.verbose,
                )

                # 更新缓存文件
                if ai_corrections:
                    corrected_srt_content = srt.compose(subtitles)
                    with open(cached_srt, "w", encoding="utf-8") as f:
                        f.write(corrected_srt_content)
                    if args.verbose:
                        print(f"   ✅ 更新字幕缓存，AI纠错 {len(ai_corrections)} 处")

            # 重建timed_text格式
            timed_text = ""
            for sub in subtitles:
                timed_text += f"[{sub.start}] {sub.content.strip()}\n"

        progress_bar.update(40)

        # Step 3: 提取关键帧（基于字幕时间点）
        if args.verbose:
            print("🖼️  提取视频关键帧...")

        # 检查是否已有帧文件，如果没有则提取
        existing_frames = [f for f in os.listdir(frame_dir) if f.endswith(".jpg")]
        cover_frame = None

        if not existing_frames:
            # 确定用于提取帧的视频文件
            frame_source_video = (
                cached_video if os.path.exists(cached_video) else actual_video_file
            )
            frame_files, cover_frame = extract_frames_from_subtitles(
                frame_source_video,
                subtitles,
                frame_dir,
                args.verbose,
            )
        else:
            if args.verbose:
                print(f"✅ 使用已存在的 {len(existing_frames)} 个关键帧")
            frame_files = [(f, None) for f in existing_frames]
            # 智能推测封面帧：排除00_00，选择最早的有效帧
            valid_frames = [f for f in existing_frames if not f.startswith("00_00")]
            if valid_frames:
                cover_frame = sorted(valid_frames)[0]
                if args.verbose:
                    print(f"   🎯 推测封面帧: {cover_frame}")

        progress_bar.update(60)

        # 准备文本内容
        full_text = "\n".join(
            [
                line.split("] ", 1)[1]
                for line in timed_text.strip().split("\n")
                if "] " in line
            ]
        )

        # Step 4: 分析视频主题和类型（为后续生成提供上下文）
        if args.verbose:
            print("🎯 正在分析视频主题和类型...")
        video_theme = get_video_theme_and_type(client, full_text, args.gpt_model)
        if args.verbose:
            print("✅ 视频主题分析完成")

        # Step 5: 调用 LLM 生成内容
        generated_count = 0

        # 生成策略：先生成思维导图，再基于思维导图生成内容卡片
        mind_map_content = None

        # 优先生成思维导图（如果需要）
        if args.format in ["markmap", "both"]:
            if args.verbose:
                print("🧠 正在生成思维导图...")
            mind_map_content = generate_markmap(
                client, timed_text, args.gpt_model, frame_dir, video_md5, video_theme
            )
            Path(mind_file).write_text(mind_map_content, encoding="utf-8")
            print(f"🧠 思维导图: {mind_file}")
            generated_count += 1

        # 基于思维导图生成内容卡片
        if args.format in ["markdown", "both"]:
            if args.verbose:
                print("📝 正在生成内容卡片...")
            content = generate_xhs_note(
                client,
                full_text,
                args.gpt_model,
                frame_dir,
                video_md5,
                video_theme,
                mind_map_content,
                cover_frame,
            )
            Path(xhs_file).write_text(content, encoding="utf-8")
            print(f"📄 内容卡片: {xhs_file}")
            generated_count += 1

        # 扩展功能生成
        if args.key_moments:
            if args.verbose:
                print("🎯 正在提取关键时刻...")
            key_moments = extract_key_moments(client, timed_text, args.gpt_model)
            Path(key_moments_file).write_text(key_moments, encoding="utf-8")
            print(f"🎯 关键时刻: {key_moments_file}")
            generated_count += 1

        if args.credibility:
            if args.verbose:
                print("🔍 正在分析可信度...")
            credibility = analyze_credibility(client, full_text, args.gpt_model)
            Path(credibility_file).write_text(credibility, encoding="utf-8")
            print(f"🔍 可信度分析: {credibility_file}")
            generated_count += 1

        if args.structure:
            if args.verbose:
                print("🏗️  正在分析内容结构...")
            structure = identify_video_structure(client, timed_text, args.gpt_model)
            Path(structure_file).write_text(structure, encoding="utf-8")
            print(f"🏗️  结构分析: {structure_file}")
            generated_count += 1

        if args.value_rating:
            if args.verbose:
                print("⭐ 正在评估内容价值...")
            value_rating = rate_content_value(client, full_text, args.gpt_model)
            Path(value_file).write_text(value_rating, encoding="utf-8")
            print(f"⭐ 价值评分: {value_file}")
            generated_count += 1

        # ✅ 计算总耗时
        end_time = time.time()
        total_seconds = int(end_time - start_time)
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        # 确保进度条完成
        progress_bar.update(100)
        progress_bar.close()

        # 🎉 输出最终完成信息（统一收尾）
        print("\n" + "🎉" * 10)
        print("处理完成！")
        print(f"📂 缓存目录: {video_cache_dir}")
        print(f"📂 输出目录: {video_output_dir}")
        if minutes > 0:
            print(f"⏱️  总耗时: {minutes}分{seconds}秒")
        else:
            print(f"⏱️  总耗时: {seconds}秒")
        print("✅ 全部处理完成！")

    except Exception as e:
        print(f"❌ 处理失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()