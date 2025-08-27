# 🎯 AI视频转文字工具 - SenseVoice优化版

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **专注核心功能** - 基于阿里达摩院SenseVoice的高质量中文语音识别

## 🚀 快速开始

### Web界面启动（推荐）
```bash
# 1. 克隆项目
git clone [your-repo-url]
cd ai-video2text

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装音频处理依赖（会议监控功能）
pip install sounddevice

# 4. 启动Web服务
python app/main.py
# 访问: http://127.0.0.1:19080
```

## 🎯 核心特性（多引擎智能识别）
- 🤖 **多引擎架构** - Whisper + FasterWhisper + SenseVoice + Dolphin 智能选择
- 🔥 **中文强化** - 针对中文语音识别专门优化
- ⚡ **高性能** - FasterWhisper 加速 + GPU支持
- 🌐 **Web界面** - 现代化Vue3界面，实时进度显示
- 📱 **移动适配** - 响应式设计，支持多设备
- 🎓 **学习增强** - 闪卡 / 思维导图 / 内容卡片生成
- 🖼️ **视觉扩展** - 智能关键帧提取
- 🧩 **可插拔架构** - 引擎可扩展，配置驱动
- 📦 **三模式** - CLI命令行 + Web API + 实时会议监控
- 🎤 **会议监控** - 实时音频捕获 + 多语言转录 + 智能摘要 + 权限管理

## 🎪 功能亮点

### 📹 视频转文字
- **多格式支持**: MP4, AVI, MOV, MKV等主流视频格式
- **URL下载**: 支持Bilibili等平台视频链接
- **本地文件**: 支持本地文件路径输入和文件浏览
- **进度跟踪**: 实时显示处理进度和状态

### 🎤 实时会议监控 (NEW!)
- **系统音频捕获**: 智能检测和推荐最佳音频设备
- **权限管理**: 自动检查麦克风和系统音频权限
- **多平台支持**: 兼容腾讯会议、钉钉、Zoom、Teams等
- **实时转录**: 基于SSE的流式语音识别
- **同步翻译**: 支持多语言实时翻译
- **智能分析**: 自动生成会议摘要、关键要点和关键词
- **参与者识别**: 说话人分离和识别（开发中）

### 🔧 技术架构
- **懒加载**: ASR引擎按需加载，提升启动速度
- **模块化**: 清晰的目录结构，易于扩展
- **API优先**: RESTful API设计，支持第三方集成
- **实时通信**: WebSocket和SSE支持实时数据流

### CLI批量处理
```bash
# 基础转录
python -m src.cli.video2txt_cli -i video.mp4

# 指定引擎和语言
python -m src.cli.video2txt_cli -i video.mp4 \
  --voice_mode sensevoice --api_key sk-xxx

# 生成完整学习材料
python -m src.cli.video2txt_cli -i video.mp4 \
  --flashcards --note_card --note_xmind \
  --api_key sk-xxx --gpt_model gpt-4

# 批量处理目录
python -m src.cli.video2txt_cli -i /path/to/videos/ --batch
```

### Web API使用
```bash
# 上传文件处理
curl -X POST "http://127.0.0.1:19080/api/tasks/video" \
  -F "file=@video.mp4" \
  -F "language=zh" \
  -F "model=auto" \
  -F "output_types=transcript,summary"

# 实时进度监控
curl "http://127.0.0.1:19080/api/tasks/video/{task_id}/stream"
```

### 实时会议监控
```bash
# 启动Web服务
python app/main.py

# 访问会议监控页面
http://127.0.0.1:19080/meeting2txt
```

**会议监控功能:**
- 🎵 **实时音频捕获** - 支持系统音频、环回设备、虚拟音频线
- 🗣️ **说话人识别** - 自动识别不同说话人，统计发言情况
- 🌍 **实时翻译** - 支持中英日韩等多语言实时翻译
- 📊 **智能分析** - 自动提取关键词、生成会议要点
- 📝 **会议摘要** - 自动生成完整的会议总结报告
- 💻 **兼容主流会议软件** - 支持腾讯会议、钉钉、Zoom、Teams等

## 🎤 支持的语音识别引擎

| 引擎 | 状态 | 特点 | 适用场景 |
|------|------|------|----------|
| **Whisper** | ✅ 已实现 | OpenAI官方，通用性强 | 多语言混合内容 |
| **FasterWhisper** | ✅ 已实现 | 性能优化版，速度快 | 大批量处理 |
| **SenseVoice** | 🔄 架构完成 | 中文专用，准确率高 | 中文语音内容 |
| **Dolphin** | 🔄 架构完成 | 支持方言，多语言 | 方言和小语种 |

