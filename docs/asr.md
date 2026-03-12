# ASR 引擎指南

## 总览

`core/asr/voice_recognition_core.py` 对所有语音引擎提供统一入口。默认回退顺序如下：

1. `remote_api` – 云端 HTTP/HTTPS 服务
2. `qwen3_asr` – DashScope Qwen3-ASR (云端 API)
3. `parakeet` – NVIDIA NeMo GPU 模型
4. `whisperx`
5. `whisper`
6. `faster_whisper`
7. `sensevoice`
8. `dolphin`

若首选引擎不可用，会自动尝试下一个。

## 云端 Remote API

1. 在 **设置 → 语音模型** 页面的 “云端 ASR” 区域填入 `base_url`、`endpoint`、`API Key`，并点击“保存远程配置”。
2. `/api/settings/asr` 会把参数写入 `config/settings.json` 的 `asr.remote_api`。
3. `core/asr/engines/remote_api_engine.py` 会以 multipart/form-data 发送音频：

```
POST {base_url}/{endpoint}
Headers: {auth_header: token, ...}
Form fields:
  payload = {
    "language": "auto|zh|en...",
    "enable_diarization": bool,
    "metadata": {"engine": "remote_api"}
  }
  file = (<audio binary>)
```

返回应包含 `text`、`segments`、`speakers` 字段。缺失的字段会自动回退成单段结果。

## Qwen3-ASR (DashScope)

1. 在 [DashScope 控制台](https://dashscope.aliyun.com/) 申请 `DASHSCOPE_API_KEY`，或者在 `config/settings.json -> asr.qwen3_asr.dashscope_api_key` 中填写专用 key。
2. 打开 **设置 → 语音模型 → Qwen3-ASR (DashScope)**，配置模型（`qwen3-asr-flash` / `qwen3-asr-plus`）、线程数、VAD 分段阈值、临时目录及上下文提示词。
3. 点击“保存Qwen3配置”即可将参数写入 `config/settings.json -> asr.qwen3_asr`，`core/asr/engines/qwen3_asr_engine.py` 会：
   - 使用 `silero-vad` 自动切分长音频；
   - 将每个分片保存到 `tmp_dir` 后，通过 Python SDK (`dashscope.MultiModalConversation`) 并行调用 ASR；
   - 汇总文本、分片起止时间并输出平台统一格式。
4. 如果 `.env` 已设置 `DASHSCOPE_API_KEY`，可以在设置页留空 API Key，由引擎自动读取环境变量。
5. `num_threads` 建议与 DashScope 并发配额一致；`min_duration_for_vad`（默认 3min）可避免短音频被切割，`max_segment_duration` 可防止单段超 180s。`tmp_dir` 建议指向 SSD 目录（默认 `~/qwen3-asr-cache`），执行完每个任务后会自动清理。
6. `silence` 设为 `true` 时会压缩日志输出，适合批量任务。若需要额外上下文，可在 `context` 中注入 JSON 片段（如会议主题、参会人）提升识别率。

> **提示**：上下文提示词可放置会议主题、说话人背景等信息，有助于 Qwen3 增强识别准确率。线程数建议与 DashScope 并发配额保持一致。

## Parakeet (NeMo)

1. 先安装依赖：`pip install nemo_toolkit[nlp] nemo-asr`.
2. 在 “Parakeet GPU 引擎” 区域选择模型（TDT 0.6B / CTC 1.1B）并点击“下载”。UI 会调用 `nemo_asr_install_models <model>`。
3. 下载完成后会在 `data/models/parakeet/<model>.installed` 落地标记文件，便于检测。
4. 默认参数：
   - `device`: auto → 优先 CUDA
   - `segment_duration`: 18s
   - `words_per_segment`: 32
   - `diarization`: 依赖 Hugging Face Token 触发 `pyannote` + `whisperx` 标注

## 模型管理 API

`/api/models` 现在会返回 `parakeet`、`qwen3_asr` 与 `remote_api` 条目，并在前端卡片上标记“云端/本地”。对于 Qwen3-ASR 与 Remote API，删除操作等价于禁用配置（不涉及文件清理），并额外提供 `notes` 与 `api_key_configured` 字段帮助 UI 显示 “需要 DashScope API Key / 已配置” 状态。

## 测试建议

1. 运行 `pytest -k asr` 以验证远程模板和 Parakeet 分段逻辑。
2. 可使用示例视频 `/Users/jiechengyang/Downloads/0815.mp4` 进行真实处理，分别指定 `remote_api`、`qwen3_asr` 与 `parakeet` 引擎，观察 `/api/tasks/meeting/{id}` 中的 diarization 状态与下载链接。
