#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实时会议记录系统
支持实时语音转文字、多语言翻译、说话人分离、智能总结
"""

import os
import sys
import json
import time
import queue
import threading
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import argparse

# 会议软件集成
try:
    from meeting_integration import MeetingIntegration

    HAS_MEETING_INTEGRATION = True
except ImportError:
    HAS_MEETING_INTEGRATION = False

# 音频处理
try:
    import pyaudio
    import numpy as np

    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False

# 语音识别
try:
    from faster_whisper import WhisperModel

    HAS_FASTER_WHISPER = True
except ImportError:
    try:
        import whisper

        HAS_FASTER_WHISPER = False
        HAS_WHISPER = True
    except ImportError:
        HAS_WHISPER = False

# 说话人分离
try:
    from pyannote.audio import Pipeline
    import torch

    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False

# 翻译模型
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
    import torch

    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False


@dataclass
class TranscriptionSegment:
    """转录片段数据结构"""

    start_time: float
    end_time: float
    text: str
    language: str
    speaker_id: Optional[str] = None
    confidence: float = 0.0
    translation: Optional[Dict[str, str]] = None


@dataclass
class SpeakerSegment:
    """说话人片段"""

    start_time: float
    end_time: float
    speaker_id: str
    confidence: float = 0.0


@dataclass
class MeetingConfig:
    """会议记录配置"""

    # 音频设置
    sample_rate: int = 16000
    chunk_size: int = 1024
    channels: int = 1

    # 模型设置
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # 语言设置
    primary_language: str = "zh"
    target_languages: List[str] = None

    # 输出设置
    output_dir: str = "meeting_records"
    realtime_display: bool = True
    save_audio: bool = True

    # 高级功能
    enable_speaker_diarization: bool = False
    enable_translation: bool = False
    enable_summarization: bool = False
    enable_meeting_integration: bool = False

    def __post_init__(self):
        if self.target_languages is None:
            self.target_languages = ["en"]


class AudioCapture:
    """音频捕获模块"""

    def __init__(self, config: MeetingConfig):
        self.config = config
        self.audio = None
        self.stream = None
        self.is_recording = False
        self.audio_queue = queue.Queue()

    def initialize(self) -> bool:
        """初始化音频捕获"""
        if not HAS_PYAUDIO:
            print("❌ 需要安装pyaudio: pip install pyaudio")
            return False

        try:
            self.audio = pyaudio.PyAudio()
            return True
        except Exception as e:
            print(f"❌ 音频初始化失败: {e}")
            return False

    def start_capture(self) -> bool:
        """开始音频捕获"""
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self.config.chunk_size,
                stream_callback=self._audio_callback,
            )

            self.stream.start_stream()
            self.is_recording = True
            print("🎤 开始音频捕获...")
            return True

        except Exception as e:
            print(f"❌ 启动音频捕获失败: {e}")
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """音频回调函数"""
        if self.is_recording:
            audio_data = np.frombuffer(in_data, dtype=np.int16)
            self.audio_queue.put((audio_data, time.time()))
        return (in_data, pyaudio.paContinue)

    def stop_capture(self):
        """停止音频捕获"""
        self.is_recording = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.audio:
            self.audio.terminate()
        print("🛑 音频捕获已停止")

    def get_audio_chunk(self) -> Optional[Tuple[np.ndarray, float]]:
        """获取音频数据块"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None


