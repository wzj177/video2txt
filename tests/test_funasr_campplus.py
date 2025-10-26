import os
import re
from funasr import AutoModel
from modelscope.pipelines import pipeline
from modelscope.utils.constant import Tasks
import soundfile

audio_file = '/Users/jiechengyang/Downloads/apple.wav'

try:
    data, sample_rate = soundfile.read(audio_file)
    if sample_rate != 16000:
        print(f"警告：音频采样率为 {sample_rate}Hz。为了获得最佳效果，建议使用16kHz采样率的音频。")
except Exception as e:
    print(f"错误：无法读取音频文件 {audio_file}。请确保文件存在且格式正确。错误信息: {e}")
    exit()

# === 说话人分离模型 ===
print("初始化说话人分离模型 (cam++)...")
diarization_pipeline = pipeline(
    task=Tasks.speaker_diarization,
    model='iic/speech_campplus_speaker-diarization_common',
    model_revision='v1.0.0'
)

# === 语音识别模型 ===
print("初始化语音识别模型 (paraformer-zh)...")
asr_model = AutoModel(model="iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                      vad_model="fsmn-vad",
                      punc_model="ct-punc-c")

# --- 2. 执行模型 Pipeline ---

print(f"开始处理音频文件: {audio_file}")
print("开始执行说话人分离...")

# 如果您能确定说话人数量，增加此参数可以提升准确率
num_speakers = 2
diarization_result = diarization_pipeline(audio_file, oracle_num=num_speakers)
diarization_output = diarization_result['text']
print(f"说话人分离完成。")
print(f"--- 说话人分离模型原始输出 ---\n{diarization_output}\n---------------------------------")

print("开始执行语音识别...")
# 利用模型内置的VAD进行智能分句，直接获取句子列表
res = asr_model.generate(input=audio_file, sentence_timestamp=True)
print("语音识别完成。")


# --- 3. 合并与处理 ---

def parse_diarization_result(diarization_segments):
    """解析说话人分离模型返回的 [[start, end, id]] 格式列表。"""
    speaker_segments = []
    if not isinstance(diarization_segments, list): return []
    for segment in diarization_segments:
        if isinstance(segment, list) and len(segment) == 3:
            try:
                start_sec, end_sec = float(segment[0]), float(segment[1])
                speaker_id = f"spk_{segment[2]}"
                speaker_segments.append({'speaker': speaker_id, 'start': start_sec, 'end': end_sec})
            except (ValueError, TypeError) as e:
                print(f"警告：跳过格式错误的分离片段: {segment}。错误: {e}")
    return speaker_segments


def merge_results(asr_sentences, speaker_segments):
    """将ASR结果和说话人分离结果合并"""
    merged_sentences = []
    if not speaker_segments:
        # 如果说话人分离失败，则所有句子都标记为未知
        for sentence in asr_sentences:
            sentence['speaker'] = "spk_unknown"
            merged_sentences.append(sentence)
        return merged_sentences

    for sentence in asr_sentences:
        sentence_start_sec, sentence_end_sec = sentence['start'] / 1000.0, sentence['end'] / 1000.0
        found_speaker, best_overlap = "spk_unknown", 0

        # 寻找与当前句子时间重叠最长的说话人片段
        for seg in speaker_segments:
            overlap_start = max(sentence_start_sec, seg['start'])
            overlap_end = min(sentence_end_sec, seg['end'])
            overlap_duration = max(0, overlap_end - overlap_start)

            if overlap_duration > best_overlap:
                best_overlap = overlap_duration
                found_speaker = seg['speaker']

        sentence['speaker'] = found_speaker
        merged_sentences.append(sentence)
    return merged_sentences


def format_time(milliseconds):
    """将毫秒转换为SRT的时间格式 (HH:MM:SS,ms)"""
    seconds = milliseconds / 1000.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(sentences):
    """将合并后的结果转换为带说话人ID的SRT格式"""
    srt_content = ""
    for i, sentence in enumerate(sentences):
        if 'start' not in sentence or 'end' not in sentence: continue
        start_time = format_time(sentence['start'])
        end_time = format_time(sentence['end'])
        speaker_id = sentence.get('speaker', 'spk_unknown')
        text = sentence.get('text', '')
        srt_content += f"{i + 1}\n{start_time} --> {end_time}\n[{speaker_id}] {text}\n\n"
    return srt_content


# --- 4. 生成最终SRT字幕 ---
speaker_info = parse_diarization_result(diarization_output)

sentence_list = []
if res and 'sentence_info' in res[0]:
    sentence_list = res[0]['sentence_info']
else:
    print("错误或警告：未能从ASR结果中获取 'sentence_info'。")

final_sentences = merge_results(sentence_list, speaker_info)
srt_output = to_srt(final_sentences)

print("\n--- 生成的SRT字幕内容 ---")
if srt_output:
    print(srt_output)
    output_srt_file = 'output_with_speakers.srt'
    with open(output_srt_file, 'w', encoding='utf-8') as f:
        f.write(srt_output)
    print(f"带说话人标识的SRT字幕文件已保存到: {output_srt_file}")
else:
    print("未能生成SRT内容。")
