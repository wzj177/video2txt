# 听语 AI 视频/音频转写平台

本项目是面向本地部署与私有化使用的转写与内容抽取平台，覆盖视频/音频转写、会议录音处理、结构化内容输出与任务管理。支持本地与云端 ASR 混合使用，适合需要稳定、可控、可扩展的生产场景。

## 适用场景
- 会议记录与归档
- 访谈/播客/课堂内容整理
- 视频内容转写与二次编辑
- 多语言素材整理与检索

## 核心能力
- 多引擎 ASR：本地与云端可切换
- Web UI + REST API + CLI
- 任务队列与进度追踪
- 结构化输出：摘要、思维导图、内容卡片、学习卡片、关键帧
- 说话人日志（手动生成）


## 特色功能
- 角色内容提示词模板与内容类型绑定
- 支持自定义提示词（DIY），便于内容生成调试
- 思维导图一键截图，支持导入 XMind
- 精准音视频转录（多引擎可选）
- 说话人日志生成

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

## ASR 模型与 API 说明
- **本地 ASR**：Whisper / FasterWhisper / SenseVoice / Dolphin（设置 → 语音模型 → 本地模型）
- **云端 ASR**：DashScope Qwen3-ASR（Flash / FileTrans / Realtime）
  - FileTrans 需要 OSS 配置与公网可访问 URL，并安装 `oss2`
  - Realtime 使用 PCM/OPUS 流式输入
- **远程 API**：设置 → 语音模型 → 云端 / 远程（Base URL + Endpoint + 鉴权）
- **WhisperX**：设置 → 语音模型 → WhisperX（说话人分离，需 Hugging Face Token）

> Qwen3-ASR 不提供说话人日志，需在会议详情中手动触发生成（本地模型：`models/speaker-diarization-community-1`）。

## API 文档
- [docs/API.md](docs/API.md)

## 0 → 1 使用流程
- 文档：[docs/用户从0到1使用指南.md](docs/用户从0到1使用指南.md)
- 建议从“设置”页开始配置 ASR、云端 API 与 OSS。

## 输出
任务输出目录：`data/outputs/<task_id>/`

常见输出包括：
- 转写文本（txt / json）
- 摘要
- 思维导图
- 内容卡片
- 学习卡片（md / csv）
- 关键帧

## 目录结构
```
app/            FastAPI 入口
biz/            路由与业务服务
core/           ASR/AI/音频引擎
public/         Web 前端
commands/       CLI 工作流
models/         本地模型
data/           任务输入/输出
```

- ![首页](example/images/首页.png)
- ![Dashboard](example/images/面板.png)
- ![任务详情](example/images/任务详情.png)
- ![任务列表](example/images/任务列表.png)
- ![内容卡片](example/images/内容卡片.png)
- ![思维导图](example/images/思维导图.png)
- ![会议列表](example/images/会议列表.png)
- ![会议详情](example/images/会议详情.png)

## License
MIT