class RealtimeTranscriber:
    """实时转录模块"""

    def __init__(self, config: MeetingConfig):
        self.config = config
        self.model = None
        self.transcription_queue = queue.Queue()
        self.audio_buffer = []
        self.buffer_duration = 5.0  # 5秒缓冲
        self._using_original_whisper = False  # 标记是否使用原版whisper

    def initialize(self) -> bool:
        """初始化转录模型"""
        try:
            # 使用智能加载器
            from whisper_loader import WhisperModelLoader

            print(f"🚀 智能加载 Whisper 模型: {self.config.whisper_model}")

            # 创建加载器，设置15秒超时避免长时间卡住
            loader = WhisperModelLoader(timeout_seconds=15)

            # 加载最佳可用模型
            self.model = loader.load_best_available(
                self.config.whisper_model,
                self.config.whisper_device,
                self.config.whisper_compute_type,
            )

            if self.model:
                self._using_original_whisper = loader.using_original_whisper
                model_type = (
                    "原版 Whisper" if self._using_original_whisper else "faster-whisper"
                )
                print(f"✅ 模型加载成功 - 使用: {model_type}")
                return True
            else:
                print("❌ 所有模型加载方式都失败")
                return False

        except ImportError:
            # 回退到原始加载方式
            print("⚠️ 智能加载器不可用，使用原始方式...")
            return self._initialize_fallback()

        except Exception as e:
            print(f"❌ 智能加载失败: {e}")
            print("🔄 尝试原始加载方式...")
            return self._initialize_fallback()

    def _initialize_fallback(self) -> bool:
        """回退的原始初始化方式"""
        try:
            if HAS_FASTER_WHISPER:
                print(f"🔄 加载 faster-whisper 模型: {self.config.whisper_model}")

                # 尝试本地缓存优先
                try:
                    self.model = WhisperModel(
                        self.config.whisper_model,
                        device=self.config.whisper_device,
                        compute_type=self.config.whisper_compute_type,
                        local_files_only=True,  # 仅使用本地
                    )
                    print("✅ faster-whisper 模型（本地）加载完成")
                    return True
                except Exception:
                    print("⚠️ 本地加载失败，跳过在线下载")

            # 尝试原版 whisper
            if HAS_WHISPER:
                print(f"🔄 加载原版 Whisper 模型: {self.config.whisper_model}")
                self.model = whisper.load_model(self.config.whisper_model)
                self._using_original_whisper = True
                print("✅ 原版 Whisper 模型加载完成")
                return True
            else:
                print(
                    "❌ 需要安装语音识别模型: pip install faster-whisper 或 pip install openai-whisper"
                )
                return False

        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            print("💡 建议:")
            print("   1. 检查网络连接")
            print("   2. 安装原版: pip install openai-whisper")
            print("   3. 或尝试: pip install faster-whisper")
            return False

    def add_audio_chunk(self, audio_data: np.ndarray, timestamp: float):
        """添加音频数据到缓冲区"""
        self.audio_buffer.append((audio_data, timestamp))

        # 检查缓冲区是否达到处理条件
        if (
            len(self.audio_buffer)
            >= self.buffer_duration * self.config.sample_rate / self.config.chunk_size
        ):
            self._process_audio_buffer()

    def _process_audio_buffer(self):
        """处理音频缓冲区"""
        if not self.audio_buffer:
            return

        # 合并音频数据
        audio_chunks = [chunk[0] for chunk in self.audio_buffer]
        timestamps = [chunk[1] for chunk in self.audio_buffer]

        combined_audio = np.concatenate(audio_chunks)
        start_time = timestamps[0]
        end_time = timestamps[-1]

        # 转换为float32格式
        audio_float = combined_audio.astype(np.float32) / 32768.0

        # 进行转录
        self._transcribe_audio(audio_float, start_time, end_time)

        # 清空缓冲区（保留一点重叠）
        overlap_size = len(self.audio_buffer) // 4  # 25%重叠
        self.audio_buffer = self.audio_buffer[-overlap_size:]

    def _transcribe_audio(
        self, audio_data: np.ndarray, start_time: float, end_time: float
    ):
        """转录音频数据"""
        try:
            # 根据实际加载的模型类型选择转录方式
            if (
                hasattr(self, "_using_original_whisper")
                and self._using_original_whisper
            ):
                # 使用原版 Whisper 的转录逻辑
                result = self.model.transcribe(
                    audio_data,
                    language=(
                        self.config.primary_language
                        if self.config.primary_language != "auto"
                        else None
                    ),
                    initial_prompt="请使用简体中文输出",
                )

                for segment in result.get("segments", []):
                    transcription = TranscriptionSegment(
                        start_time=start_time + segment["start"],
                        end_time=start_time + segment["end"],
                        text=segment["text"].strip(),
                        language=result.get("language", "unknown"),
                        confidence=segment.get("avg_logprob", 0.0),
                    )

                    if transcription.text:
                        self.transcription_queue.put(transcription)

            elif HAS_FASTER_WHISPER and not getattr(
                self, "_using_original_whisper", False
            ):
                # 使用 faster-whisper 的转录逻辑
                segments, info = self.model.transcribe(
                    audio_data,
                    language=(
                        self.config.primary_language
                        if self.config.primary_language != "auto"
                        else None
                    ),
                    initial_prompt="请使用简体中文输出",
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )

                for segment in segments:
                    transcription = TranscriptionSegment(
                        start_time=start_time + segment.start,
                        end_time=start_time + segment.end,
                        text=segment.text.strip(),
                        language=info.language,
                        confidence=segment.avg_logprob,
                    )

                    if transcription.text:  # 只处理非空文本
                        self.transcription_queue.put(transcription)

            else:
                # 回退处理
                print("⚠️ 未找到可用的转录模型")

        except Exception as e:
            print(f"⚠️ 转录失败: {e}")
            # 如果转录失败，可能需要更详细的错误处理
            import traceback

            if hasattr(self.config, "verbose") and self.config.verbose:
                traceback.print_exc()

    def get_transcription(self) -> Optional[TranscriptionSegment]:
        """获取转录结果"""
        try:
            return self.transcription_queue.get_nowait()
        except queue.Empty:
            return None


