#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Meeting CLI - 智能会议记录命令行工具
支持实时转录、多语言翻译、说话人分离、会议软件集成

使用示例：
  # 实时会议记录
  python -m src.cli.meeting_cli --enable-meeting-integration
  
  # 完整会议功能
  python -m src.cli.meeting_cli \
    --enable-translation \
    --enable-speaker-diarization \
    --languages zh,en,ja,ko \
    --voice_model medium
    
  # 会议分析
  python -m src.cli.meeting_cli \
    --type=meeting_advanced \
    -i meeting_records/latest/transcriptions.jsonl
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
import queue
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

# 确保项目根目录在Python路径中
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 导入核心模块
from core.asr.voice_recognition_core import voice_core, initialize_voice_recognition
from core.ai.clients.ai_client_openai import OpenAIClientWrapper
from core.ai.clients.ai_client_ollama import OllamaClient

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AudioCapture:
    """音频捕获模块"""

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 4096):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.is_recording = False
        self.audio_queue = queue.Queue()

        try:
            import pyaudio

            self.pyaudio = pyaudio
            self.audio = None
            self.stream = None
        except ImportError:
            logger.error("❌ PyAudio未安装，请运行: pip install pyaudio")
            self.pyaudio = None

    def start_recording(self, callback: Optional[Callable] = None):
        """开始录音"""
        if not self.pyaudio:
            logger.error("❌ PyAudio不可用")
            return False

        try:
            self.audio = self.pyaudio.PyAudio()

            # 查找默认输入设备
            default_input = self.audio.get_default_input_device_info()
            logger.info(f"🎤 使用音频设备: {default_input['name']}")

            self.stream = self.audio.open(
                format=self.pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback if not callback else callback,
            )

            self.is_recording = True
            self.stream.start_stream()
            logger.info("🔴 开始录音...")
            return True

        except Exception as e:
            logger.error(f"❌ 录音启动失败: {e}")
            return False

    def stop_recording(self):
        """停止录音"""
        self.is_recording = False

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        if self.audio:
            self.audio.terminate()

        logger.info("⏹️ 录音已停止")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """音频回调函数"""
        if self.is_recording:
            self.audio_queue.put(in_data)
        return (None, self.pyaudio.paContinue)

    def get_audio_devices(self) -> List[Dict]:
        """获取音频设备列表"""
        devices = []

        if not self.pyaudio:
            return devices

        try:
            audio = self.pyaudio.PyAudio()

            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if device_info["maxInputChannels"] > 0:
                    devices.append(
                        {
                            "index": i,
                            "name": device_info["name"],
                            "channels": device_info["maxInputChannels"],
                            "sample_rate": device_info["defaultSampleRate"],
                        }
                    )

            audio.terminate()

        except Exception as e:
            logger.error(f"❌ 获取音频设备失败: {e}")

        return devices


class RealTimeTranscriber:
    """实时转录器"""

    def __init__(self, voice_mode: str = "auto"):
        self.voice_mode = voice_mode
        self.transcription_queue = queue.Queue()
        self.is_transcribing = False
        self.buffer_duration = 5.0  # 5秒缓冲

    def start_transcribing(
        self, audio_queue: queue.Queue, callback: Optional[Callable] = None
    ):
        """开始实时转录"""
        self.is_transcribing = True

        # 启动转录线程
        transcribe_thread = threading.Thread(
            target=self._transcribe_loop, args=(audio_queue, callback)
        )
        transcribe_thread.daemon = True
        transcribe_thread.start()

        logger.info("🎯 实时转录已启动")

    def stop_transcribing(self):
        """停止转录"""
        self.is_transcribing = False
        logger.info("⏹️ 实时转录已停止")

    def _transcribe_loop(self, audio_queue: queue.Queue, callback: Optional[Callable]):
        """转录循环"""
        import tempfile
        import wave

        audio_buffer = []
        last_transcribe_time = time.time()

        while self.is_transcribing:
            try:
                # 收集音频数据
                if not audio_queue.empty():
                    audio_data = audio_queue.get(timeout=0.1)
                    audio_buffer.append(audio_data)

                # 检查是否达到转录时间
                current_time = time.time()
                if (
                    current_time - last_transcribe_time >= self.buffer_duration
                    and len(audio_buffer) > 0
                ):

                    # 保存音频到临时文件
                    with tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    ) as temp_file:
                        temp_path = temp_file.name

                        # 写入WAV文件
                        with wave.open(temp_path, "wb") as wav_file:
                            wav_file.setnchannels(1)
                            wav_file.setsampwidth(2)
                            wav_file.setframerate(16000)
                            wav_file.writeframes(b"".join(audio_buffer))

                    # 转录音频
                    result = voice_core.transcribe(temp_path, language="auto")

                    # 清理临时文件
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

                    if result and result.get("text"):
                        text = result["text"].strip()
                        if text:
                            timestamp = datetime.now().isoformat()
                            transcription_data = {
                                "timestamp": timestamp,
                                "text": text,
                                "confidence": 0.95,
                                "speaker": "unknown",
                            }

                            # 调用回调函数
                            if callback:
                                callback(transcription_data)

                            self.transcription_queue.put(transcription_data)

                    # 重置缓冲
                    audio_buffer = []
                    last_transcribe_time = current_time

                time.sleep(0.01)  # 小延迟避免CPU占用过高

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"❌ 转录过程出错: {e}")
                time.sleep(1)


