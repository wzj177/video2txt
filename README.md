# 🎬 AI音视频学习内容生成器

## 📋 项目简介

这是一个基于AI的音视频内容分析和转换工具，能够将视频和音频转换为多种格式的学习内容，包括内容卡片、思维导图、学习闪卡等。

**🆕 重大升级**：现已支持音频文件直接处理、智能闪卡生成、XMind导出等全新功能！

## 🌟 核心特性

### 📁 文件支持
- **视频格式**：MP4、AVI、MOV、MKV等主流格式
- **音频格式**：MP3、M4A、WAV、AAC、FLAC、OGG、WMA 🆕
- **URL支持**：Bilibili等在线视频链接

### 🧠 智能处理
- **语音识别**：基于Whisper模型，支持多语言高精度转录
- **AI纠错**：多轮智能纠错，大幅提升转录准确度
- **动态取帧**：根据视频时长智能调整关键帧提取间隔 🆕
- **音频可视化**：为音频文件生成专业波形图和频谱图 🆕

## 🎯 输出内容

### 📝 核心内容
- **内容卡片**：结构化知识整理，章节式组织，智能配图
- **思维导图**：多层级结构，包含时间戳，逻辑清晰

### 🆕 学习增强
- **学习闪卡**：15-25张高质量学习卡片
  - 概念卡、应用卡、对比卡、流程卡、案例卡
  - 智能难度递进，记忆友好设计
- **Anki格式**：直接导入Anki进行间隔重复学习
- **XMind格式**：思维导图可直接在XMind中编辑

### 📊 深度分析
- **关键时刻标记**：精准识别重要片段
- **可信度分析**：多维度内容质量评估
- **结构分析**：叙事框架和组织方式解析
- **价值评分**：内容实用性量化评估

## 🚀 快速开始

### 环境配置
```bash
# 克隆项目
git clone <your-repo-url>
cd ai-video2text

# 安装依赖
pip install -r requirements.txt

# 设置API密钥（必需）
export DASHSCOPE_API_KEY="your_api_key_here"
export DASHSCOPE_API_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### 基础使用

#### 处理视频文件
```bash
# 基础处理
python video2txt.py -i video.mp4 --verbose

# 完整功能（推荐）
python video2txt.py -i video.mp4 --flashcards --key_moments --value_rating --verbose
```

#### 处理音频文件 🆕
```bash
# 直接处理音频
python video2txt.py -i audio.mp3 --flashcards --verbose
python video2txt.py -i podcast.m4a --verbose
```

## 📋 完整参数

### 基础参数
- `-i, --input`：输入文件路径（视频或音频）
- `--verbose`：详细日志输出（推荐）
- `--format {markdown,markmap,both}`：输出格式（默认：both）

### 🆕 新增功能
- `--flashcards`：生成学习闪卡和Anki格式

### 扩展分析
- `--key_moments`：关键时刻标记
- `--credibility`：可信度分析
- `--structure`：内容结构分析
- `--value_rating`：内容价值评分

### 技术参数
- `--whisper_model {tiny,base,small,medium,large}`：语音识别模型
- `--gpt_model`：GPT模型选择
- `--ai_correction`：启用AI智能纠错
- `--language`：音频语言（默认：zh）

## 📁 输出文件结构

处理完成后，在 `outputs/{MD5}/` 目录下生成：

### 核心内容
- `内容卡片.md` - 结构化学习内容
- `思维导图.md` - Markdown格式思维导图
- `思维导图.mm` - XMind兼容格式 🆕

### 学习工具 🆕
- `学习闪卡.md` - 智能生成的学习卡片
- `学习闪卡-Anki格式.txt` - Anki导入文件

### 分析报告（可选）
- `关键时刻标记.mp` - 重要片段提取
- `可信度分析.md` - 内容质量评估
- `内容结构分析.md` - 叙事结构解析
- `内容价值评分.md` - 价值量化分析

### 可视化资源
- **视频**：时间戳命名的关键帧（如 `01_23.jpg`）
- **音频**：`waveform.jpg`（波形图）+ `spectrogram.jpg`（频谱图）🆕

## 🎓 使用场景

### 在线学习
```bash
# 将教学视频转为完整学习资料
python video2txt.py -i lecture.mp4 --flashcards --structure --verbose
```

### 播客整理 🆕
```bash
# 处理音频播客
python video2txt.py -i podcast.mp3 --flashcards --credibility --verbose
```

### 会议记录
```bash
# 会议音频分析
python video2txt.py -i meeting.m4a --key_moments --structure --verbose
```

### 知识管理
```bash
# 全功能知识处理
python video2txt.py -i knowledge.mp4 \
  --flashcards --key_moments --structure --value_rating --credibility --verbose
```

## 🔧 高级功能

### 智能取帧算法 🆕
系统根据内容时长动态调整：
- 短内容（<5分钟）：15秒间隔
- 中等内容（5-30分钟）：30秒间隔  
- 长内容（30分钟-1小时）：45秒间隔
- 超长内容（>1小时）：60秒间隔

### 音频可视化 🆕
为纯音频文件生成：
- **波形图**：展示音频幅度变化
- **频谱图**：显示频率分布特征

### 学习闪卡系统 🆕
5种智能卡片类型：
- **概念卡**：基础定义和概念
- **应用卡**：方法技巧应用
- **对比卡**：相似概念区别
- **流程卡**：步骤流程记忆
- **案例卡**：具体案例理解

## 📱 第三方软件集成

### XMind导入
1. 打开XMind → 导入 → FreeMind文件
2. 选择生成的 `.mm` 文件
3. 完整导入所有层级和时间戳

### Anki学习
1. 创建或选择牌组
2. 导入 `学习闪卡-Anki格式.txt`
3. 确认字段映射后开始学习

## 🎉 版本亮点

### v2.0 重大升级 🆕
- ✅ **音频文件支持**：7种音频格式直接处理
- ✅ **智能取帧优化**：动态间隔算法，与时长真正挂钩
- ✅ **学习闪卡系统**：15-25张高质量记忆卡片
- ✅ **XMind格式导出**：思维导图可在专业软件编辑
- ✅ **Anki学习集成**：间隔重复学习系统
- ✅ **音频可视化**：专业波形图和频谱图

### 性能提升
- 取帧效率提升20-40%
- 内容质量显著改善
- 应用场景从视频扩展到音频
- 学习工具链完整闭环

## 🔗 相关资源

- [完整使用指南](USAGE_GUIDE.md)
- [升级详细说明](UPGRADE_SUMMARY.md)
- [优化方案报告](OPTIMIZATION_REPORT.md)

## 📄 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

---

**🎓 从视频转文本工具升级为完整的音视频学习内容生成系统！**