class MultiLanguageTranslator:
    """多语言翻译模块"""

    def __init__(self, config: MeetingConfig):
        self.config = config
        self.translation_cache = {}
        self.smart_translator = None

    def initialize(self) -> bool:
        """初始化翻译模型"""
        if not self.config.enable_translation:
            print("⚠️ 翻译功能未启用")
            return True

        try:
            # 使用智能翻译系统
            from translation_loader import SmartTranslationSystem

            print("🚀 初始化智能翻译系统...")
            self.smart_translator = SmartTranslationSystem(
                target_languages=self.config.target_languages,
                timeout_seconds=15,  # 15秒超时
            )

            return self.smart_translator.initialize()

        except ImportError:
            # 回退到原始翻译方式
            print("⚠️ 智能翻译器不可用，使用原始方式...")
            return self._initialize_fallback()

        except Exception as e:
            print(f"❌ 智能翻译初始化失败: {e}")
            print("🔄 尝试原始翻译方式...")
            return self._initialize_fallback()

    def _initialize_fallback(self) -> bool:
        """原始翻译初始化方式（仅本地缓存）"""
        if not HAS_TRANSFORMERS:
            print("⚠️ transformers 未安装，跳过翻译功能")
            return True

        try:
            from transformers import pipeline

            print("🔄 尝试加载本地翻译模型...")

            self.translators = {}

            # 仅尝试本地缓存，不在线下载
            translation_models = {
                "zh-en": "Helsinki-NLP/opus-mt-zh-en",
                "en-zh": "Helsinki-NLP/opus-mt-en-zh",
                "ja-zh": "Helsinki-NLP/opus-mt-ja-zh",
                "ko-zh": "Helsinki-NLP/opus-mt-ko-zh",
            }

            for target_lang in self.config.target_languages:
                if target_lang == "en":
                    for pair in ["zh-en", "en-zh"]:
                        if pair in translation_models:
                            try:
                                self.translators[pair] = pipeline(
                                    "translation",
                                    model=translation_models[pair],
                                    device=-1,  # 使用CPU
                                    local_files_only=True,  # 仅使用本地缓存
                                )
                                print(f"✅ {pair} 本地模型加载成功")
                            except Exception:
                                print(f"⚠️ {pair} 本地模型不存在，跳过")

                elif target_lang in ["ja", "ko"]:
                    pair = f"{target_lang}-zh"
                    if pair in translation_models:
                        try:
                            self.translators[pair] = pipeline(
                                "translation",
                                model=translation_models[pair],
                                device=-1,
                                local_files_only=True,
                            )
                            print(f"✅ {pair} 本地模型加载成功")
                        except Exception:
                            print(f"⚠️ {pair} 本地模型不存在，跳过")

            if self.translators:
                print(f"✅ 成功加载 {len(self.translators)} 个本地翻译模型")
            else:
                print("⚠️ 无可用的本地翻译模型，翻译功能将受限")

            return True

        except Exception as e:
            print(f"⚠️ 原始翻译初始化失败: {e}")
            print("💡 翻译功能将不可用，但不影响其他功能")
            return True  # 翻译失败不应该阻止整个系统

    def translate_text(
        self, text: str, source_lang: str, target_lang: str
    ) -> Optional[str]:
        """翻译文本"""
        if not self.config.enable_translation or not text.strip():
            return None

        # 检查缓存
        cache_key = f"{source_lang}-{target_lang}:{text}"
        if cache_key in self.translation_cache:
            return self.translation_cache[cache_key]

        # 优先使用智能翻译系统
        if self.smart_translator:
            try:
                translated_text = self.smart_translator.translate_text(
                    text, source_lang, target_lang
                )
                if translated_text and translated_text != text:
                    # 缓存成功的翻译结果
                    self.translation_cache[cache_key] = translated_text
                    return translated_text
            except Exception as e:
                print(f"⚠️ 智能翻译失败: {e}")

        # 回退到原始翻译器（如果有的话）
        if hasattr(self, "translators") and self.translators:
            try:
                translator_key = f"{source_lang}-{target_lang}"
                if translator_key in self.translators:
                    result = self.translators[translator_key](text)
                    translation = result[0]["translation_text"]

                    # 缓存结果
                    self.translation_cache[cache_key] = translation
                    return translation

            except Exception as e:
                print(f"⚠️ 原始翻译失败 ({source_lang}->{target_lang}): {e}")

        return None


