"""
bubble.py — 纯文字消息显示（角色下方）
"""
import pygame
import time
import os
from font_helper import get_font
from config import SCREEN_WIDTH, SCREEN_HEIGHT


class SpeechBubble:
    MSG_FILE = "/home/jacob/robot/message.txt"

    def __init__(self, screen):
        self.screen = screen
        self.current_text = ""
        self.display_text = ""
        self.char_index = 0
        self.char_timer = 0
        self.char_speed = 0.03
        self.fade_timer = 0
        self.fade_duration = 8
        self.last_modified = 0

    def update(self, dt):
        try:
            mtime = os.path.getmtime(self.MSG_FILE)
            if mtime != self.last_modified:
                self.last_modified = mtime
                with open(self.MSG_FILE, "r", encoding="utf-8") as f:
                    text = f.read().strip()
                if text and text != self.current_text:
                    self.current_text = text
                    self.display_text = ""
                    self.char_index = 0
                    self.char_timer = 0
                    self.fade_timer = 0
        except Exception:
            pass

        if self.char_index < len(self.current_text):
            self.char_timer += dt
            while self.char_timer >= self.char_speed and self.char_index < len(self.current_text):
                self.char_timer -= self.char_speed
                self.char_index += 1
            self.display_text = self.current_text[:self.char_index]
        elif self.current_text:
            self.fade_timer += dt
            if self.fade_timer > self.fade_duration:
                self.current_text = ""
                self.display_text = ""

    def draw(self):
        if not self.display_text:
            return

        remaining = self.fade_duration - self.fade_timer
        if remaining < 0:
            return
        alpha = 255
        if remaining < 2:
            alpha = int(255 * max(0, remaining / 2))

        cx = SCREEN_WIDTH * 3 // 4
        text_y = SCREEN_HEIGHT // 2 + 150

        font = get_font(18)
        max_w = 280
        lines = self._wrap_text(self.display_text, font, max_w)

        for i, line in enumerate(lines):
            ts = font.render(line, True, (255, 255, 255))
            ts.set_alpha(alpha)
            tx = cx - ts.get_width() // 2
            self.screen.blit(ts, (tx, text_y + i * 24))

        # 打字光标
        if self.char_index < len(self.current_text):
            last_line = lines[-1] if lines else ""
            cursor_x = cx + font.size(last_line)[0] // 2 + 2
            cursor_y = text_y + (len(lines) - 1) * 24
            if int(time.time() * 3) % 2:
                pygame.draw.rect(self.screen, (255, 255, 255), (cursor_x, cursor_y, 2, 18))

    def _wrap_text(self, text, font, max_width):
        lines = []
        current = ""
        for char in text:
            test = current + char
            if font.size(test)[0] > max_width:
                if current:
                    lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
        return lines if lines else [""]
