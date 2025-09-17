#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SenseVoice离线模式测试脚本
测试修复后的SenseVoice引擎是否能正确使用本地缓存模型
"""

import sys
import logging
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_local_model():
    """检查本地ModelScope缓存"""
    modelscope_cache = (
        Path.home()
        / ".cache"
        / "modelscope"
        / "hub"
        / "models"
        / "iic"
        / "SenseVoiceSmall"
    )

    print(f"🔍 检查路径: {modelscope_cache}")

    if modelscope_cache.exists():
        print("✅ 发现ModelScope缓存目录")

        # 列出文件
        files = list(modelscope_cache.glob("*"))
        print(f"📁 缓存文件数量: {len(files)}")

        if files:
            print("📋 文件列表:")
            for i, file in enumerate(files[:10]):  # 显示前10个文件
                print(f"  {i+1}. {file.name}")
            if len(files) > 10:
                print(f"  ... 还有 {len(files)-10} 个文件")
            return True
        else:
            print("⚠️ 缓存目录存在但为空")
            return False
    else:
        print("❌ 未找到ModelScope缓存目录")
        print(f"💡 请确保模型已下载到: {modelscope_cache}")
        return False


def test_sensevoice_engine():
    """测试SenseVoice引擎初始化"""
    try:
        print("\n🧪 测试SenseVoice引擎初始化...")

        from core.asr.engines.sensevoice_engine import SenseVoiceEngine

        # 创建引擎实例
        engine = SenseVoiceEngine()

        # 检查本地模型
        has_local, path = engine._check_local_model()
        print(f"📋 本地模型检查: {'✅ 找到' if has_local else '❌ 未找到'}")
        if has_local:
            print(f"📁 模型路径: {path}")

        # 尝试初始化
        print("\n🔧 尝试初始化引擎...")
        success = engine.initialize()

        if success:
            print("✅ SenseVoice引擎初始化成功！")
            print(f"🔒 离线模式: {'是' if engine.offline_mode else '否'}")

            # 获取引擎信息
            info = engine.get_engine_info()
            print(f"📊 引擎信息:")
            print(f"  - 模型: {info['model']}")
            print(f"  - 设备: {info['device']}")
            print(f"  - 已加载: {info['loaded']}")
            print(f"  - VAD启用: {info['vad_enabled']}")

            if info.get("model_path"):
                print(f"  - 模型路径: {info['model_path']}")

            return True
        else:
            print("❌ SenseVoice引擎初始化失败")
            return False

    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("💡 请确保已安装FunASR: pip install funasr modelscope")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False


def main():
    """主函数"""
    print("🎤 SenseVoice离线模式测试")
    print("=" * 50)

    # 1. 检查本地模型
    has_local = check_local_model()

    if not has_local:
        print("\n❌ 没有本地模型，无法进行离线测试")
        print("💡 请先下载SenseVoice模型:")
        print(
            "   python -c \"from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall')\""
        )
        return False

    # 2. 测试引擎
    success = test_sensevoice_engine()

    # 3. 总结
    print("\n" + "=" * 50)
    if success:
        print("🎉 测试通过！SenseVoice可以正常使用本地模型")
        print("💡 现在可以在没有网络连接的情况下使用SenseVoice")
    else:
        print("💔 测试失败！需要进一步调试")
        print("💡 请检查:")
        print("   1. FunASR是否正确安装")
        print("   2. 本地模型文件是否完整")
        print("   3. Python依赖是否满足")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