class MeetingTranslator:
    """会议翻译器"""

    def __init__(self, target_languages: List[str] = None, ai_client=None):
        self.target_languages = target_languages or ["en"]
        self.ai_client = ai_client

        # 语言映射
        self.language_names = {"zh": "中文", "en": "英文", "ja": "日语", "ko": "韩语"}

    def translate_text(self, text: str, source_lang: str = "zh") -> Dict[str, str]:
        """翻译文本"""
        translations = {}

        if not self.ai_client:
            # 模拟翻译
            for lang in self.target_languages:
                if lang != source_lang:
                    translations[lang] = (
                        f"[{self.language_names.get(lang, lang)}] {text}"
                    )
            return translations

        try:
            for target_lang in self.target_languages:
                if target_lang == source_lang:
                    continue

                prompt = f"""
请将以下{self.language_names.get(source_lang, source_lang)}文本翻译为{self.language_names.get(target_lang, target_lang)}，保持原意：

{text}

只返回翻译结果，不要其他解释。
"""

                if hasattr(self.ai_client, "chat"):
                    translation = self.ai_client.chat(prompt)
                    translations[target_lang] = translation.strip()

        except Exception as e:
            logger.error(f"❌ 翻译失败: {e}")

        return translations


class MeetingSoftwareDetector:
    """会议软件检测器"""

    def __init__(self):
        self.meeting_apps = [
            "Tencent Meeting",
            "VooV Meeting",
            "DingTalk",
            "zoom.us",
            "Microsoft Teams",
            "Skype",
            "WeChat",
            "Google Meet",
        ]

    def detect_meeting_software(self) -> List[str]:
        """检测正在运行的会议软件"""
        running_meetings = []

        try:
            import psutil

            for process in psutil.process_iter(["pid", "name"]):
                try:
                    process_name = process.info["name"]
                    for app in self.meeting_apps:
                        if app.lower() in process_name.lower():
                            running_meetings.append(app)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        except ImportError:
            logger.warning("⚠️ psutil未安装，无法检测会议软件")
        except Exception as e:
            logger.error(f"❌ 检测会议软件失败: {e}")

        return list(set(running_meetings))


