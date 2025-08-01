# AI 视频/音频转写工具

面向本地部署与私有化使用的转写与内容抽取服务，支持视频/音频转写、会议流程、内容总结与结构化输出。

# AI Video/Audio Transcription Tool

A local-first transcription and content extraction service for video/audio, with meeting workflows and structured outputs.

## 主要功能
- 多引擎转写（本地与云端 ASR）
- Web UI + REST API
- 会议音频上传与实时采集流程
- 说话人日志（手动触发生成）
- 内容输出：摘要、思维导图、内容卡片、学习卡片、关键帧

## Key Features
- Multi-engine ASR (local + cloud)
- Web UI + REST API
- Meeting upload & live capture flows
- Speaker diarization (manual trigger)
- Outputs: summary, mind map, content cards, flashcards, keyframes

## 快速开始
```bash
# macOS
pip install -r requirements-mac.txt

# Windows
pip install -r requirements-win.txt

# (可选) 实时会议采集依赖
pip install sounddevice

# 启动服务
python app/main.py
# 打开: http://127.0.0.1:19080
```

## Quick Start
```bash
# macOS
pip install -r requirements-mac.txt

# Windows
pip install -r requirements-win.txt

# (Optional) Live meeting capture dependency
pip install sounddevice

# Start service
python app/main.py
# Open: http://127.0.0.1:19080
```

## CLI
```bash
# End-to-end CLI workflow
python commands/beta/3.0/video2txt.py -i sample.mp4
```

## Web API
```bash
# Upload a video file
curl -X POST "http://127.0.0.1:19080/api/tasks/video" \
  -F "file=@video.mp4" \
  -F "language=auto"

# Stream progress
curl "http://127.0.0.1:19080/api/tasks/video/{task_id}/stream"
```

## 输出
每个任务会写入 `data/outputs/<task_id>/`，常见文件包括：
- 转写文本（纯文本与结构化 JSON）
- 摘要
- 思维导图
- 内容卡片
- 学习卡片（md/csv）
- 关键帧

具体输出取决于任务配置与模板。

## Outputs
Each task writes to `data/outputs/<task_id>/`. Typical outputs include:
- Transcript (text + structured JSON)
- Summary
- Mind map
- Content cards
- Flashcards (md/csv)
- Keyframes

Exact files depend on task configuration and templates.

## 模型与引擎
可用引擎取决于本地依赖与 API Key。配置在设置页完成。

- 本地引擎（如 Whisper / FasterWhisper / SenseVoice / Dolphin）
- 云端引擎（如 DashScope Qwen3-ASR）

Qwen3-ASR 不提供说话人日志。需要时可在会议详情中手动触发说话人日志生成，使用本地模型
`models/speaker-diarization-community-1`。

## Models & Engines
Available engines depend on local installation and API keys. Configure via Settings.

- Local engines (e.g., Whisper / FasterWhisper / SenseVoice / Dolphin)
- Cloud engines (e.g., DashScope Qwen3-ASR)

Qwen3-ASR does not provide speaker logs. Generate them manually using the local model
`models/speaker-diarization-community-1`.

## 配置说明
- 需要 FFmpeg 进行媒体转换与关键帧提取。
- API Key 与引擎参数在设置页配置。
- 大模型存放于 `models/`，除 `models/speaker-diarization-community-1` 外默认不入库。

## Configuration Notes
- FFmpeg is required for media conversion and keyframe extraction.
- API keys and engine settings are managed in Settings.
- Large models live under `models/`, only `models/speaker-diarization-community-1` is tracked.

## 目录结构
```
app/            FastAPI 入口
biz/            路由与业务服务
core/           ASR/AI/音频引擎
public/         Web 前端
commands/       CLI 工作流
data/           任务输入/输出
models/         本地模型
```

## Project Structure
```
app/            FastAPI entrypoint
biz/            routes and services
core/           ASR/AI/audio engines
public/         Web UI
commands/       CLI workflows
data/           task inputs/outputs
models/         local models
```

## 测试
```bash
pytest -q
```

## License