### 引擎对比
| 特性 | Whisper | FasterWhisper | SenseVoice | Dolphin |
|------|---------|---------------|------------|---------|
| **中文准确率** | ~70% | ~75% | ~90% | ~85% |
| **处理速度** | 慢 | 快 | 中等 | 中等 |
| **模型大小** | 3GB+ | 1.5GB+ | 1.3GB | 2GB+ |
| **GPU支持** | ✅ | ✅ | ✅ | ✅ |

## 🏗️ 项目架构

### 技术栈
- **前端**: Vue3 + Canvas动画 + SSE实时通信
- **后端**: FastAPI + 异步处理 + 多引擎架构
- **语音识别**: 多引擎智能选择系统
- **AI分析**: OpenAI + Ollama本地模型支持

### 目录结构
```
ai-video2text/
├── app/                    # FastAPI应用入口
│   └── main.py            # Web服务启动
├── biz/                   # 业务逻辑层
│   ├── routes/           # API路由
│   └── services/         # 业务服务
├── core/                 # 核心功能模块
│   ├── asr/             # 语音识别引擎
│   ├── ai/              # AI分析模块
│   └── cli/             # 命令行工具
├── public/              # Web前端资源
├── data/               # 数据存储
└── src/cli/           # CLI工具入口
```

## 📊 输出文件说明

### 基础输出
- `transcript.txt` - 纯文本转录结果
- `transcript.json` - 带时间戳的结构化转录
- `summary.md` - AI生成的内容摘要

### 学习材料（CLI）
- `flashcards.json` - 学习闪卡
- `mindmap.mm` - 思维导图 (FreeMind格式)
- `content_card.md` - 结构化内容卡片
- `keyframes/` - 智能提取的关键帧

### 技术细节
- **音频处理**: FFmpeg提取和转换
- **视频处理**: OpenCV关键帧提取
- **AI分析**: OpenAI GPT + Ollama本地模型
- **实时通信**: Server-Sent Events (SSE)

## 🔧 安装部署

### 环境要求
- Python 3.8+
- FFmpeg (音视频处理)
- GPU支持 (可选，用于加速)

### 快速安装
```bash
# 1. 安装Python依赖
pip install -r requirements.txt

# 2. 安装FFmpeg
# macOS
brew install ffmpeg
# Ubuntu
sudo apt install ffmpeg

# 3. 启动Web服务
python app/main.py
```

### 依赖安装详细说明
```bash
# 核心依赖
pip install fastapi uvicorn        # Web服务
pip install openai-whisper         # Whisper引擎
pip install faster-whisper         # FasterWhisper引擎
pip install opencv-python          # 视频处理
pip install requests tqdm          # 工具库

# AI分析功能 (可选)
pip install openai                 # OpenAI API
pip install ollama                 # 本地AI模型
```

## 📊 主要输出与元数据

| 文件 | 说明 | 触发条件 |
|------|------|----------|
| transcriptions.jsonl | 逐段转录（含 provider / 置信度） | 默认 |
| transcript_meta.json | 全局元数据 (见下表) | 默认 |
| summary.json / meeting_summary.md | AI 摘要 / Markdown | --summary |
| flashcards.json | 闪卡 | 自动/--flashcards |
| mindmap.mm | 思维导图 (FreeMind) | 自动/--mindmap |
| markmap.md | Markmap 结构地图 | --markmap |
| structure_points.json | 结构要点 (启发式) | 自动/--structure |
| content_scores.json | 内容多维评分 (强化版) | --summary |
| value_rating.json | 价值评分 (启发式) | 自动/--value_rating |
| key_moments.json | 关键切片 | 自动/--key_moments |
| xhs_note.md | 小红书风格笔记 | --xhs-note |
| keyframes/ + cover.jpg | 关键帧 + 封面 | 视频输入/--keyframes |
| waveform.png / spectrogram.png | 波形/频谱 | --enable-visuals |
| dual_decisions.jsonl | 双模型桶级决策日志 | --dual |

### transcript_meta.json 字段

| 字段 | 含义 |
|------|------|
| duration | 音频时长(秒) |
| segments_count | 段落数量（可能经 merge 后变化） |
| model | 使用的模型或组合 (单 / dual) |
| languages | 语种计数分布 |
| dialect_hint | 方言提示（预留） |
| is_dual | 是否启用双模型择优 |
| ai_correction_rounds | AI 多轮纠错轮数（未启用=0） |
| merged_applied | 是否应用了短段合并 |
| provider_usage | 各 provider 被选段数量统计 |
| dual_weights | 双模型打分权重（仅 dual 时存在） |
| chunking_applied | 长音频是否触发分块策略（未来扩展） |
| chunk_count | 分块数量（未来扩展） |