class SpeakerDiarizer:
    """说话人分离模块"""

    def __init__(self):
        self.pipeline = None
        self.speaker_embeddings = {}
        self.speaker_names = {}
        self.speaker_counter = 0

    def initialize(self) -> bool:
        """初始化说话人分离模型"""
        if not HAS_PYANNOTE:
            print("⚠️ 说话人分离功能需要安装: pip install pyannote.audio")
            return False

        try:
            print("🔄 加载说话人分离模型...")
            # 使用预训练的说话人分离模型
            self.pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=None,  # 如果需要HuggingFace token
            )
            print("✅ 说话人分离模型加载完成")
            return True

        except Exception as e:
            print(f"⚠️ 说话人分离模型加载失败: {e}")
            print("💡 提示: 可能需要HuggingFace访问权限")
            return False

    def process_audio_chunk(
        self, audio_data: np.ndarray, sample_rate: int = 16000
    ) -> List[SpeakerSegment]:
        """处理音频块，返回说话人片段"""
        if not self.pipeline:
            return []

        try:
            # 转换为torch tensor
            audio_tensor = torch.from_numpy(audio_data).float()
            if len(audio_tensor.shape) == 1:
                audio_tensor = audio_tensor.unsqueeze(0)  # 添加batch维度

            # 创建临时音频对象用于分离
            waveform = {"waveform": audio_tensor, "sample_rate": sample_rate}

            # 执行说话人分离
            diarization = self.pipeline(waveform)

            # 转换结果
            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segment = SpeakerSegment(
                    start_time=turn.start,
                    end_time=turn.end,
                    speaker_id=speaker,
                    confidence=1.0,  # pyannote不直接提供置信度
                )
                segments.append(segment)

            return segments

        except Exception as e:
            print(f"⚠️ 说话人分离处理失败: {e}")
            return []

    def assign_speaker_name(self, speaker_id: str, name: str):
        """为说话人分配名称"""
        self.speaker_names[speaker_id] = name

    def get_speaker_name(self, speaker_id: str) -> str:
        """获取说话人名称"""
        return self.speaker_names.get(speaker_id, f"说话人{speaker_id}")

    def assign_speaker_to_transcription(
        self,
        transcription: TranscriptionSegment,
        speaker_segments: List[SpeakerSegment],
    ) -> TranscriptionSegment:
        """为转录片段分配说话人"""
        # 寻找时间重叠最大的说话人片段
        best_speaker = None
        max_overlap = 0

        for speaker_segment in speaker_segments:
            # 计算时间重叠
            overlap_start = max(transcription.start_time, speaker_segment.start_time)
            overlap_end = min(transcription.end_time, speaker_segment.end_time)
            overlap_duration = max(0, overlap_end - overlap_start)

            if overlap_duration > max_overlap:
                max_overlap = overlap_duration
                best_speaker = speaker_segment.speaker_id

        if best_speaker:
            transcription.speaker_id = best_speaker

        return transcription


