# 🚀 AI音视频处理平台 - 快速入门

## ⚡ 30秒快速体验

### 环境要求
- **Python 3.8+** 
- **8GB+ 内存**
- **5GB+ 存储空间**

### 一键安装
```bash
# 1. 克隆项目
git clone https://github.com/your-repo/ai-video2text.git
cd ai-video2text

# 2. 安装依赖
pip install -r requirements.txt

# 3. 快速测试
python setup_realtime_meeting.py
```

### 立即体验

#### 🎯 场景1: 实时会议记录
```bash
# 最简单的实时转录
python realtime_meeting.py

# 🎤 对着麦克风说话，观察实时转录效果
# 💡 按 Ctrl+C 停止，查看 meeting_records/ 目录
```

#### 🎯 场景2: 视频内容学习
```bash
# 处理学习视频，生成闪卡和思维导图
python video2txt.py -i your_video.mp4 --flashcards --verbose

# 📁 查看 outputs/ 目录获得：
#   - 完整内容总结
#   - XMind思维导图  
#   - Anki学习闪卡
#   - 关键帧截图
```

#### 🎯 场景3: 多语言翻译
```bash
# 启用中英日韩实时翻译
python realtime_meeting.py --enable-translation --languages zh,en,ja,ko

# 🌐 说中文自动翻译为英文
# 🌐 说英文自动翻译为中文
```

## 🎮 功能导航

### 批量处理功能（迭代1）
| 功能 | 命令 | 输出 |
|------|------|------|
| **基础转录** | `python video2txt.py -i file.mp4` | 内容总结 + 字幕 |
| **学习增强** | `python video2txt.py -i file.mp4 --flashcards` | +闪卡 +思维导图 |
| **音频处理** | `python video2txt.py -i audio.mp3 --flashcards` | +波形图 +频谱图 |
| **详细模式** | `python video2txt.py -i file.mp4 --verbose` | 完整处理信息 |

### 实时处理功能（迭代2）
| 功能 | 命令 | 效果 |
|------|------|------|
| **实时转录** | `python realtime_meeting.py` | <2秒延迟转录 |
| **多语言翻译** | `--enable-translation --languages zh,en` | 实时双语显示 |
| **说话人分离** | `--enable-speaker-diarization` | 识别不同发言人 |
| **会议集成** | `--enable-meeting-integration` | 自动检测会议软件 |
| **完整功能** | 组合所有参数 | 全功能会议记录 |

### 高级分析功能（迭代3）
| 功能 | 命令 | 用途 |
|------|------|------|
| **AI分析** | `python meeting_advanced.py records/xxx.jsonl` | 智能会议总结 |
| **会议检测** | `python meeting_integration.py` | 测试会议软件检测 |
| **系统测试** | `python setup_realtime_meeting.py` | 完整功能测试 |

## 🎓 学习路径

### 新手用户（10分钟入门）
```bash
# 第1步：测试基础功能
python video2txt.py -i test_video.mp4

# 第2步：体验实时转录  
python realtime_meeting.py

# 第3步：查看输出文件
ls outputs/    # 批量处理结果
ls meeting_records/  # 实时记录结果
```

### 进阶用户（30分钟掌握）
```bash
# 第1步：学习功能组合
python video2txt.py -i course.mp4 --flashcards --verbose

# 第2步：多语言翻译
python realtime_meeting.py --enable-translation --languages zh,en,ja

# 第3步：说话人分离
python realtime_meeting.py --enable-speaker-diarization

# 第4步：会议软件集成
python realtime_meeting.py --enable-meeting-integration
```

### 专业用户（1小时精通）
```bash
# 第1步：完整功能体验
python realtime_meeting.py \
  --enable-translation \
  --enable-speaker-diarization \
  --enable-meeting-integration \
  --languages zh,en,ja,ko

# 第2步：AI智能分析
python meeting_advanced.py meeting_records/latest/transcriptions.jsonl

# 第3步：批量处理工作流
find videos/ -name "*.mp4" -exec python video2txt.py -i {} --flashcards \;

# 第4步：自定义配置
cp meeting_config.yaml my_config.yaml
# 编辑配置文件
python realtime_meeting.py --config my_config.yaml
```

## 📱 使用场景快速指南

### 🎓 教育学习场景
```bash
# 在线课程处理
python video2txt.py -i course_video.mp4 --flashcards --verbose

# 获得学习材料：
# 1. content.md - 完整课程笔记
# 2. mind_map.mm - XMind思维导图
# 3. flashcards_anki.csv - Anki复习卡片
# 4. frames/ - 关键知识点截图

# 学习工作流：
# XMind打开思维导图 → 建立知识框架
# Anki导入闪卡 → 间隔重复记忆
# 参考截图 → 回顾重点内容
```

