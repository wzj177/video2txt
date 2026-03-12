# API 文档

本文档覆盖主要接口与参数。更多字段以实际接口响应为准。

## 基础信息
- Base URL: `http://127.0.0.1:19080`
- Content-Type: `application/json`（文件上传为 `multipart/form-data`）
- 鉴权：当前版本默认不启用鉴权

## 通用响应
```json
{
  "success": true,
  "message": "操作成功",
  "data": {},
  "error": null
}
```

## 视频/音频任务（/api/tasks/video）

### 1) 创建任务（上传文件）
**POST** `/api/tasks/video`

**Content-Type**: `multipart/form-data`

**表单字段**
| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | file | 是（二选一） | 上传文件 |
| url | string | 是（二选一） | 文件 URL（与 file 互斥） |
| name | string | 否 | 任务名称 |
| language | string | 否 | 语言，默认 `zh` |
| model | string | 否 | ASR 引擎，默认 `whisper`，可用 `auto` |
| model_size | string | 否 | 模型大小，默认 `small` |
| output_types | string | 否 | 输出类型，逗号分隔，默认 `transcript,summary` |
| ai_output_types | string | 否 | AI 输出类型，逗号分隔 |
| force_sync | bool | 否 | 是否同步执行 |
| ai_correction | bool | 否 | 是否纠错 |
| content_role | string | 否 | 内容角色，默认 `general` |
| ai_enhancement | bool | 否 | 内容扩写/润色开关 |

**示例**
```bash
curl -X POST "http://127.0.0.1:19080/api/tasks/video" \
  -F "file=@video.mp4" \
  -F "language=auto" \
  -F "model=auto" \
  -F "output_types=transcript,summary"
```

### 2) 任务列表
**GET** `/api/tasks/video?status=processing`

参数：
- `status`：可选，`processing/finished/error/all`

### 3) 任务详情
**GET** `/api/tasks/video/{task_id}`

### 4) 任务状态
**GET** `/api/tasks/video/{task_id}/status`

### 5) 任务进度流（SSE）
**GET** `/api/tasks/video/{task_id}/stream`

### 6) 输出文件列表
**GET** `/api/tasks/video/{task_id}/outputs`

### 7) 下载输出文件
**GET** `/api/tasks/video/{task_id}/files/{file_name}`

### 8) 获取关键帧
**GET** `/api/tasks/video/{task_id}/images/{image_path}`

### 9) 取消/删除
- **POST** `/api/tasks/video/{task_id}/cancel`
- **DELETE** `/api/tasks/video/{task_id}`

---

## 会议任务（/api/tasks/meeting）

### 1) 上传会议录音
**POST** `/api/tasks/meeting/upload`

**Content-Type**: `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| audio_file | file | 是 | 会议录音文件 |
| title | string | 是 | 会议标题 |
| engine | string | 否 | ASR 引擎，默认 `sensevoice` |
| model_name | string | 否 | 模型名称（云端/特定引擎用） |
| language | string | 否 | 语言，默认 `auto` |
| enable_speaker_diarization | bool | 否 | 是否启用说话人分离（仅本地有效） |

**示例**
```bash
curl -X POST "http://127.0.0.1:19080/api/tasks/meeting/upload" \
  -F "audio_file=@meeting.mp3" \
  -F "title=周会" \
  -F "engine=qwen3_asr" \
  -F "model_name=qwen3-asr-flash-filetrans"
```

### 2) 创建实时会议任务
**POST** `/api/tasks/meeting/create`

**JSON Body**
```json
{
  "title": "周会",
  "audioSource": "system",
  "engine": "sensevoice",
  "model_name": null,
  "language": "auto",
  "enableSpeakerDiarization": true
}
```

### 3) 会议列表
**GET** `/api/tasks/meeting/list`

### 4) 会议详情
**GET** `/api/tasks/meeting/{task_id}`

### 5) 会议流（SSE）
**GET** `/api/tasks/meeting/{task_id}/stream`

### 6) 控制录制
- **POST** `/api/tasks/meeting/{task_id}/start-recording`
- **POST** `/api/tasks/meeting/{task_id}/pause`
- **POST** `/api/tasks/meeting/{task_id}/resume`
- **POST** `/api/tasks/meeting/{task_id}/stop`

### 7) 说话人日志
- **GET** `/api/tasks/meeting/{task_id}/speaker-log`
- **POST** `/api/tasks/meeting/{task_id}/speaker-log`（生成）

### 8) 下载
- **GET** `/api/tasks/meeting/{task_id}/download`
- **GET** `/api/tasks/meeting/{task_id}/download-audio`

### 9) 删除
- **DELETE** `/api/tasks/meeting/{task_id}`

---

## 模型管理（/api/models）
- **GET** `/api/models`
- **GET** `/api/models/{model_type}`
- **GET** `/api/models/{model_type}/{model_name}`
- **POST** `/api/models/{model_type}/{model_name}/download`
- **DELETE** `/api/models/{model_type}/{model_name}`
- **GET** `/api/models/download/{task_id}/stream`

---

## 设置（/api/settings）

### ASR 配置
- **GET** `/api/settings/asr`
- **POST** `/api/settings/asr`

### WhisperX 配置
- **POST** `/api/settings/whisperx`
- **POST** `/api/settings/whisperx/test`

### OpenAI / Ollama
- **GET** `/api/settings/openai`
- **POST** `/api/settings/openai`
- **POST** `/api/settings/openai/test`
- **GET** `/api/settings/ollama`
- **POST** `/api/settings/ollama/detect`

### 汇总
- **GET** `/api/settings/all`

---

## 系统状态（/api/system）
- **GET** `/api/system/info`
- **GET** `/api/system/health`
- **GET** `/api/system/version`

---

## 备注
- Qwen3-ASR FileTrans 必须使用 OSS 公网 URL 并安装 `oss2`。
- 说话人日志为手动触发生成，默认仅保留转写结果。