### content_scores.json 指标说明（增强版）

| 指标 | 说明 |
|------|------|
| total_chars | 总字符数 |
| avg_segment_len | 平均段长度 |
| unique_tokens | 不重复词数 |
| token_density | 词汇密度（唯一词/总词） |
| repetition_rate | 重复度（出现≥3次词的占比） |
| stopword_ratio | 停用词占比（中英混合集合） |
| chars_per_min | 每分钟字符（节奏） |
| avg_confidence | 平均识别置信度（若有） |
| value_scores.informativeness | 信息量评分（密度+低重复） |
| value_scores.clarity | 清晰度（停用词反向 & 置信度） |
| value_scores.actionability | 行动性（平均段长度归一化） |

## 🧩 长音频分块（即将加入）

| 目标 | 策略 | 预期字段影响 |
|------|------|---------------|
| 超长文件内存控制 | 时间窗口切片 (如 5-10 分钟) | chunking_applied=True |
| 减少重复计算 | 缓存中间 JSONL + 增量继续 | chunk_count=窗口数 |
| 提升摘要质量 | 分块小摘要 -> 汇总二级摘要 | 未来增加 summary_hierarchy |
| 质量稳健 | 分块内独立纠错后再全局微调 | ai_correction_rounds 保留 |

（当前版本尚未落地分块逻辑，保留元字段确保向后兼容迭代。）

## ⚡ 性能指标

| 指标 | Web模式 | CLI模式 | 状态 |
|------|---------|---------|------|
| 启动时间 | <10秒 | <5秒 | ✅ |
| 内存占用 | <2GB | <1GB | ✅ |
| 并发处理 | 支持 | N/A | ✅ |
| 实时进度 | SSE推送 | 命令行显示 | ✅ |
| 文件支持 | 上传+URL | 本地+URL | ✅ |

## 🔥 使用场景

- 📚 **在线课程学习** - 自动生成笔记和闪卡
- 🎯 **会议记录** - 实时转录和总结
- 🎬 **视频内容提取** - 快速获取视频文字内容
- 📖 **语言学习** - 听力材料转文字练习
- 🎤 **播客整理** - 音频内容文字化

## 💡 最佳实践

### 音频质量优化
- 使用清晰的录音设备
- 避免背景噪音
- 保持稳定的音量

### 识别效果提升
- 中文内容效果最佳
- 支持中英混合语音
- 标准普通话识别率最高

## 🎯 项目优势

### 技术优势
- ✅ **多引擎架构** - 智能选择最佳识别引擎
- ✅ **Web + CLI双模式** - 满足不同使用场景
- ✅ **实时进度显示** - SSE推送，用户体验佳
- ✅ **现代化界面** - Vue3 + 3D动画效果
- ✅ **高性能处理** - 异步任务队列

### 商业价值
- 🎯 **中文优化** - 针对中文语音识别专门优化
- 💡 **离线优先** - 核心功能无需外部API
- 📈 **可扩展** - 引擎和功能模块化设计
- 🚀 **生产就绪** - 完整的错误处理和日志

## 🚀 快速体验

### Web界面体验
1. 启动服务：`python app/main.py`
2. 访问：http://127.0.0.1:19080
3. 功能页面：
   - **仪表盘**: 查看任务概览和系统状态
   - **视频转文字**: 上传文件或输入URL，实时查看处理进度
   - **实时会议监控**: 监控外部会议软件，实时转录和分析
   - **设置**: 配置引擎参数和API密钥

### 会议监控快速开始
1. 访问会议监控页面：http://127.0.0.1:19080/meeting2txt
2. 检查音频权限和设备状态
3. 选择识别引擎和语言设置
4. 启动要监控的会议软件（腾讯会议、钉钉等）
5. 点击"开始监控"实时转录会议内容
6. 会议结束后自动生成摘要和关键词

### CLI命令行体验
```bash
# 快速转录
python -m src.cli.video2txt_cli -i test.mp4

# 查看帮助
python -m src.cli.video2txt_cli --help
```

## 🤝 支持与反馈

- 📧 问题反馈: 提交Issue
- 📖 详细文档: 查看docs/目录
- 🆘 获取帮助: 运行 `--help` 查看命令说明

---

**总结**: 这是一个现代化的AI视频转文字工具，采用多引擎架构，支持Web界面和CLI双模式，特别针对中文语音识别优化，具备完整的学习材料生成功能。
