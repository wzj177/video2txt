import onnx
import onnxruntime as ort
import numpy as np
import soundfile as sf

def save_result(est_source):
    # 假设输出是 [batch, T, spk]，取第一个说话人
    signal = est_source[0, :, 0]  # shape: (T,)
    signal = signal / (np.abs(signal).max() + 1e-6) * 0.5
    sf.write('output_spk0.wav', signal, 16000)

# 加载 ONNX 模型
onnx_model_path = 'models/simple_model.onnx'
onnx_model = onnx.load(onnx_model_path)
onnx.checker.check_model(onnx_model)
ort_session = ort.InferenceSession(onnx_model_path)

# 读取音频
input_data, sr = sf.read('/Users/jiechengyang/Downloads/test-audio.mp3')

# 转为单声道（如果 stereo）
if input_data.ndim > 1:
    input_data = np.mean(input_data, axis=1)  # 转 mono

# 重采样到 16kHz（如果需要）
# 注意：soundfile 不能重采样，需用 librosa 或 resampy
# 为简化，假设你已确保是 16kHz

# 添加 batch 维度 -> shape: (1, T)
input_data = input_data.astype(np.float32)[np.newaxis, :]  # shape: (1, T)

# 检查输入维度
print("Input shape to model:", input_data.shape)  # 应该是 (1, T)

# 推理
input_name = ort_session.get_inputs()[0].name
outputs = ort_session.run(None, {input_name: input_data})
output_data = outputs[0]
print("Output shape:", output_data.shape)

# 保存结果
save_result(output_data)