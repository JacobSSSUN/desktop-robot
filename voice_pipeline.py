#!/usr/bin/env python3
"""
voice_pipeline.py — 语音管线
按住录音 → Whisper STT → edge-tts 播报
支持表情回调：listening / thinking / speaking
支持唤醒词检测
"""
import pyaudio
import wave
import tempfile
import subprocess
import time
import threading
import os
from faster_whisper import WhisperModel

WHISPER_MODEL = "tiny"
WHISPER_LANGUAGE = "zh"
SAMPLE_RATE = 48000
CHANNELS = 1
CHUNK = 4096
TTS_VOICE = "zh-CN-XiaoxiaoNeural"
TTS_RATE = "+0%"

CHAT_IN = "/home/jacob/robot/chat_in.txt"
CHAT_OUT = "/home/jacob/robot/chat_out.txt"


class VoicePipeline:
    def __init__(self):
        self._model = None
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._frames = []
        self._recording = False
        self._mic_device = self._find_usb_mic()
        self._emotion_callback = None
        # 唤醒词
        self._wake_listening = False
        self._wake_thread = None
        self._wake_callback = None
        self._wakewords = ["莓虾", "你好莓虾", "梅虾", "你好梅虾"]

    def set_emotion_callback(self, cb):
        """设置表情回调: cb(emotion_name, duration)"""
        self._emotion_callback = cb

    def _set_emotion(self, emo, dur=5):
        if self._emotion_callback:
            self._emotion_callback(emo, dur)

    def _find_usb_mic(self):
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                if "UACDemo" in info["name"] or "USB" in info["name"]:
                    print(f"[Voice] 使用麦克风: [{i}] {info['name']}")
                    return i
        print("[Voice] 未找到 USB 麦克风，使用默认")
        return None

    def _get_model(self):
        if self._model is None:
            print("[Voice] 加载 Whisper 模型...")
            t0 = time.time()
            self._model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
            print(f"[Voice] 模型加载完成 ({time.time()-t0:.1f}s)")
        return self._model

    # ---- 按钮录音 ----
    def start_recording(self):
        self._frames = []
        self._recording = True
        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16, channels=CHANNELS,
                rate=SAMPLE_RATE, input=True,
                input_device_index=self._mic_device,
                frames_per_buffer=CHUNK,
            )
        except Exception as e:
            print(f"[Voice] 麦克风打开失败: {e}")
            self._recording = False
            self._set_emotion("idle", 0)
            return
        self._set_emotion("listening", 60)

        def _loop():
            while self._recording:
                try:
                    data = self._stream.read(CHUNK, exception_on_overflow=False)
                    self._frames.append(data)
                except Exception:
                    pass

        self._record_thread = threading.Thread(target=_loop, daemon=True)
        self._record_thread.start()
        print("[Voice] 录音中...")

    def stop_and_transcribe(self):
        self._recording = False
        if hasattr(self, '_record_thread') and self._record_thread:
            self._record_thread.join(timeout=2)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if not self._frames:
            print("[Voice] 没有录到音频")
            self._set_emotion("idle", 0)
            return ""
        return self._transcribe_frames()

    def _transcribe_frames(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wf = wave.open(tmp.name, "wb")
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(self._frames))
        wf.close()
        self._frames = []

        self._set_emotion("thinking", 30)
        print("[Voice] 识别中...")
        t0 = time.time()
        model = self._get_model()
        segments, info = model.transcribe(
            tmp.name, language=WHISPER_LANGUAGE,
            beam_size=5, vad_filter=True,
        )
        text = "".join(seg.text for seg in segments).strip()
        print(f"[Voice] 识别完成 ({time.time()-t0:.1f}s): {text}")
        return text

    # ---- 文本清理 ----
    def _clean_for_tts(self, text):
        """清理文本，去掉 markdown 和 emoji，让 TTS 朗读自然"""
        import re
        # 去 markdown 加粗/斜体
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        # 去 markdown 链接 [text](url) → text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # 去 emoji（标准 Unicode emoji 表示法，避免匹配中文）
        text = re.sub(r'[\U0001F600-\U0001F64F]', '', text)  # emoticons
        text = re.sub(r'[\U0001F300-\U0001F5FF]', '', text)  # symbols & pictographs
        text = re.sub(r'[\U0001F680-\U0001F6FF]', '', text)  # transport & map
        text = re.sub(r'[\U0001F1E0-\U0001F1FF]', '', text)  # flags
        text = re.sub(r'[\U0001F900-\U0001F9FF]', '', text)  # supplemental
        text = re.sub(r'[\U0001FA00-\U0001FA6F]', '', text)  # chess symbols
        text = re.sub(r'[\U0001FA70-\U0001FAFF]', '', text)  # symbols ext-A
        text = re.sub(r'[\U00002702-\U000027B0]', '', text)  # dingbats
        text = re.sub(r'[\U0000FE00-\U0000FE0F]', '', text)  # variation selectors
        text = re.sub(r'[\U0000200D]', '', text)  # ZWJ
        text = re.sub(r'[\U00002600-\U000026FF]', '', text)  # misc symbols
        text = re.sub(r'[\U00002300-\U000023FF]', '', text)  # misc technical
        # 去 # 标题标记
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 去行首列表标记
        text = re.sub(r'^[\s]*[-*]\s+', '', text, flags=re.MULTILINE)
        # 去代码块
        text = re.sub(r'```[^`]*```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # 去多余空白
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    # ---- TTS 播报 ----
    def speak(self, text):
        if not text:
            return
        text = self._clean_for_tts(text)
        if not text:
            return
        print(f"[Voice] 播报: {text}")
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        subprocess.run(
            ["edge-tts", "--voice", TTS_VOICE, "--rate", TTS_RATE,
             "--text", text, "--write-media", tmp.name],
            check=True, capture_output=True,
        )
        # 音频生成完再触发动画
        self._set_emotion("speaking", 30)
        subprocess.run(["pw-play", tmp.name], check=True)
        print("[Voice] 播报完成")
        self._set_emotion("idle", 0)

    # ---- 唤醒词监听 ----
    def start_wake_listener(self, callback):
        """启动后台唤醒词监听，检测到后调用 callback()"""
        self._wake_callback = callback
        self._wake_listening = True
        self._wake_thread = threading.Thread(target=self._wake_loop, daemon=True)
        self._wake_thread.start()
        print("[Voice] 唤醒词监听启动 (你好莓虾)")

    def stop_wake_listener(self):
        self._wake_listening = False

    def _wake_loop(self):
        """持续监听，短片段识别，检查唤醒词"""
        while self._wake_listening:
            # 录 5 秒片段
            frames = []
            try:
                stream = self._pa.open(
                    format=pyaudio.paInt16, channels=CHANNELS,
                    rate=SAMPLE_RATE, input=True,
                    input_device_index=self._mic_device,
                    frames_per_buffer=CHUNK,
                )
                for _ in range(int(SAMPLE_RATE / CHUNK * 5)):
                    if not self._wake_listening:
                        break
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    frames.append(data)
                stream.stop_stream()
                stream.close()
            except Exception:
                time.sleep(1)
                continue

            if not frames or not self._wake_listening:
                continue

            # 检查音量，太安静就跳过
            import numpy as np
            raw = b"".join(frames)
            audio_data = np.frombuffer(raw, dtype=np.int16)
            rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
            if rms < 150:  # 安静阈值（降低了，更灵敏）
                continue

            # 快速识别
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            wf = wave.open(tmp.name, "wb")
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
            wf.close()

            try:
                model = self._get_model()
                segments, _ = model.transcribe(
                    tmp.name, language=WHISPER_LANGUAGE,
                    beam_size=1, vad_filter=True,
                )
                text = "".join(seg.text for seg in segments).strip()
                if text:
                    print(f"[Wake] 检测: {text}")
                    for wakeword in self._wakewords:
                        if wakeword in text:
                            print(f"[Wake] ✅ 唤醒词命中: {wakeword}")
                            self._set_emotion("happy", 3)
                            if self._wake_callback:
                                self._wake_callback()
                            time.sleep(3)  # 唤醒后冷却
                            break
            except Exception as e:
                print(f"[Wake] 识别错误: {e}")

    # ---- 语音对话 ----
    def chat(self, text):
        """发送文字到 OpenClaw，获取回复并播报"""
        if not text:
            return
        print(f"[Chat] 用户: {text}")
        self._set_emotion("thinking", 60)

        # 写入对话请求
        with open(CHAT_IN, "w", encoding="utf-8") as f:
            f.write(text)

        # 等待回复（轮询）
        reply = ""
        for _ in range(60):  # 最多等 60 秒
            time.sleep(1)
            try:
                if os.path.exists(CHAT_OUT):
                    mtime = os.path.getmtime(CHAT_OUT)
                    in_mtime = os.path.getmtime(CHAT_IN)
                    if mtime >= in_mtime:
                        with open(CHAT_OUT, "r", encoding="utf-8") as f:
                            reply = f.read().strip()
                        if reply:
                            break
            except Exception:
                pass

        if reply:
            print(f"[Chat] 回复: {reply}")
            self.speak(reply)
        else:
            print("[Chat] 超时，无回复")
            self.speak("我没有想好怎么回答")
            self._set_emotion("idle", 0)

    def cleanup(self):
        self._wake_listening = False
        self._recording = False
        self._pa.terminate()
