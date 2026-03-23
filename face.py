"""
face.py — 黑底白线极简圆脸
"""
import pygame
import math
import time
import random
from config import SCREEN_WIDTH, SCREEN_HEIGHT


class CuteCharacter:
    def __init__(self, screen):
        self.screen = screen
        self.cx = SCREEN_WIDTH * 3 // 4
        self.cy = SCREEN_HEIGHT // 2

        self.emotion = "idle"
        self.emotion_timer = 0

        self.blink_timer = 0
        self.is_blinking = False
        self.next_blink = time.time() + random.uniform(2, 4)
        self.t = 0

        self.pupil_ox = 0
        self.pupil_oy = 0
        self.pupil_target_ox = 0
        self.pupil_target_oy = 0
        self.next_look = time.time() + random.uniform(2, 4)

    def trigger_emotion(self, emotion, duration=2.0):
        self.emotion = emotion
        self.emotion_timer = duration

    def update(self, dt):
        now = time.time()
        self.t += dt

        if self.emotion_timer > 0:
            self.emotion_timer -= dt
            if self.emotion_timer <= 0:
                self.emotion = "idle"

        if not self.is_blinking and now > self.next_blink:
            self.is_blinking = True
            self.blink_timer = 0
        if self.is_blinking:
            self.blink_timer += dt
            if self.blink_timer > 0.15:
                self.is_blinking = False
                self.next_blink = now + random.uniform(2, 5)

        if now > self.next_look:
            self.pupil_target_ox = random.uniform(-5, 5)
            self.pupil_target_oy = random.uniform(-3, 3)
            self.next_look = now + random.uniform(2, 4)
        self.pupil_ox += (self.pupil_target_ox - self.pupil_ox) * 3 * dt
        self.pupil_oy += (self.pupil_target_oy - self.pupil_oy) * 3 * dt

    def draw(self):
        cx = self.cx
        cy = self.cy + int(math.sin(self.t * 1.5) * 2)

        W = (255, 255, 255)
        B = (0, 0, 0)
        BG = (25, 25, 35)  # 屏幕背景色

        r = 110

        # 脸（黑底）
        pygame.draw.circle(self.screen, B, (cx, cy), r)
        pygame.draw.circle(self.screen, (60, 60, 70), (cx, cy), r, 2)

        pox = int(self.pupil_ox)
        poy = int(self.pupil_oy)

        eye_y = cy - 18
        lx = cx - 38
        rx = cx + 38

        # === 眼睛 ===
        if self.emotion == "happy":
            for ex in [lx, rx]:
                pygame.draw.arc(self.screen, W,
                                (ex - 16, eye_y - 6, 32, 20), 3.14, 6.28, 4)

        elif self.emotion == "surprised":
            for ex in [lx, rx]:
                pygame.draw.circle(self.screen, B, (ex, eye_y), 20)
                pygame.draw.circle(self.screen, W, (ex, eye_y), 20, 3)
                pygame.draw.circle(self.screen, W, (ex + pox, eye_y + poy), 9)
                pygame.draw.circle(self.screen, B, (ex - 3, eye_y - 5), 3)

        elif self.emotion == "love":
            for ex in [lx, rx]:
                self._draw_heart(ex, eye_y, 11, W)

        elif self.emotion == "sad":
            # 委屈 — 眉毛下耷 + 圆眼
            for ex in [lx, rx]:
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18)
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18, 3)
                pygame.draw.circle(self.screen, B, (ex + pox, eye_y + 4 + poy), 9)
                pygame.draw.circle(self.screen, W, (ex - 3 + pox // 2, eye_y + 1 + poy // 2), 4)
            # 眉毛下耷
            for ex in [lx, rx]:
                pts = [(ex - 16, eye_y - 26), (ex + 16, eye_y - 32)]
                pygame.draw.line(self.screen, W, pts[0], pts[1], 3)

        elif self.emotion == "angry":
            # 生气 — 眉毛上挑交叉 + 眯眼
            for ex in [lx, rx]:
                pygame.draw.ellipse(self.screen, W, (ex - 16, eye_y - 4, 32, 14))
                pygame.draw.ellipse(self.screen, B, (ex - 14, eye_y - 2, 28, 10))
                pygame.draw.circle(self.screen, W, (ex + pox, eye_y + 2), 5)
            # 怒眉
            pygame.draw.line(self.screen, W, (lx - 16, eye_y - 28), (lx + 14, eye_y - 36), 3)
            pygame.draw.line(self.screen, W, (rx + 16, eye_y - 28), (rx - 14, eye_y - 36), 3)

        elif self.emotion == "shy":
            # 害羞 — 眼睛往下看 + 眯一点
            for ex in [lx, rx]:
                pygame.draw.circle(self.screen, W, (ex, eye_y), 16)
                pygame.draw.circle(self.screen, W, (ex, eye_y), 16, 3)
                pygame.draw.circle(self.screen, B, (ex, eye_y + 6), 8)

        elif self.emotion == "sleepy":
            for ex in [lx, rx]:
                pygame.draw.ellipse(self.screen, W, (ex - 14, eye_y - 2, 28, 8))

        elif self.emotion == "listening":
            # 倾听 — 正常大眼，微微向上看
            for ex in [lx, rx]:
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18)
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18, 3)
                pygame.draw.circle(self.screen, B, (ex + pox, eye_y - 3 + poy), 9)
                pygame.draw.circle(self.screen, W, (ex - 3 + pox // 2, eye_y - 6 + poy // 2), 4)

        elif self.emotion == "thinking":
            # 思考 — 一只眼正常一只眯
            # 左眼正常
            pygame.draw.circle(self.screen, W, (lx, eye_y), 18)
            pygame.draw.circle(self.screen, B, (lx + pox, eye_y + poy), 9)
            pygame.draw.circle(self.screen, W, (lx - 3 + pox // 2, eye_y - 4 + poy // 2), 4)
            # 右眼眯
            pygame.draw.ellipse(self.screen, W, (rx - 16, eye_y - 2, 32, 10))

        elif self.emotion == "speaking":
            # 说话 — 正常眼 + 动嘴
            for ex in [lx, rx]:
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18)
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18, 3)
                pygame.draw.circle(self.screen, B, (ex + pox, eye_y + poy), 9)
                pygame.draw.circle(self.screen, W, (ex - 3 + pox // 2, eye_y - 4 + poy // 2), 4)

        elif self.is_blinking:
            for ex in [lx, rx]:
                pygame.draw.line(self.screen, W,
                                 (ex - 12, eye_y), (ex + 12, eye_y), 3)

        else:
            # 正常大眼
            for ex in [lx, rx]:
                # 眼白（黑底上的白圆）
                pygame.draw.circle(self.screen, W, (ex, eye_y), 18)
                # 黑瞳孔
                pygame.draw.circle(self.screen, B, (ex + pox, eye_y + poy), 9)
                # 白高光
                pygame.draw.circle(self.screen, W, (ex - 3 + pox // 2, eye_y - 4 + poy // 2), 4)

        # === 嘴巴 ===
        my = cy + 40

        if self.emotion == "happy":
            # 大笑 — 宽弧线，微微露出牙齿感
            pygame.draw.arc(self.screen, W,
                            (cx - 28, my - 10, 56, 32), 3.14, 6.28, 3)
            # 内弧（深色口腔）
            pygame.draw.arc(self.screen, BG,
                            (cx - 22, my - 4, 44, 20), 3.5, 5.9, 2)

        elif self.emotion == "surprised":
            # O 嘴 — 椭圆
            pygame.draw.ellipse(self.screen, W, (cx - 10, my - 8, 20, 22), 3)

        elif self.emotion == "sleepy":
            # 无力的波浪
            pts = []
            for i in range(7):
                px = cx - 18 + i * 6
                py = my + int(3 * math.sin(i * 1.2))
                pts.append((px, py))
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, W, False, pts, 2)

        elif self.emotion == "listening":
            # 微微张开的小嘴
            pygame.draw.ellipse(self.screen, W, (cx - 8, my - 2, 16, 12), 2)

        elif self.emotion == "thinking":
            # 嘴角微微歪
            pygame.draw.arc(self.screen, W,
                            (cx - 14, my - 3, 32, 14), 3.6, 5.8, 2)

        elif self.emotion == "speaking":
            # 说话 — 嘴巴开合动画
            open_amt = abs(math.sin(self.t * 8))  # 快速开合
            mouth_h = int(6 + open_amt * 12)
            pygame.draw.ellipse(self.screen, W,
                                (cx - 12, my - mouth_h // 2, 24, mouth_h), 2)

        elif self.emotion == "love":
            # 微微上扬的微笑
            pygame.draw.arc(self.screen, W,
                            (cx - 22, my - 8, 44, 24), 3.3, 6.1, 3)

        elif self.emotion == "sad":
            # 往下弯的嘴
            pygame.draw.arc(self.screen, W,
                            (cx - 18, my + 2, 36, 18), 0.2, 2.9, 2)

        elif self.emotion == "angry":
            # 紧抿的嘴（一条线，中间微微下凹）
            pts = [(cx - 16, my), (cx - 6, my + 3), (cx + 6, my + 3), (cx + 16, my)]
            pygame.draw.lines(self.screen, W, False, pts, 2)

        elif self.emotion == "shy":
            # 憋着笑的小嘴
            pygame.draw.arc(self.screen, W,
                            (cx - 10, my - 2, 20, 12), 3.5, 5.9, 2)

        else:
            # 正常 — 自然弧度的小嘴
            pygame.draw.arc(self.screen, W,
                            (cx - 18, my - 5, 36, 18), 3.4, 6.0, 2)

    def _draw_heart(self, cx, cy, size, color):
        s = size
        for t in range(0, 360, 10):
            rad = math.radians(t)
            x = 16 * math.sin(rad) ** 3
            y = -(13 * math.cos(rad) - 5 * math.cos(2 * rad) -
                  2 * math.cos(3 * rad) - math.cos(4 * rad))
            px = cx + int(x * s / 16)
            py = cy + int(y * s / 16)
            pygame.draw.circle(self.screen, color, (px, py), 3)
