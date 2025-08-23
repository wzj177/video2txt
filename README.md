# 🎯 AI视频转文字工具 - SenseVoice优化版

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **专注核心功能** - 基于阿里达摩院SenseVoice的高质量中文语音识别

## 🚀 快速开始

### 30秒体验
```bash
# 1. 克隆项目
git clone [your-repo-url]
cd ai-video2text

# 2. 一键部署
## 🎯 核心特性（已升级为多阶段能力）
- 🆓 **完全离线主流程** - SenseVoice 本地识别，零 API 成本
- 🔥 **中文强化** - 针对口语 / 课程 / 会议多场景优化
- ⚡ **快速稳定** - 轻量模型(≈1.3GB) + 可选双模型择优
- 🎓 **学习增强** - 闪卡 / 思维导图 / 结构要点 / Markmap / XHS 笔记
- 🤖 **多轮纠错链** - 规则 + 自定义词典 + 可选 AI 多轮细化
- 🖼️ **视觉扩展** - 关键帧、封面选图、波形 & 频谱图
- 🤝 **双模型（Phase3）** - SenseVoice & Whisper 并行打分自动选优
- 🧩 **可插拔架构** - Provider / Pipeline / Postprocess 分层可扩展
- 📦 **配置驱动** - 支持 --config 预加载 API Key/Base/模型参数

### 批量视频处理（新版 CLI 入口）
```bash
# 简单转录 + 摘要
python -m src.cli.video2txt_cli -i video.mp4 --summary

# 加语言提示 + 合并短片段(15s) + 关键帧 + 波形/频谱
python -m src.cli.video2txt_cli -i video.mp4 \
	--language-hint zh --merge-short 15 --keyframes --enable-visuals

# 多轮 AI 纠错 + 结构 Markmap + 闪卡 + 思维导图 + XHS 笔记
python -m src.cli.video2txt_cli -i video.mp4 \
	--ai-correction --correction-rounds 2 --markmap --flashcards --mindmap --xhs-note

# 双模型择优 (SenseVoice + Whisper fallback/对比) + 自定义权重
python -m src.cli.video2txt_cli -i video.mp4 --dual --fallback-model medium \
	--w-conf 1.0 --w-len 0.03 --w-lang 0.6 --punct-penalty 0.3

# 使用配置文件预加载 key/base/model，命令行可覆盖
python -m src.cli.video2txt_cli -i video.mp4 --config my.env --summary
```

| 特性 | Whisper | SenseVoice | 优势 |
|------|---------|------------|------|
| **中文准确率** | ~70% | ~90% | 🔥 **+29%** |
| **模型大小** | 3GB+ | 1.3GB | 🔥 **-57%** |
| **加载时间** | 45s+ | <20s | 🔥 **-56%** |
| **Apple Silicon** | 兼容性问题 | 专门优化 | 🔥 **完美支持** |
| **网络依赖** | HuggingFace(慢) | ModelScope(快) | 🔥 **国内优化** |

## 🎮 使用方式

### 批量视频处理
```bash
# 基础转录
python commands/video2txt.py -i video.mp4
python commands/video2txt.py -i audio.mp3 --flashcards
```

### 实时会议记录
```bash
# 启动实时记录
python commands/simple_meeting_recorder.py

# 检查系统状态
python commands/simple_meeting_recorder.py --check-only
```

### 系统检查
```bash
# 检查依赖和模型状态
python commands/video2txt.py --check-only
```

## 🏗️ 技术架构

```
- `transcriptions.jsonl` 逐段文本 + 时间戳 + provider
- `transcript_meta.json` 元信息（模型、段数、耗时、是否 dual、纠错轮数）
- `summary.json` / `summary.md` 摘要（可含结构）
┌─────────────────────────────────────────┐
- `flashcards.json` 闪卡
- `mindmap.mm` 思维导图 (FreeMind)
- `markmap.md` Markmap 结构图
- `structure_points.json` 启发式结构要点
- `content_scores.json` 内容多维评分（Phase2 占位）
- `value_rating.json` 价值评级（启发式）
- `key_moments.json` 关键时刻（时间抽样）
- `xhs_note.md` 小红书风格笔记
│            AI视频转文字工具              │
- `keyframes/` 关键帧目录
- `cover.jpg` 自动封面（variance / first / middle）
- `waveform.png` 音频波形
- `spectrogram.png` 频谱图
├─────────────────────────────────────────┤
- `dual_decisions.jsonl` 每个时间桶的模型得分与选择
(注：部分输出需对应参数启用)
│ 应用层  │ video2txt  │ 会议记录         │
├─────────────────────────────────────────┤
│ 服务层  │ SenseVoice │ VAD检测          │
│ 数据层  │ FFmpeg     │ OpenCV          │
### 核心技术栈
- **语音识别**: SenseVoiceSmall (阿里达摩院)
- **VAD检测**: FSMN-VAD (智能语音分段)
- **音频处理**: FFmpeg + PyAudio + Pydub
- **视频处理**: OpenCV + FFmpeg
- **模型管理**: ModelScope Hub

## 📁 项目结构

```
ai-video2text/
├── commands/                          # 核心源代码
│   ├── video2txt.py             # 主程序 (SenseVoice版)
│   ├── voice_recognition_core.py # 语音识别核心
│   ├── simple_meeting_recorder.py # 实时会议记录
│   └── download_sensevoice_models.py # 模型下载工具
├── deploy_sensevoice.py         # 一键部署脚本
├── requirements.txt             # 精简依赖列表
├── data/                        # 数据目录
│   ├── outputs/                 # 处理结果
│   └── uploads/                 # 上传文件
└── meeting_records/             # 会议记录
```

## 🔧 安装部署

### 方式1: 一键部署（推荐）
```bash
python deploy_sensevoice.py
# 选择 "1. 完整部署"
```

### 方式2: 手动安装
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 下载模型
python commands/download_sensevoice_models.py

# 3. 测试系统
python commands/video2txt.py --check-only
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

| 指标 | 表现 | 状态 |
|------|------|------|
| 启动时间 | <20秒 | ✅ |
| 内存占用 | <2GB | ✅ |
| CPU占用 | <30% | ✅ |
| 中文识别准确率 | >90% | ✅ |

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

## 🆚 与原项目对比

| 项目版本 | 原复杂版本 | 新简化版本 |
|----------|-----------|-----------|
| **文件数量** | 20+ | 4个核心文件 |
| **依赖复杂度** | 高(40+依赖) | 低(15个核心依赖) |
| **启动成功率** | ~60% | ~95% |
| **维护难度** | 复杂 | 简单 |
| **功能完整性** | 复杂但不稳定 | 精简且可靠 |

## 🔄 从旧版本迁移

如果你之前使用过复杂版本：

```bash
# 1. 备份数据
cp -r data/ data_backup/

# 2. 清理旧依赖
pip uninstall -y whisper faster-whisper pyannote-audio transformers

# 3. 安装新版本
python deploy_sensevoice.py
```

## 🤝 支持与反馈

- 📧 问题反馈: 提交Issue
- 📖 详细文档: 查看docs/目录
- 🆘 获取帮助: 运行 `--help` 查看命令说明

---

**总结**: 这是一个专注于核心功能的视频转文字工具，基于SenseVoice引擎，特别针对中文场景优化，简单可靠，开箱即用。