class MeetingRecorder:
    """会议记录主控制器"""

    def __init__(self, config: MeetingConfig):
        self.config = config
        self.audio_capture = AudioCapture(config)
        self.transcriber = RealtimeTranscriber(config)
        self.translator = MultiLanguageTranslator(config)
        self.speaker_diarizer = (
            SpeakerDiarizer() if config.enable_speaker_diarization else None
        )
        self.meeting_integration = None

        # 初始化会议集成（如果启用）
        if config.enable_meeting_integration and HAS_MEETING_INTEGRATION:
            self.meeting_integration = MeetingIntegration(self._on_meeting_audio_data)

        self.is_running = False
        self.transcriptions = []
        self.speaker_segments = []  # 存储说话人片段
        self.output_dir = Path(config.output_dir)
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def initialize(self) -> bool:
        """初始化所有模块"""
        print("🚀 初始化实时会议记录系统...")

        # 创建输出目录
        self.output_dir.mkdir(exist_ok=True)
        session_dir = self.output_dir / self.session_id
        session_dir.mkdir(exist_ok=True)

        # 初始化各模块
        if not self.audio_capture.initialize():
            return False

        if not self.transcriber.initialize():
            return False

        if not self.translator.initialize():
            return False

        # 初始化说话人分离（可选）
        if self.speaker_diarizer and not self.speaker_diarizer.initialize():
            print("⚠️ 说话人分离功能初始化失败，将禁用此功能")
            self.speaker_diarizer = None

        # 初始化会议集成（可选）
        if self.meeting_integration and not self.meeting_integration.initialize():
            print("⚠️ 会议集成功能初始化失败，将禁用此功能")
            self.meeting_integration = None

        print("✅ 系统初始化完成")
        return True

    def start_recording(self):
        """开始录制"""
        if not self.audio_capture.start_capture():
            return False

        self.is_running = True

        # 启动处理线程
        threading.Thread(target=self._audio_processing_loop, daemon=True).start()
        threading.Thread(
            target=self._transcription_processing_loop, daemon=True
        ).start()

        # 启动说话人分离线程（如果启用）
        if self.speaker_diarizer:
            threading.Thread(target=self._speaker_processing_loop, daemon=True).start()

        # 启动会议集成（如果启用）
        if self.meeting_integration:
            self.meeting_integration.start_integration()

        print("🎬 开始实时会议记录...")
        if self.meeting_integration:
            print("📱 会议软件自动检测已启用")
        print("💡 按 Ctrl+C 停止录制")

        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n⏹️  用户中断录制")
            self.stop_recording()

    def _audio_processing_loop(self):
        """音频处理循环"""
        while self.is_running:
            audio_chunk = self.audio_capture.get_audio_chunk()
            if audio_chunk:
                audio_data, timestamp = audio_chunk
                self.transcriber.add_audio_chunk(audio_data, timestamp)
            time.sleep(0.01)

    def _transcription_processing_loop(self):
        """转录处理循环"""
        while self.is_running:
            transcription = self.transcriber.get_transcription()
            if transcription:
                # 说话人分离处理
                if self.speaker_diarizer and self.speaker_segments:
                    transcription = (
                        self.speaker_diarizer.assign_speaker_to_transcription(
                            transcription, self.speaker_segments
                        )
                    )

                # 添加翻译
                if self.config.enable_translation:
                    transcription.translation = {}
                    for target_lang in self.config.target_languages:
                        translation = self.translator.translate_text(
                            transcription.text, transcription.language, target_lang
                        )
                        if translation:
                            transcription.translation[target_lang] = translation

                # 保存转录结果
                self.transcriptions.append(transcription)

                # 实时显示
                if self.config.realtime_display:
                    self._display_transcription(transcription)

                # 保存到文件
                self._save_transcription(transcription)

            time.sleep(0.01)

    def _speaker_processing_loop(self):
        """说话人分离处理循环"""
        audio_buffer = []
        buffer_duration = 10.0  # 10秒缓冲用于说话人分离

        while self.is_running:
            # 从音频捕获获取数据
            audio_chunk = self.audio_capture.get_audio_chunk()
            if audio_chunk:
                audio_data, timestamp = audio_chunk
                audio_buffer.append((audio_data, timestamp))

                # 检查缓冲区是否达到处理条件
                if (
                    len(audio_buffer)
                    >= buffer_duration
                    * self.config.sample_rate
                    / self.config.chunk_size
                ):
                    # 合并音频数据
                    audio_chunks = [chunk[0] for chunk in audio_buffer]
                    timestamps = [chunk[1] for chunk in audio_buffer]

                    combined_audio = np.concatenate(audio_chunks)
                    start_time = timestamps[0]

                    # 执行说话人分离
                    speaker_segments = self.speaker_diarizer.process_audio_chunk(
                        combined_audio, self.config.sample_rate
                    )

                    # 更新时间戳并保存说话人片段
                    for segment in speaker_segments:
                        segment.start_time += start_time
                        segment.end_time += start_time
                        self.speaker_segments.append(segment)

                    # 保持说话人片段列表不要太长（只保留最近5分钟）
                    current_time = time.time()
                    self.speaker_segments = [
                        seg
                        for seg in self.speaker_segments
                        if current_time - seg.end_time < 300  # 5分钟
                    ]

                    # 清空缓冲区（保留一点重叠）
                    overlap_size = len(audio_buffer) // 4
                    audio_buffer = audio_buffer[-overlap_size:]

            time.sleep(0.05)  # 说话人分离不需要太频繁

    def _display_transcription(self, transcription: TranscriptionSegment):
        """实时显示转录结果"""
        timestamp = datetime.datetime.fromtimestamp(transcription.start_time).strftime(
            "%H:%M:%S"
        )

        # 显示说话人信息
        speaker_info = ""
        if transcription.speaker_id and self.speaker_diarizer:
            speaker_name = self.speaker_diarizer.get_speaker_name(
                transcription.speaker_id
            )
            speaker_info = f" - {speaker_name}"

        print(f"\n[{timestamp}] {transcription.language.upper()}{speaker_info}")
        print(f"📝 {transcription.text}")

        if transcription.translation:
            for lang, translation in transcription.translation.items():
                print(f"🌐 {lang.upper()}: {translation}")

    def _save_transcription(self, transcription: TranscriptionSegment):
        """保存转录结果到文件"""
        session_dir = self.output_dir / self.session_id

        # 保存为JSON格式
        json_file = session_dir / "transcriptions.jsonl"
        with open(json_file, "a", encoding="utf-8") as f:
            json_data = {
                "timestamp": transcription.start_time,
                "start_time": transcription.start_time,
                "end_time": transcription.end_time,
                "text": transcription.text,
                "language": transcription.language,
                "speaker_id": transcription.speaker_id,
                "confidence": transcription.confidence,
                "translation": transcription.translation,
            }
            f.write(json.dumps(json_data, ensure_ascii=False) + "\n")

        # 保存为Markdown格式
        md_file = session_dir / "meeting_record.md"
        timestamp_str = datetime.datetime.fromtimestamp(
            transcription.start_time
        ).strftime("%H:%M:%S")

        with open(md_file, "a", encoding="utf-8") as f:
            # 添加说话人信息
            speaker_info = ""
            if transcription.speaker_id and self.speaker_diarizer:
                speaker_name = self.speaker_diarizer.get_speaker_name(
                    transcription.speaker_id
                )
                speaker_info = f" - {speaker_name}"

            f.write(
                f"\n## [{timestamp_str}] {transcription.language.upper()}{speaker_info}\n\n"
            )
            f.write(f"**原文**: {transcription.text}\n\n")

            if transcription.translation:
                for lang, translation in transcription.translation.items():
                    f.write(f"**{lang.upper()}**: {translation}\n\n")

    def stop_recording(self):
        """停止录制"""
        self.is_running = False
        self.audio_capture.stop_capture()

        # 停止会议集成（如果启用）
        if self.meeting_integration:
            self.meeting_integration.stop_integration()

        # 生成会议总结
        if self.transcriptions:
            self._generate_summary()

        print(f"📁 会议记录已保存到: {self.output_dir / self.session_id}")

    def _generate_summary(self):
        """生成会议总结"""
        session_dir = self.output_dir / self.session_id
        summary_file = session_dir / "meeting_summary.md"

        total_duration = 0
        if self.transcriptions:
            total_duration = (
                self.transcriptions[-1].end_time - self.transcriptions[0].start_time
            )

        languages = set(t.language for t in self.transcriptions)
        total_words = sum(len(t.text) for t in self.transcriptions)

        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"# 会议记录总结\n\n")
            f.write(
                f"**会议时间**: {datetime.datetime.fromtimestamp(self.transcriptions[0].start_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write(f"**会议时长**: {total_duration/60:.1f} 分钟\n")
            f.write(f"**检测语言**: {', '.join(languages)}\n")
            f.write(f"**转录字数**: {total_words} 字\n")
            f.write(f"**转录片段**: {len(self.transcriptions)} 段\n\n")

            if self.config.enable_translation:
                f.write(f"**翻译语言**: {', '.join(self.config.target_languages)}\n\n")

    def _on_meeting_audio_data(self, audio_data: np.ndarray, timestamp: float):
        """会议音频数据回调"""
        # 将会议音频数据传递给转录系统
        if self.is_running:
            self.transcriber.add_audio_chunk(audio_data, timestamp)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="实时会议记录系统")

    parser.add_argument(
        "--mode", choices=["realtime", "file"], default="realtime", help="运行模式"
    )
    parser.add_argument("--languages", default="zh,en", help="支持的语言（逗号分隔）")
    parser.add_argument("--output-dir", default="meeting_records", help="输出目录")
    parser.add_argument("--whisper-model", default="base", help="Whisper模型大小")
    parser.add_argument("--enable-translation", action="store_true", help="启用翻译")
    parser.add_argument(
        "--enable-speaker-diarization", action="store_true", help="启用说话人分离"
    )
    parser.add_argument(
        "--no-realtime-display", action="store_true", help="禁用实时显示"
    )
    parser.add_argument(
        "--enable-meeting-integration", action="store_true", help="启用会议软件自动检测"
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 解析语言列表
    target_languages = args.languages.split(",")[1:] if "," in args.languages else []
    primary_language = args.languages.split(",")[0]

    # 创建配置
    config = MeetingConfig(
        whisper_model=args.whisper_model,
        primary_language=primary_language,
        target_languages=target_languages,
        output_dir=args.output_dir,
        realtime_display=not args.no_realtime_display,
        enable_translation=args.enable_translation,
        enable_speaker_diarization=args.enable_speaker_diarization,
        enable_meeting_integration=args.enable_meeting_integration,
    )

    # 创建记录器
    recorder = MeetingRecorder(config)

    # 初始化并开始录制
    if recorder.initialize():
        recorder.start_recording()
    else:
        print("❌ 系统初始化失败")
        sys.exit(1)


if __name__ == "__main__":
    main()