### 💼 商务会议场景
```bash
# 启动完整会议记录
python realtime_meeting.py \
  --enable-translation \
  --enable-speaker-diarization \
  --enable-meeting-integration \
  --languages zh,en

# 工作流程：
# 1. 打开腾讯会议/钉钉 → 系统自动检测
# 2. 实时转录所有发言 → 按发言人分类
# 3. 多语言实时翻译 → 跨语言沟通
# 4. 会议结束自动总结 → AI智能分析

# 会议后处理：
python meeting_advanced.py meeting_records/latest/transcriptions.jsonl
```

### 🌐 国际交流场景
```bash
# 多语言内容处理
python video2txt.py -i international_content.mp4 --flashcards

# 实时多语言会议
python realtime_meeting.py \
  --enable-translation \
  --languages zh,en,ja,ko

# 支持翻译方向：
# 中文 ↔ 英文
# 日语 → 中文  
# 韩语 → 中文
# 方言 → 普通话 → 英文
```

### 📱 内容创作场景
```bash
# 播客/视频内容分析
python video2txt.py -i podcast.mp3 --flashcards --verbose

# 直播实时记录
python realtime_meeting.py --output-dir live_streams/

# 批量内容处理
for file in content/*.{mp4,mp3,wav}; do
    python video2txt.py -i "$file" --flashcards
done
```

## 🔧 常见问题解决

### 安装问题
```bash
# Q: pip install失败？
# A: 升级pip并使用国内源
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# Q: pyaudio安装失败？
# A: 安装系统依赖
# macOS: brew install portaudio
# Ubuntu: sudo apt-get install portaudio19-dev
# Windows: 下载预编译的wheel文件

# Q: 缺少某些可选依赖？
# A: 运行自动安装脚本
python setup_realtime_meeting.py
```

### 使用问题
```bash
# Q: 转录效果不好？
# A: 1. 确保音频质量良好
#    2. 选择合适的Whisper模型
#    3. 指定正确的语言参数

# Q: 实时延迟太高？
# A: 1. 使用faster-whisper
#    2. 选择较小的模型(base)
#    3. 检查CPU和内存使用

# Q: 会议软件检测失败？
# A: 1. 确认软件在支持列表中
#    2. 检查进程名称
#    3. 尝试手动指定音频设备

# Q: 翻译质量不满意？
# A: 1. 确保原文转录准确
#    2. 使用更大的Whisper模型
#    3. 检查语言检测结果
```

### 性能优化
```bash
# 提升转录速度
python realtime_meeting.py --whisper-model base  # 使用小模型

# 提升转录质量  
python realtime_meeting.py --whisper-model medium  # 使用中等模型

# 平衡速度和质量
python realtime_meeting.py --whisper-model small  # 推荐选择

# 自定义配置
vim meeting_config.yaml  # 编辑配置文件
python realtime_meeting.py --config meeting_config.yaml
```

## 📚 进阶学习

### 完整文档体系
- 📖 [迭代1文档](docs/迭代1-Video2Text优化/) - 批量处理功能详解
- 📖 [迭代2文档](docs/迭代2-实时会议系统/) - 实时处理系统架构  
- 📖 [迭代3文档](docs/迭代3-完整系统/) - 完整平台和商业化

### 技术深入
- 🔧 [技术实现详解](docs/迭代1-Video2Text优化/技术实现详解.md)
- 🏗️ [系统架构详解](docs/迭代2-实时会议系统/系统架构详解.md)
- 💰 [商业化策略](docs/迭代3-完整系统/商业化策略详解.md)

### 社区资源
- 🌟 **GitHub**: [项目主页](https://github.com/your-repo/ai-video2text)
- 💬 **技术交流群**: 扫码加入
- 📧 **技术支持**: support@ai-video2text.com

## 🎉 立即开始

**选择你的使用场景，立即开始体验：**

```bash
# 🎓 学习用户
python video2txt.py -i your_course.mp4 --flashcards --verbose

# 💼 商务用户  
python realtime_meeting.py --enable-translation --enable-speaker-diarization

# 🌐 国际用户
python realtime_meeting.py --enable-translation --languages zh,en,ja,ko

# 🚀 完整体验
python realtime_meeting.py \
  --enable-translation \
  --enable-speaker-diarization \
  --enable-meeting-integration \
  --languages zh,en,ja,ko
```

**🎯 从工具到平台，让每一次对话都有价值！**

---

<div align="center">

**需要帮助？**

[📖 查看完整文档](README.md) | [🐛 报告问题](https://github.com/your-repo/ai-video2text/issues) | [💬 加入社区](https://github.com/your-repo/ai-video2text/discussions)

</div>