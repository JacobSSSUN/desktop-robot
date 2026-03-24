#!/usr/bin/env python3
"""
main.py — 桌面机器人 v4
左半屏：信息面板 | 右半屏：可爱小脑袋 / 摄像头画面
底部：摄像头按钮 + 退出按钮
"""
import os
import subprocess
import re
import json
import pygame
import sys
import time
import math
import signal
import threading
import numpy as np
import cv2
from config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, CAMERA_WIDTH, CAMERA_HEIGHT
from vision import Vision
from face import CuteCharacter
from status import InfoPanel
from ultrasonic import UltrasonicSensor
from pir import PIRSensor
from touch import TouchReader
from servo import ServoController
from voice_pipeline import VoicePipeline
from music_player import MusicPlayer
import spidev
from reminder import add_reminder, check_due, dismiss, dismiss_all_triggered, snooze, list_pending, cancel_last, play_ding, cleanup_old
import briefing



def main():
    print("=== 🦐 桌面机器人 v4 启动 ===")

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("Robot Friend")
    pygame.mouse.set_visible(True)

    # ── 立即显示加载画面（避免黑屏） ──
    LOADING_FONT = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 24)
    LOADING_BG = (25, 25, 35)
    LOADING_TEXT_COLOR = (160, 160, 180)
    LOADING_DOTS_COLOR = (100, 180, 255)
    def _draw_loading(msg="启动中...", dots=0):
        screen.fill(LOADING_BG)
        label = LOADING_FONT.render(msg, True, LOADING_TEXT_COLOR)
        screen.blit(label, (SCREEN_WIDTH // 2 - label.get_width() // 2, SCREEN_HEIGHT // 2 - 30))
        for i in range(3):
            r = 6 if i == dots % 3 else 4
            cx = SCREEN_WIDTH // 2 - 16 + i * 16
            cy = SCREEN_HEIGHT // 2 + 20
            color = LOADING_DOTS_COLOR if i == dots % 3 else (60, 60, 70)
            pygame.draw.circle(screen, color, (cx, cy), r)
        pygame.display.flip()
    _draw_loading()

    # 后台线程加载 Whisper（不阻塞启动）
    voice = VoicePipeline()
    whisper_ready = [False]
    def _load_whisper():
        voice._get_model()
        whisper_ready[0] = True
        print("[Main] Whisper 模型就绪")
    whisper_thread = threading.Thread(target=_load_whisper, daemon=True)
    whisper_thread.start()

    # 初始化其他组件
    vision = Vision()
    character = CuteCharacter(screen)
    info_panel = InfoPanel(screen)
    ultrasonic = UltrasonicSensor(trigger_pin=18, echo_pin=17)
    pir = PIRSensor(pin=21)
    touch = TouchReader()
    servo = ServoController(pan_channel=0, tilt_channel=1)

    # 音乐暂停/恢复辅助
    MUSIC_REQ = "/home/jacob/robot/music_request.json"
    def _music_request(req):
        try:
            with open(MUSIC_REQ, "w") as f:
                json.dump(req, f)
        except Exception:
            pass

    # 语音管线 → 角色表情联动
    def on_voice_emotion(emo, dur):
        if emo in ["idle", "happy", "surprised", "love", "sleepy", "sad", "angry", "shy",
                    "listening", "thinking", "speaking"]:
            character.trigger_emotion(emo, dur)
    voice.set_emotion_callback(on_voice_emotion)

    # 音乐播放器 widget（右上角）
    music_player = MusicPlayer(screen, x=530, y=8, w=475, h=100)

    # 开启人脸检测（跟踪需要）— 跟随摄像头开关
    vision.detect_enabled = False

    # 情绪文件
    CHAT_OUT = "/home/jacob/robot/chat_out.txt"
    last_chat_out_mtime = 0
    EMOTION_FILE = "/home/jacob/robot/emotion.txt"
    last_emotion_mtime = 0
    no_chat_timer = 0
    NO_CHAT_TIMEOUT = 3600  # 1小时没说话就困

    # 屏幕控制
    screen_on = True
    no_activity_timer = 0
    SCREEN_OFF_TIMEOUT = 60  # 1分钟没活动关屏

    # 摄像头预览
    show_camera = False

    # 超声波开关
    ultrasonic_enabled = False

    # 提醒状态
    active_reminder = None       # 当前显示的提醒 {"id", "message", "time"}
    reminder_show_time = 0       # 提醒卡片显示的时间戳
    REMINDER_AUTO_DISMISS = 60   # 60秒自动关闭

    # 提醒卡片按钮（动态生成，在绘制时计算位置）
    reminder_ok_btn = None
    reminder_snooze_btn = None

    # 早报播报状态
    briefing_running = [False]   # 是否正在播报

    # 底部按钮
    BTN_SIZE = 50
    BTN_MARGIN = 15
    BTN_Y = SCREEN_HEIGHT - BTN_SIZE - BTN_MARGIN
    # 超声波按钮（最左下角）
    ultra_btn = pygame.Rect(BTN_MARGIN, BTN_Y, BTN_SIZE, BTN_SIZE)
    # 摄像头按钮（超声波右边）
    cam_btn = pygame.Rect(BTN_MARGIN * 2 + BTN_SIZE, BTN_Y, BTN_SIZE, BTN_SIZE)
    # 退出按钮（最右下角）
    exit_btn = pygame.Rect(SCREEN_WIDTH - BTN_MARGIN - BTN_SIZE, BTN_Y, BTN_SIZE, BTN_SIZE)

    # 语音按钮（右半屏中间偏下）
    VOICE_BTN_R = 35
    voice_btn_cx = SCREEN_WIDTH * 3 // 4
    voice_btn_cy = SCREEN_HEIGHT // 2 + 150
    voice_recording = [False]  # 用列表实现跨作用域共享
    voice_processing = [False]

    # 按钮字体
    button_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 18)
    small_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 14)

    # 音量控制

    def get_volume():
        try:
            out = subprocess.check_output(
                ["amixer", "-c", "2", "sget", "PCM"], text=True)
            m = re.search(r"Playback \d+ \[(\d+)%\]", out)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 100

    def set_volume(pct):
        pct = max(0, min(100, pct))
        subprocess.run(["amixer", "-c", "2", "sset", "PCM", f"{pct}%"],
                        capture_output=True)
        print(f"[Main] 音量 → {pct}%")

    set_volume(60)
    current_vol = 60

    def draw_voice_button(surface):
        """绘制语音按钮 — 圆形 + 经典麦克风图标"""
        cx, cy = voice_btn_cx, voice_btn_cy
        r = VOICE_BTN_R

        if not whisper_ready[0]:
            # Whisper 加载中 — 灰色 + 旋转
            pygame.draw.circle(surface, (30, 30, 40), (cx, cy), r)
            pygame.draw.circle(surface, (60, 60, 75), (cx, cy), r, 2)
            angle = time.time() * 2
            for i in range(4):
                a = angle + i * 1.57
                px = cx + int(14 * pygame.math.Vector2(1, 0).rotate_rad(a).x)
                py = cy + int(14 * pygame.math.Vector2(1, 0).rotate_rad(a).y)
                pygame.draw.circle(surface, (100, 100, 120), (px, py), 3)

        elif voice_recording[0]:
            # 录音中 — 红色 + 脉冲
            pulse_t = time.time() * 3
            for ring in range(2, 0, -1):
                rr = r + int(ring * 5 * (0.5 + 0.5 * math.sin(pulse_t + ring)))
                pygame.draw.circle(surface, (180, 50 + ring * 20, 50 + ring * 20),
                                   (cx, cy), rr, 2)
            pygame.draw.circle(surface, (210, 55, 55), (cx, cy), r)
            pygame.draw.circle(surface, (240, 90, 90), (cx, cy), r, 2)
            _draw_mic3(surface, cx, cy, (255, 255, 255))

        elif voice_processing[0]:
            # 处理中 — 蓝底 + 旋转点
            pygame.draw.circle(surface, (35, 55, 95), (cx, cy), r)
            pygame.draw.circle(surface, (70, 110, 190), (cx, cy), r, 2)
            angle = time.time() * 4
            for i in range(6):
                a = angle + i * 1.047
                px = cx + int(18 * pygame.math.Vector2(1, 0).rotate_rad(a).x)
                py = cy + int(18 * pygame.math.Vector2(1, 0).rotate_rad(a).y)
                pygame.draw.circle(surface, (150, 180, 255), (px, py), 2)

        else:
            # 待机 — 深色圆
            pygame.draw.circle(surface, (40, 40, 55), (cx, cy), r)
            pygame.draw.circle(surface, (90, 90, 115), (cx, cy), r, 2)
            _draw_mic3(surface, cx, cy, (160, 160, 180))

    def _draw_mic3(surface, cx, cy, color):
        """经典麦克风：椭圆头 + 竖线 + 横线底座"""
        # 椭圆头（放大）
        head_rect = pygame.Rect(cx - 7, cy - 18, 14, 18)
        pygame.draw.ellipse(surface, color, head_rect)
        # 竖线
        pygame.draw.line(surface, color, (cx, cy), (cx, cy + 10), 2)
        # 横线底座
        pygame.draw.line(surface, color, (cx - 8, cy + 10), (cx + 8, cy + 10), 2)

    # 抚摸手势追踪
    pet_path = []  # [(time, x, y), ...]
    pet_cooldown = 0
    tap_start = None  # (time, x, y) 按下瞬间
    tap_cooldown = 0

    def screen_power(on):
        pass  # 软黑屏方案

    def cleanup(signum, frame):
        music_player.cleanup()
        vision.stop()
        ultrasonic.stop()
        pir.stop()
        touch.stop()
        servo.stop()
        try: _pot_spi.close()
        except: pass
        try: lgpio.gpio_free(_gpio_handle, 16)
        except: pass
        lgpio.gpiochip_close(_gpio_handle)
        voice.cleanup()
        pygame.quit()
        sys.exit(0)

    vision.start()
    ultrasonic.start()
    touch.start()
    servo.start()

    # 电位器音量控制 (MCP3008 AIN0, SPI CE0)
    _pot_spi = spidev.SpiDev()
    _pot_spi.open(0, 0)
    _pot_spi.max_speed_hz = 1350000
    _pot_shared_vol = [current_vol]  # 线程和主循环共享
    _pot_pause_until = [0.0]  # 暂停电位器控制的截止时间

    def _pot_monitor():
        """后台线程：读电位器 ADC → 平滑 → 设音量"""
        _pot_samples = []
        while True:
            time.sleep(0.15)
            if time.time() < _pot_pause_until[0]:
                continue
            try:
                r = _pot_spi.xfer2([1, 0x80, 0])
                raw = ((r[1] & 3) << 8) + r[2]
            except Exception:
                break
            _pot_samples.append(raw)
            if len(_pot_samples) > 5:
                _pot_samples.pop(0)
            smoothed = sum(_pot_samples) / len(_pot_samples)
            # 端点补偿：实际范围约 5~1018，映射到 0~100
            new_vol = round(max(0, min(100, (smoothed - 5) / 1013 * 100)))
            if abs(new_vol - _pot_shared_vol[0]) >= 3:
                _pot_shared_vol[0] = new_vol
                set_volume(new_vol)
                print(f"[Pot] 电位器音量 → {new_vol}%")

    threading.Thread(target=_pot_monitor, daemon=True).start()
    print("[Pot] 电位器音量监控已启动")

    # PS2 摇杆表情控制 (MCP3008 CH1=X, CH2=Y, CH3=SW)
    _JOY_DEAD_MIN = 400
    _JOY_DEAD_MAX = 624
    _joy_last_dir = [None]
    _joy_sw_prev = [1]

    def _joystick_monitor():
        """后台线程：读摇杆方向/按键 → 触发表情"""
        def _read_ch(ch):
            r = _pot_spi.xfer2([1, (8 + ch) << 4, 0])
            return ((r[1] & 3) << 8) + r[2]

        _sw_cooldown = 0.0
        while True:
            time.sleep(0.08)
            try:
                x = _read_ch(1)
                y = _read_ch(2)
            except Exception:
                break

            # 按键检测 (GPIO12, 内部上拉, 按下拉低)
            now = time.time()
            try:
                sw_val = lgpio.gpio_read(_gpio_handle, 12)
            except Exception:
                sw_val = 1
            if sw_val == 0 and _joy_sw_prev[0] == 1 and now > _sw_cooldown:
                character.trigger_emotion("surprised", 2)
                _sw_cooldown = now + 1.0
                print("[Joy] 摇杆按下 → surprised")
            _joy_sw_prev[0] = sw_val

            # 方向检测（带方向锁，同方向不重复触发）
            direction = None
            if x < _JOY_DEAD_MIN:
                direction = "left"
            elif x > _JOY_DEAD_MAX:
                direction = "right"
            elif y < _JOY_DEAD_MIN:
                direction = "up"
            elif y > _JOY_DEAD_MAX:
                direction = "down"

            if direction and direction != _joy_last_dir[0]:
                emo_map = {
                    "up": ("happy", 3),
                    "down": ("sad", 3),
                    "left": ("angry", 3),
                    "right": ("love", 3),
                }
                emo, dur = emo_map[direction]
                character.trigger_emotion(emo, dur)
                print(f"[Joy] 摇杆 {direction} → {emo}")
            _joy_last_dir[0] = direction

    threading.Thread(target=_joystick_monitor, daemon=True).start()
    print("[Joy] 摇杆表情控制已启动")

    # 物理语音按键 (GPIO16, 按下低电平) — 用 lgpio 直接读取
    import lgpio
    _gpio_handle = lgpio.gpiochip_open(4)

    # 摇杆按钮 (GPIO12, 内部上拉, 按下低电平)
    try:
        lgpio.gpio_claim_input(_gpio_handle, 12, lFlags=lgpio.SET_PULL_UP)
        print("[GPIO] GPIO12 (摇杆按钮) claim 成功")
    except Exception as e:
        print(f"[GPIO] GPIO12 claim 失败: {e}")

    def _gpio_monitor():
        """监控 GPIO16 按键状态"""
        try:
            lgpio.gpio_claim_input(_gpio_handle, 16)
            print("[GPIO] GPIO16 claim 成功")
        except Exception as e:
            print(f"[GPIO] GPIO16 claim 失败: {e}")
            return
        last_state = lgpio.gpio_read(_gpio_handle, 16)
        while True:
            time.sleep(0.02)  # 20ms 轮询
            try:
                state = lgpio.gpio_read(_gpio_handle, 16)
            except Exception:
                break
            if state != last_state:
                time.sleep(0.03)  # 消抖延时
                state = lgpio.gpio_read(_gpio_handle, 16)
                if state != last_state:
                    if state == 0:  # 按下 (低电平)
                        if not voice_recording[0] and not voice_processing[0] and whisper_ready[0]:
                            voice_recording[0] = True
                            voice.start_recording()
                            _music_request({"action": "pause"})
                            print("[Voice] 物理按键 → 开始录音")
                    else:  # 松开 (高电平)
                        if voice_recording[0]:
                            voice_recording[0] = False
                            voice_processing[0] = True
                            threading.Thread(target=_do_voice_process, daemon=True).start()
                    last_state = state

    def _do_voice_process():
        """物理按键松开后的处理线程"""
        try:
            text = voice.stop_and_transcribe()
            if text:
                print(f"[Voice] 识别: {text}")
                voice.chat(text)
            else:
                print("[Voice] 没有识别到内容")
                character.trigger_emotion("idle", 0)
        except Exception as e:
            print(f"[Voice] 错误: {e}")
            character.trigger_emotion("idle", 0)
        finally:
            voice_processing[0] = False
            _music_request({"action": "resume"})

    threading.Thread(target=_gpio_monitor, daemon=True).start()
    print("[Main] 物理语音按键就绪 (GPIO16)")

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    def play_ding_twice():
        """播放叮咚提示音 ×3（更长更醒目的提示音）"""
        import pygame as pg
        sample_rate = 22050

        def make_tone(freq, duration, volume=0.5):
            t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
            tone = np.sin(2 * np.pi * freq * t) * volume
            fade_out = np.linspace(1, 0, len(tone))
            return (tone * fade_out * 32767).astype(np.int16)

        silence_short = np.zeros(int(sample_rate * 0.08), dtype=np.int16)
        silence_long = np.zeros(int(sample_rate * 0.25), dtype=np.int16)

        # 单组叮咚
        ding1 = np.concatenate([make_tone(800, 0.12), silence_short, make_tone(1200, 0.18)])
        # 三遍
        sound_data = np.concatenate([ding1, silence_long, ding1, silence_long, ding1])
        try:
            snd = pg.mixer.Sound(buffer=sound_data)
            snd.play()
        except Exception as e:
            print(f"[Reminder] 播放音效失败: {e}")

    def draw_reminder_card(surface):
        """绘制提醒卡片（覆盖右半屏脸区域）"""
        if active_reminder is None:
            return

        # 遮罩层
        overlay = pygame.Surface((SCREEN_WIDTH // 2, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        right_x = SCREEN_WIDTH // 2
        surface.blit(overlay, (right_x, 0))

        # 卡片区域（右半屏居中）
        card_w = 420
        card_h = 280
        card_x = right_x + (SCREEN_WIDTH // 2 - card_w) // 2
        card_y = (SCREEN_HEIGHT - card_h) // 2 - 20

        # 卡片背景
        card_rect = pygame.Rect(card_x, card_y, card_w, card_h)
        pygame.draw.rect(surface, (35, 35, 50), card_rect, border_radius=16)
        pygame.draw.rect(surface, (100, 180, 255), card_rect, 2, border_radius=16)

        # 标题（纯文字，不用 emoji）
        title_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 22)
        msg_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 28)
        time_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 16)

        title = title_font.render("[ 提醒 ]", True, (100, 180, 255))
        surface.blit(title, (card_x + (card_w - title.get_width()) // 2, card_y + 20))

        # 提醒内容（大字居中）
        msg = active_reminder["message"]
        msg_surf = msg_font.render(msg, True, (255, 255, 255))
        surface.blit(msg_surf, (card_x + (card_w - msg_surf.get_width()) // 2, card_y + 70))

        # 设置时间
        set_time = time.strftime("%H:%M", time.localtime(active_reminder["time"]))
        time_text = time_font.render(f"设置于 {set_time}", True, (120, 120, 140))
        surface.blit(time_text, (card_x + (card_w - time_text.get_width()) // 2, card_y + 120))

        # 按钮（使用预计算的位置）
        btn_font = pygame.font.Font("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 18)

        if reminder_ok_btn:
            pygame.draw.rect(surface, (60, 140, 80), reminder_ok_btn, border_radius=10)
            ok_text = btn_font.render("知道了", True, (255, 255, 255))
            surface.blit(ok_text, (reminder_ok_btn.x + (reminder_ok_btn.w - ok_text.get_width()) // 2,
                                   reminder_ok_btn.y + (reminder_ok_btn.h - ok_text.get_height()) // 2))

        if reminder_snooze_btn:
            pygame.draw.rect(surface, (60, 60, 90), reminder_snooze_btn, border_radius=10)
            snooze_text = btn_font.render("再等5分钟", True, (180, 180, 200))
            surface.blit(snooze_text, (reminder_snooze_btn.x + (reminder_snooze_btn.w - snooze_text.get_width()) // 2,
                                       reminder_snooze_btn.y + (reminder_snooze_btn.h - snooze_text.get_height()) // 2))

    time.sleep(1)
    print("[Main] 运行中 — 点击底部按钮操作")

    clock = pygame.time.Clock()
    running = True
    last_face_time = time.time()

    def draw_camera_preview(surface):
        """在右半屏绘制摄像头画面"""
        frame = vision.get_frame()
        if frame is None:
            return
        # 右半屏区域
        right_x = SCREEN_WIDTH // 2
        right_w = SCREEN_WIDTH // 2
        right_h = SCREEN_HEIGHT - BTN_SIZE - BTN_MARGIN * 2

        # 缩放画面适配右半屏
        h, w = frame.shape[:2]
        scale = min(right_w / w, right_h / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (new_w, new_h))
        # 翻转图像（上下+左右 = 180°旋转）
        resized = cv2.flip(resized, -1)

        # 转换为 pygame surface
        # frame 是 RGB，pygame 需要 RGB
        surf = pygame.image.frombuffer(resized.tobytes(), (new_w, new_h), "RGB")

        # 居中放置
        x = right_x + (right_w - new_w) // 2
        y = (right_h - new_h) // 2
        surface.blit(surf, (x, y))

        # 顶部标题（不使用 emoji）
        title = button_font.render("实时画面", True, (150, 150, 150))
        surface.blit(title, (right_x + 10, 10))

    def draw_buttons(surface):
        """绘制底部按钮"""
        # 超声波开关按钮 — 画声波图形
        ultra_color = (60, 130, 60) if ultrasonic_enabled else (60, 60, 80)
        pygame.draw.rect(surface, ultra_color, ultra_btn, border_radius=10)
        pygame.draw.rect(surface, (100, 100, 120), ultra_btn, 2, border_radius=10)
        # 居中画声波图标
        ucx = ultra_btn.x + BTN_SIZE // 2
        ucy = ultra_btn.y + BTN_SIZE // 2
        col = (200, 200, 200) if ultrasonic_enabled else (120, 120, 130)
        # 小喇叭（左下）
        pygame.draw.polygon(surface, col, [
            (ucx - 8, ucy - 4), (ucx - 2, ucy - 8),
            (ucx - 2, ucy + 8), (ucx - 8, ucy + 4)
        ])
        # 声波弧线（右半圆，3条）
        import math
        for r in [8, 14, 20]:
            pts = []
            for deg in range(-50, 51, 5):
                rad = math.radians(deg)
                px = ucx + int(r * math.cos(rad))
                py = ucy - int(r * math.sin(rad))
                pts.append((px, py))
            if len(pts) >= 2:
                pygame.draw.lines(surface, col, False, pts, 2)

        # 摄像头按钮 — 画相机图形
        cam_color = (60, 130, 60) if show_camera else (60, 60, 80)
        pygame.draw.rect(surface, cam_color, cam_btn, border_radius=10)
        pygame.draw.rect(surface, (100, 100, 120), cam_btn, 2, border_radius=10)
        # 相机身
        body = pygame.Rect(cam_btn.x + 10, cam_btn.y + 16, 30, 20)
        pygame.draw.rect(surface, (200, 200, 200), body, border_radius=3)
        # 镜头
        pygame.draw.circle(surface, (200, 200, 200),
                           (cam_btn.x + 25, cam_btn.y + 26), 8)
        pygame.draw.circle(surface, cam_color,
                           (cam_btn.x + 25, cam_btn.y + 26), 5)
        # 闪光灯小方块
        pygame.draw.rect(surface, (200, 200, 200),
                         (cam_btn.x + 14, cam_btn.y + 12, 8, 5))

        # 退出按钮 — 画 X
        pygame.draw.rect(surface, (100, 40, 40), exit_btn, border_radius=10)
        pygame.draw.rect(surface, (150, 60, 60), exit_btn, 2, border_radius=10)
        cx, cy = exit_btn.x + BTN_SIZE // 2, exit_btn.y + BTN_SIZE // 2
        pygame.draw.line(surface, (220, 100, 100),
                         (cx - 10, cy - 10), (cx + 10, cy + 10), 3)
        pygame.draw.line(surface, (220, 100, 100),
                         (cx + 10, cy - 10), (cx - 10, cy + 10), 3)

        # 音量条（摄像头按钮右侧）
        vol_bar_x = cam_btn.x + BTN_SIZE + 10
        vol_bar_y = BTN_Y + 12
        vol_bar_w = 100
        vol_bar_h = 26
        # 背景
        pygame.draw.rect(surface, (30, 30, 45), (vol_bar_x, vol_bar_y, vol_bar_w, vol_bar_h), border_radius=6)
        # 填充（左→右）
        fill_w = int(vol_bar_w * current_vol / 100)
        fill_color = (80, 200, 120) if current_vol > 20 else (220, 80, 80)
        pygame.draw.rect(surface, fill_color,
                         (vol_bar_x, vol_bar_y, fill_w, vol_bar_h), border_radius=6)
        # 边框
        pygame.draw.rect(surface, (90, 90, 110), (vol_bar_x, vol_bar_y, vol_bar_w, vol_bar_h), 2, border_radius=6)
        # 百分比（条内居中）
        vol_text = small_font.render(f"{current_vol}%", True, (255, 255, 255))
        tx = vol_bar_x + (vol_bar_w - vol_text.get_width()) // 2
        ty = vol_bar_y + (vol_bar_h - vol_text.get_height()) // 2
        surface.blit(vol_text, (tx, ty))

    try:
        while running:
            dt = clock.tick(FPS) / 1000.0

            # 音乐播放器状态更新（处理语音指令、检测播放结束）
            music_player.update()

            # 同步电位器音量到显示
            current_vol = _pot_shared_vol[0]

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    # 提醒卡片按钮（最高优先级）
                    if active_reminder is not None:
                        if reminder_ok_btn and reminder_ok_btn.collidepoint(mx, my):
                            dismiss(active_reminder["id"])
                            print(f"[Reminder] 已确认: {active_reminder['message']}")
                            active_reminder = None
                            reminder_ok_btn = None
                            reminder_snooze_btn = None
                        elif reminder_snooze_btn and reminder_snooze_btn.collidepoint(mx, my):
                            snooze(active_reminder["id"], 5)
                            print(f"[Reminder] 推迟5分钟: {active_reminder['message']}")
                            active_reminder = None
                            reminder_ok_btn = None
                            reminder_snooze_btn = None
                    # 音乐播放器按钮（优先级最高）
                    if music_player.handle_click(mx, my):
                        pass
                    # 语音按钮（圆形碰撞检测）
                    elif (mx - voice_btn_cx) ** 2 + (my - voice_btn_cy) ** 2 <= (VOICE_BTN_R + 5) ** 2:
                        if not voice_recording[0] and not voice_processing[0] and whisper_ready[0]:
                            voice_recording[0] = True
                            voice.start_recording()
                            _music_request({"action": "pause"})
                            print("[Voice] 开始录音")
                    elif ultra_btn.collidepoint(mx, my):
                        ultrasonic_enabled = not ultrasonic_enabled
                        state = "开启" if ultrasonic_enabled else "关闭"
                        print(f"[Main] 超声波反应 {state}")
                    elif cam_btn.collidepoint(mx, my):
                        show_camera = not show_camera
                        vision.detect_enabled = show_camera
                        servo.tracking_enabled = show_camera
                        if show_camera:
                            servo.center()
                            print("[Main] 摄像头+跟踪 开启")
                        else:
                            print("[Main] 摄像头+跟踪 关闭")
                    elif exit_btn.collidepoint(mx, my):
                        running = False
                elif event.type == pygame.MOUSEBUTTONUP:
                    if voice_recording[0]:
                        voice_recording[0] = False
                        voice_processing[0] = True
                        # 在后台处理
                        def process_voice():
                            try:
                                text = voice.stop_and_transcribe()
                                if text:
                                    print(f"[Voice] 识别: {text}")
                                    voice.chat(text)
                                else:
                                    print("[Voice] 没有识别到内容")
                                    character.trigger_emotion("idle", 0)
                            except Exception as e:
                                print(f"[Voice] 错误: {e}")
                                character.trigger_emotion("idle", 0)
                            finally:
                                voice_processing[0] = False
                                _music_request({"action": "resume"})
                        threading.Thread(target=process_voice, daemon=True).start()

            # 触屏手势检测（通过 pygame 鼠标事件，X11 下 /dev/input 被 grab）
            tx, ty = pygame.mouse.get_pos()
            touching = pygame.mouse.get_pressed()[0]
            now = time.time()
            pet_detected = False  # 本帧是否已触发 pet

            if touching and tx > SCREEN_WIDTH // 2 and not show_camera:
                # 记录按下瞬间
                if tap_start is None:
                    tap_start = (now, tx, ty)

                pet_path.append((now, tx, ty))
                pet_path = [(t, x, y) for t, x, y in pet_path if now - t < 0.5]

                # 检测抚摸：有来回蹭的动作
                if len(pet_path) >= 6 and now > pet_cooldown:
                    # 先算总移动距离
                    total_dx = sum(abs(pet_path[i][1] - pet_path[i-1][1]) for i in range(1, len(pet_path)))
                    total_dy = sum(abs(pet_path[i][2] - pet_path[i-1][2]) for i in range(1, len(pet_path)))
                    # 移动够多才检测方向反转
                    if total_dx + total_dy > 60:
                        y_changes = 0
                        x_changes = 0
                        for i in range(2, len(pet_path)):
                            dy1 = pet_path[i][2] - pet_path[i-1][2]
                            dy2 = pet_path[i-1][2] - pet_path[i-2][2]
                            dx1 = pet_path[i][1] - pet_path[i-1][1]
                            dx2 = pet_path[i-1][1] - pet_path[i-2][1]
                            if dy1 * dy2 < 0 and abs(dy1) > 3:
                                y_changes += 1
                            if dx1 * dx2 < 0 and abs(dx1) > 3:
                                x_changes += 1
                        if y_changes >= 2 or x_changes >= 2:
                            character.trigger_emotion("love", 3)
                            pet_cooldown = now + 3
                            pet_detected = True
                            pet_path = []
                            tap_start = None
                            print("[Main] 摸摸 → love")

            elif not touching:
                # 松手时：如果没触发 pet，检查是否是点击
                if tap_start and now > tap_cooldown and not pet_detected:
                    elapsed = now - tap_start[0]
                    dist = abs(tx - tap_start[1]) + abs(ty - tap_start[2])
                    # 短按 + 没怎么移动 = 点击
                    if elapsed < 0.3 and dist < 30:
                        character.trigger_emotion("surprised", 2)
                        tap_cooldown = now + 1
                        print("[Main] 点击 → surprised")
                pet_path = []
                tap_start = None

            # 人脸跟踪 → 舵机
            faces = vision.get_faces()
            if faces:
                # 取最大的人脸
                biggest = max(faces, key=lambda f: f[2] * f[3])
                fx, fy, fw, fh = biggest
                face_cx = fx + fw / 2
                face_cy = fy + fh / 2
                # 归一化偏移 (-1 ~ 1)，摄像头画面 640x480
                offset_x = (face_cx - CAMERA_WIDTH / 2) / (CAMERA_WIDTH / 2)
                offset_y = (face_cy - CAMERA_HEIGHT / 2) / (CAMERA_HEIGHT / 2)
                servo.update_face_position(offset_x, offset_y, detected=True)
                if int(now) % 3 == 0:  # 每3秒打印一次
                    print(f"[Track] face=({fx},{fy},{fw},{fh}) offset=({offset_x:.2f},{offset_y:.2f}) servo=({servo.pan_angle:.0f},{servo.tilt_angle:.0f})")
            else:
                servo.update_face_position(0, 0, detected=False)

            # 读取情绪文件
            try:
                em = os.path.getmtime(EMOTION_FILE)
                if em != last_emotion_mtime:
                    last_emotion_mtime = em
                    with open(EMOTION_FILE, "r", encoding="utf-8") as f:
                        emo = f.read().strip()
                    if emo in ["idle", "happy", "surprised", "love", "sleepy", "sad", "angry", "shy"]:
                        if emo == "sleepy":
                            character.trigger_emotion("sleepy", 3660)
                        else:
                            character.trigger_emotion(emo, 15)
            except Exception:
                pass

            # 检测对话（仅语音对话和 web UI，不包含飞书）
            try:
                co = os.path.getmtime(CHAT_OUT)
                if co > last_chat_out_mtime:
                    last_chat_out_mtime = co
                    no_chat_timer = 0
            except Exception:
                pass

            # 没说话计时 → 困
            no_chat_timer += dt
            if no_chat_timer > NO_CHAT_TIMEOUT and character.emotion != "sleepy":
                character.trigger_emotion("sleepy", 35)

            # 超声波距离反应
            if ultrasonic_enabled and (character.emotion == "idle" or character.emotion_timer < 0.5):
                zone = ultrasonic.get_zone()
                if zone == "very_close":
                    character.trigger_emotion("love", 3)
                elif zone == "close":
                    character.trigger_emotion("happy", 2)
                elif zone == "medium":
                    character.trigger_emotion("surprised", 1.5)

            # 提醒检查
            if active_reminder is None:
                due = check_due()
                if due:
                    active_reminder = due[0]
                    reminder_show_time = time.time()
                    play_ding_twice()
                    character.trigger_emotion("surprised", 3)
                    # 计算按钮位置（固定在右半屏）
                    right_x = SCREEN_WIDTH // 2
                    card_w, card_h = 420, 280
                    card_x = right_x + (SCREEN_WIDTH // 2 - card_w) // 2
                    card_y = (SCREEN_HEIGHT - card_h) // 2 - 20
                    btn_y = card_y + 170
                    btn_h = 44
                    reminder_ok_btn = pygame.Rect(card_x + (card_w // 2 - 140) // 2, btn_y, 140, btn_h)
                    reminder_snooze_btn = pygame.Rect(card_x + card_w // 2 + (card_w // 2 - 160) // 2, btn_y, 160, btn_h)
                    print(f"[Reminder] 触发: {active_reminder['message']}")
            else:
                # 超时自动关闭
                if time.time() - reminder_show_time > REMINDER_AUTO_DISMISS:
                    dismiss(active_reminder["id"])
                    active_reminder = None
                    reminder_ok_btn = None
                    reminder_snooze_btn = None

            # PIR 人体感应
            pir_active = pir.is_detected()

            # 早报自动播报
            if (pir_active and screen_on
                    and not briefing_running[0]
                    and not voice_recording[0]
                    and not voice_processing[0]
                    and briefing.should_brief()):
                briefing_running[0] = True

                def _do_briefing():
                    try:
                        text = briefing.compose()
                        print(f"[Briefing] 播报: {text}")
                        character.trigger_emotion("happy", 8)
                        voice.speak(text)
                        briefing.mark_done()
                    except Exception as e:
                        print(f"[Briefing] 错误: {e}")
                    finally:
                        briefing_running[0] = False

                threading.Thread(target=_do_briefing, daemon=True).start()

            # 屏幕控制
            if pir_active:
                no_activity_timer = 0
                if not screen_on:
                    screen_power(True)
                    screen_on = True
            else:
                no_activity_timer += dt
                if no_activity_timer > SCREEN_OFF_TIMEOUT and screen_on:
                    screen_power(False)
                    screen_on = False

            # === 绘制 ===
            if screen_on:
                screen.fill((20, 20, 30))
                info_panel.draw()
                music_player.draw()

                if show_camera:
                    draw_camera_preview(screen)
                else:
                    character.update(dt)
                    character.draw()

                # 语音按钮（原气泡位置）
                draw_voice_button(screen)

                # 提醒卡片（覆盖在脸上）
                draw_reminder_card(screen)

                # PIR 状态指示（右上角小点）
                if pir.is_detected():
                    pygame.draw.circle(screen, (100, 255, 100), (SCREEN_WIDTH - 20, 15), 5)
                else:
                    pygame.draw.circle(screen, (60, 60, 70), (SCREEN_WIDTH - 20, 15), 5)

                # 底部按钮
                draw_buttons(screen)
            else:
                screen.fill((0, 0, 0))

            pygame.display.flip()

    except KeyboardInterrupt:
        print("\n[Main] 用户中断")
    finally:
        vision.stop()
        ultrasonic.stop()
        pir.stop()
        touch.stop()
        servo.stop()
        try: lgpio.gpio_free(_gpio_handle, 16)
        except: pass
        lgpio.gpiochip_close(_gpio_handle)
        voice.cleanup()
        pygame.quit()
        print("[Main] 再见！")


if __name__ == "__main__":
    main()
