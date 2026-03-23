#!/usr/bin/env python3
"""
voice_test.py — 语音管线测试
录音 → Whisper STT → edge-tts 播报
"""
import pyaudio
import wave
import tempfile
import subprocess
import time
import sys
from faster_whisper import WhisperModel

# === 配置 ===
WHISPER_MODEL = "tiny"       # tiny/base/small
WHISPER_LANGUAGE = "zh"      # 中文
RECORD_SECONDS = 5
SAMPLE_RATE = 48000  # USB 声卡只支持 48000
CHANNELS = 1
CHUNK = 4096
DEVICE_INDEX = None  # None = 默认设备，或指定 USB 声卡索引

TTS_VOICE = "zh-CN-XiaoxiaoNeural"  # 中文女声
TTS_RATE = "+0%"  # 语速


def find_usb_mic():
    """查找 USB 麦克风设备索引"""
    pa = pyaudio.PyAudio()
    target = None
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            print(f"  [{i}] {info['name']} (输入通道: {info['maxInputChannels']})")
            if "UACDemo" in info["name"] or "USB" in info["name"]:
                target = i
    pa.terminate()
    return target


def record_audio(duration=5, device=None):
    """录音"""
    print(f"\n🎤 录音 {duration} 秒... 请说话！")
    pa = pyaudio.PyAudio()

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        input_device_index=device,
        frames_per_buffer=CHUNK,
    )

    frames = []
    for _ in range(0, int(SAMPLE_RATE / CHUNK * duration)):
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    pa.terminate()

    # 保存为临时 wav 文件
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    wf = wave.open(tmp.name, "wb")
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(2)  # 16bit
    wf.setframerate(SAMPLE_RATE)
    wf.writeframes(b"".join(frames))
    wf.close()
    print(f"✅ 录音完成: {tmp.name}")
    return tmp.name


_whisper_model = None

def transcribe(audio_path):
    """用 faster-whisper 识别"""
    global _whisper_model
    print("🧠 正在识别...")
    t0 = time.time()
    if _whisper_model is None:
        print("  (首次加载模型...)")
        _whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = _whisper_model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        beam_size=5,
        vad_filter=True,
    )
    text = "".join(seg.text for seg in segments).strip()
    elapsed = time.time() - t0
    print(f"✅ 识别完成 ({elapsed:.1f}s): {text}")
    return text


def speak(text):
    """用 edge-tts 合成并通过 pw-play 播放"""
    if not text:
        print("⚠️ 没有文字，跳过播报")
        return
    print(f"🔊 播报: {text}")
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    subprocess.run(
        ["edge-tts", "--voice", TTS_VOICE, "--rate", TTS_RATE,
         "--text", text, "--write-media", tmp.name],
        check=True, capture_output=True,
    )
    subprocess.run(["pw-play", tmp.name], check=True)
    print("✅ 播报完成")


def main():
    print("=== 🦐 语音管线测试 ===\n")

    # 1. 查找麦克风
    print("📱 查找音频输入设备...")
    mic = find_usb_mic()
    if mic is None:
        print("❌ 没找到 USB 麦克风，使用默认设备")
        mic = DEVICE_INDEX
    else:
        print(f"✅ 使用设备 [{mic}]")

    # 2. 录音
    audio_file = record_audio(RECORD_SECONDS, mic)

    # 3. STT
    text = transcribe(audio_file)

    # 4. TTS 播报
    if text:
        speak(f"你刚才说的是：{text}")
    else:
        speak("我没有听清楚，请再说一遍")


if __name__ == "__main__":
    main()