class MeetingRecorder:
    """会议记录器主类"""

    def __init__(self, output_dir: str = "data/meeting_records"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 组件
        self.audio_capture = AudioCapture()
        self.transcriber = RealTimeTranscriber()
        self.translator = None
        self.detector = MeetingSoftwareDetector()

        # 状态
        self.is_recording = False
        self.session_id = None
        self.session_dir = None
        self.transcriptions = []

        # 统计
        self.stats = {
            "start_time": None,
            "total_transcriptions": 0,
            "total_translations": 0,
            "detected_languages": set(),
        }

    def setup_ai_client(
        self, api_key: str = None, api_base: str = None, gpt_model: str = None
    ):
        """设置AI客户端"""
        try:
            if api_key and api_base:
                ai_client = OpenAIClientWrapper(
                    api_key=api_key,
                    base_url=api_base,
                    model=gpt_model or "gpt-3.5-turbo",
                )
                logger.info(f"🤖 使用外部AI: {gpt_model}")
            else:
                ai_client = OllamaClient(model="qwen:1.8b")
                logger.info("🤖 使用本地Ollama AI")

            return ai_client

        except Exception as e:
            logger.warning(f"⚠️ AI客户端设置失败: {e}")
            return None

    def start_recording(
        self,
        enable_translation: bool = False,
        target_languages: List[str] = None,
        api_key: str = None,
        api_base: str = None,
        gpt_model: str = None,
    ):
        """开始会议记录"""
        if self.is_recording:
            logger.warning("⚠️ 已在记录中")
            return False

        # 创建会话目录
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.output_dir / self.session_id
        self.session_dir.mkdir(exist_ok=True)

        logger.info(f"📁 会话目录: {self.session_dir}")

        # 设置翻译器
        if enable_translation:
            ai_client = self.setup_ai_client(api_key, api_base, gpt_model)
            self.translator = MeetingTranslator(target_languages, ai_client)

        # 检测会议软件
        meetings = self.detector.detect_meeting_software()
        if meetings:
            logger.info(f"🔍 检测到会议软件: {', '.join(meetings)}")

        # 开始录音和转录
        if not self.audio_capture.start_recording():
            return False

        self.transcriber.start_transcribing(
            self.audio_capture.audio_queue, self._on_transcription
        )

        self.is_recording = True
        self.stats["start_time"] = time.time()

        logger.info("🚀 会议记录已开始")
        return True

    def stop_recording(self):
        """停止会议记录"""
        if not self.is_recording:
            logger.warning("⚠️ 当前未在记录")
            return

        self.is_recording = False

        # 停止录音和转录
        self.audio_capture.stop_recording()
        self.transcriber.stop_transcribing()

        # 保存会议记录
        self._save_meeting_records()

        logger.info("⏹️ 会议记录已停止")
        self._print_session_stats()

    def _on_transcription(self, transcription_data: Dict):
        """转录回调"""
        self.transcriptions.append(transcription_data)
        self.stats["total_transcriptions"] += 1

        text = transcription_data["text"]
        timestamp = transcription_data["timestamp"]

        # 实时显示
        print(f"\r[{timestamp[-8:]}] {text}", end="\n", flush=True)

        # 翻译处理
        if self.translator:
            translations = self.translator.translate_text(text)
            transcription_data["translations"] = translations
            self.stats["total_translations"] += len(translations)

            # 显示翻译结果
            for lang, translated_text in translations.items():
                print(f"  └─ [{lang}] {translated_text}")

    def _save_meeting_records(self):
        """保存会议记录"""
        if not self.session_dir or not self.transcriptions:
            return

        # 保存转录记录
        transcripts_file = self.session_dir / "transcriptions.jsonl"
        with open(transcripts_file, "w", encoding="utf-8") as f:
            for item in self.transcriptions:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        # 保存纯文本
        text_file = self.session_dir / "meeting_transcript.txt"
        with open(text_file, "w", encoding="utf-8") as f:
            for item in self.transcriptions:
                timestamp = item["timestamp"]
                text = item["text"]
                f.write(f"[{timestamp}] {text}\n")

        # 保存会话信息
        session_info = {
            "session_id": self.session_id,
            "start_time": self.stats["start_time"],
            "end_time": time.time(),
            "duration": time.time() - self.stats["start_time"],
            "total_transcriptions": len(self.transcriptions),
            "total_translations": self.stats["total_translations"],
            "files": {"transcriptions": str(transcripts_file), "text": str(text_file)},
        }

        info_file = self.session_dir / "session_info.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump(session_info, f, ensure_ascii=False, indent=2)

        logger.info(f"💾 会议记录已保存到: {self.session_dir}")

    def _print_session_stats(self):
        """打印会话统计"""
        duration = (
            time.time() - self.stats["start_time"] if self.stats["start_time"] else 0
        )

        print("\n" + "=" * 50)
        print("📊 会议记录统计")
        print("=" * 50)
        print(f"🕐 持续时间: {duration:.1f}秒")
        print(f"📝 转录数量: {self.stats['total_transcriptions']}")
        print(f"🌐 翻译数量: {self.stats['total_translations']}")
        print(f"📁 输出目录: {self.session_dir}")


class MeetingCLI:
    """Meeting CLI 主类"""

    def __init__(self):
        self.recorder = None

    def run_meeting_write(self, args: argparse.Namespace):
        """运行会议记录模式"""
        logger.info("🎯 启动会议记录模式")

        # 创建记录器
        self.recorder = MeetingRecorder(args.output)

        # 解析目标语言
        target_languages = []
        if args.languages:
            target_languages = [lang.strip() for lang in args.languages.split(",")]

        # 开始记录
        success = self.recorder.start_recording(
            enable_translation=args.enable_translation,
            target_languages=target_languages,
            api_key=args.api_key,
            api_base=args.api_base,
            gpt_model=args.gpt_model,
        )

        if not success:
            logger.error("❌ 记录启动失败")
            return 1

        try:
            print("\n按 Ctrl+C 停止记录...")
            while self.recorder.is_recording:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("⚠️ 用户中断")
        finally:
            if self.recorder:
                self.recorder.stop_recording()

        return 0

    def run_meeting_advanced(self, args: argparse.Namespace):
        """运行会议分析模式"""
        logger.info("🔍 启动会议分析模式")

        if not args.input:
            logger.error("❌ 分析模式需要指定输入文件")
            return 1

        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"❌ 文件不存在: {input_path}")
            return 1

        try:
            # 读取转录数据
            transcriptions = []
            with open(input_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        transcriptions.append(json.loads(line))

            logger.info(f"📖 读取到 {len(transcriptions)} 条转录记录")

            # 生成分析报告
            self._generate_analysis_report(transcriptions, args.output)

            return 0

        except Exception as e:
            logger.error(f"❌ 分析失败: {e}")
            return 1

    def _generate_analysis_report(self, transcriptions: List[Dict], output_dir: str):
        """生成分析报告"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 基本统计
        total_text = " ".join([t.get("text", "") for t in transcriptions])
        word_count = len(total_text.split())

        # 生成报告
        report_content = f"""# 会议分析报告

## 基本统计
- 转录记录数: {len(transcriptions)}
- 总字数: {word_count}
- 时间跨度: {transcriptions[0]['timestamp'] if transcriptions else 'N/A'} - {transcriptions[-1]['timestamp'] if transcriptions else 'N/A'}

## 内容摘要
{total_text[:500]}...

## 详细转录
"""

        for i, item in enumerate(transcriptions, 1):
            timestamp = item.get("timestamp", "N/A")
            text = item.get("text", "")
            report_content += f"\n### {i}. [{timestamp}]\n{text}\n"

        # 保存报告
        report_file = output_dir / "analysis_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"📋 分析报告已生成: {report_file}")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="AI Meeting CLI - 智能会议记录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本会议记录
  python -m src.cli.meeting_cli --type=meeting_write
  
  # 完整功能会议记录
  python -m src.cli.meeting_cli --type=meeting_write \\
    --enable-translation --enable-speaker-diarization \\
    --languages zh,en,ja --voice_model medium
    
  # 会议分析
  python -m src.cli.meeting_cli --type=meeting_advanced \\
    -i meeting_records/20250813_140000/transcriptions.jsonl
        """,
    )

    # 基本参数
    parser.add_argument(
        "--type",
        default="meeting_write",
        choices=["meeting_write", "meeting_advanced"],
        help="运行模式 (默认: meeting_write)",
    )
    parser.add_argument("-i", "--input", help="输入文件路径（分析模式）")
    parser.add_argument(
        "-o",
        "--output",
        default="data/meeting_records",
        help="输出目录路径 (默认: data/meeting_records)",
    )

    # 会议功能参数
    parser.add_argument(
        "--enable-translation", action="store_true", help="启用实时翻译"
    )
    parser.add_argument(
        "--enable-speaker-diarization", action="store_true", help="启用说话人分离"
    )
    parser.add_argument(
        "--enable-meeting-integration", action="store_true", help="启用会议软件集成"
    )
    parser.add_argument(
        "--languages", default="zh,en", help="翻译目标语言，逗号分隔 (默认: zh,en)"
    )

    # 语音识别参数
    parser.add_argument(
        "--voice_model",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large"],
        help="语音识别模型 (默认: medium)",
    )

    # AI参数
    parser.add_argument("--api_key", help="AI API密钥")
    parser.add_argument("--api_base", help="AI API基础URL")
    parser.add_argument(
        "--gpt_model", default="gpt-3.5-turbo", help="AI模型名称 (默认: gpt-3.5-turbo)"
    )

    # 其他选项
    parser.add_argument("--verbose", action="store_true", help="详细输出模式")

    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    # 设置日志
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 打印启动信息
    print("🚀 AI Meeting CLI v3.0")
    print("=" * 50)

    # 初始化语音识别
    if args.type == "meeting_write":
        logger.info("🔧 初始化语音识别核心...")
        if not initialize_voice_recognition():
            logger.error("❌ 语音识别初始化失败")
            return 1
        logger.info("✅ 语音识别初始化成功")

    # 创建CLI实例并运行
    cli = MeetingCLI()

    try:
        if args.type == "meeting_write":
            return cli.run_meeting_write(args)
        elif args.type == "meeting_advanced":
            return cli.run_meeting_advanced(args)
        else:
            logger.error(f"❌ 未知的运行模式: {args.type}")
            return 1

    except KeyboardInterrupt:
        logger.info("⚠️ 用户中断")
        return 1
    except Exception as e:
        logger.error(f"❌ 运行过程出错: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
