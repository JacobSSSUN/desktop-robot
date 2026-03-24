"""
status.py — 左半屏信息面板（中文化修复）
"""
import pygame
import time
import subprocess
from collections import deque
from config import SCREEN_WIDTH, SCREEN_HEIGHT
from font_helper import get_font


# 星期映射
WEEKDAY_CN = {
    "Monday": "周一", "Tuesday": "周二", "Wednesday": "周三",
    "Thursday": "周四", "Friday": "周五", "Saturday": "周六", "Sunday": "周日",
    "Mon": "周一", "Tue": "周二", "Wed": "周三",
    "Thu": "周四", "Fri": "周五", "Sat": "周六", "Sun": "周日",
}


class InfoPanel:
    PANEL_W = SCREEN_WIDTH // 2

    def __init__(self, screen):
        self.screen = screen

        self.weather_icon = ""
        self.weather_temp = "--"
        self.weather_desc = "加载中..."
        self.weather_humidity = "--"
        self.weather_wind = "--"
        self.weather_location = ""
        self.weather_type = "clear"  # clear, cloudy, rain, snow, storm, fog
        self.weather_fetch_time = 0
        self.weather_interval = 60

        # 温度平滑
        self.temp_history = deque(maxlen=30)

    def _load_weather(self):
        now = time.time()
        if now - self.weather_fetch_time < self.weather_interval:
            return
        self.weather_fetch_time = now
        try:
            # 获取天气（中文，深圳）
            result = subprocess.run(
                ["curl", "-s", "--noproxy", "*", "-H", "Accept-Language: zh-CN",
                 "wttr.in/Shenzhen?format=%c|%t|%C|%h|%w", "--max-time", "5"],
                capture_output=True, text=True, timeout=8
            )
            print(f"[Weather] curl exit={result.returncode} stdout={result.stdout[:80]!r}")
            if result.returncode == 0 and "|" in result.stdout:
                parts = result.stdout.strip().split("|")
                if len(parts) >= 5:
                    desc = parts[2].strip()
                    self.weather_desc = desc
                    # 判断天气类型
                    if "晴" in desc or "Clear" in desc:
                        self.weather_type = "clear"
                    elif "多云" in desc or "Partly" in desc:
                        self.weather_type = "partly"
                    elif "阴" in desc or "Overcast" in desc or "cloud" in desc.lower():
                        self.weather_type = "cloudy"
                    elif "雨" in desc or "Rain" in desc:
                        self.weather_type = "rain"
                    elif "雪" in desc or "Snow" in desc:
                        self.weather_type = "snow"
                    elif "雷" in desc or "Thunder" in desc:
                        self.weather_type = "storm"
                    elif "雾" in desc or "Fog" in desc:
                        self.weather_type = "fog"
                    else:
                        self.weather_type = "clear"
                    # 温度处理：去掉+号，保留-号
                    temp_raw = parts[1].strip()
                    temp_raw = temp_raw.replace("+", "").replace("°C", "").strip()
                    self.weather_temp = temp_raw + "°C"
                    self.weather_desc = parts[2].strip()
                    self.weather_humidity = parts[3].strip()
                    self.weather_wind = parts[4].strip()
                    self.weather_location = "深圳"
                    print(f"[Weather] 更新: {self.weather_temp} {self.weather_desc}")
                    return
            print(f"[Weather] 解析失败，{self.weather_interval}秒后重试")
        except Exception as e:
            print(f"[Weather] 异常: {e}，{self.weather_interval}秒后重试")

    def _get_sys_info(self):
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                raw = int(f.read().strip()) / 1000
            self.temp_history.append(raw)
            if len(self.temp_history) >= 5:
                temp = sum(self.temp_history) / len(self.temp_history)
            else:
                temp = raw
        except Exception:
            temp = 0
        try:
            with open("/proc/loadavg") as f:
                load1, load5, load15 = f.read().split()[:3]
        except Exception:
            load1 = load5 = load15 = "?"
        try:
            result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=3)
            mem = result.stdout.split("\n")[1].split()
            mem_pct = int(mem[2]) * 100 // int(mem[1])
        except Exception:
            mem_pct = 0
        try:
            result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=3)
            disk_parts = result.stdout.split("\n")[1].split()
            disk_pct = int(disk_parts[4].replace("%", ""))
        except Exception:
            disk_pct = 0
        return temp, load1, load5, load15, mem_pct, disk_pct

    def _draw_weather_icon(self, x, y, wtype):
        """画天气图标"""
        cx, cy = x + 24, y + 24  # 中心点

        if wtype == "clear":
            # 太阳
            pygame.draw.circle(self.screen, (255, 220, 80), (cx, cy), 12)
            for angle in range(0, 360, 45):
                import math
                rad = math.radians(angle)
                ex = cx + int(18 * math.cos(rad))
                ey = cy + int(18 * math.sin(rad))
                sx = cx + int(14 * math.cos(rad))
                sy = cy + int(14 * math.sin(rad))
                pygame.draw.line(self.screen, (255, 220, 80), (sx, sy), (ex, ey), 2)

        elif wtype == "partly":
            # 太阳 + 云
            pygame.draw.circle(self.screen, (255, 220, 80), (cx - 6, cy - 6), 10)
            for angle in range(0, 360, 60):
                import math
                rad = math.radians(angle)
                ex = cx - 6 + int(15 * math.cos(rad))
                ey = cy - 6 + int(15 * math.sin(rad))
                pygame.draw.line(self.screen, (255, 220, 80),
                                 (cx - 6 + int(12 * math.cos(rad)), cy - 6 + int(12 * math.sin(rad))),
                                 (ex, ey), 2)
            self._draw_cloud(cx + 4, cy + 6, (200, 210, 220))

        elif wtype == "cloudy":
            # 云
            self._draw_cloud(cx - 4, cy - 4, (160, 170, 180))
            self._draw_cloud(cx + 6, cy + 4, (130, 140, 150))

        elif wtype == "rain":
            # 云 + 雨滴
            self._draw_cloud(cx, cy - 6, (140, 150, 170))
            for dx in [-10, 0, 10]:
                pygame.draw.line(self.screen, (100, 160, 255),
                                 (cx + dx, cy + 8), (cx + dx - 3, cy + 18), 2)

        elif wtype == "snow":
            # 云 + 雪花
            self._draw_cloud(cx, cy - 6, (180, 190, 200))
            for dx in [-10, 0, 10]:
                pygame.draw.circle(self.screen, (220, 230, 255), (cx + dx, cy + 14), 3)

        elif wtype == "storm":
            # 云 + 闪电
            self._draw_cloud(cx, cy - 6, (80, 80, 100))
            pts = [(cx, cy + 6), (cx - 4, cy + 14), (cx + 2, cy + 14), (cx - 2, cy + 22)]
            pygame.draw.polygon(self.screen, (255, 230, 50), pts)

        elif wtype == "fog":
            # 雾（横线）
            for dy in range(-8, 12, 6):
                w = 30 - abs(dy) * 2
                pygame.draw.line(self.screen, (150, 160, 170),
                                 (cx - w // 2, cy + dy), (cx + w // 2, cy + dy), 3)

    def _draw_cloud(self, cx, cy, color):
        """画一朵小云"""
        pygame.draw.circle(self.screen, color, (cx - 10, cy + 4), 10)
        pygame.draw.circle(self.screen, color, (cx + 2, cy - 2), 12)
        pygame.draw.circle(self.screen, color, (cx + 12, cy + 4), 9)
        pygame.draw.rect(self.screen, color, (cx - 10, cy, 24, 10))

    def draw(self):
        self._load_weather()
        pw = self.PANEL_W
        ph = SCREEN_HEIGHT

        bg = pygame.Surface((pw, ph))
        bg.fill((15, 15, 25))
        self.screen.blit(bg, (0, 0))
        pygame.draw.line(self.screen, (40, 40, 55), (pw, 0), (pw, ph), 2)

        y = 20

        # === 时间 ===
        time_str = time.strftime("%H:%M")
        sec_str = time.strftime(":%S")
        weekday_en = time.strftime("%A")
        weekday_cn = WEEKDAY_CN.get(weekday_en, weekday_en)
        date_str = time.strftime(f"%Y年%m月%d日 {weekday_cn}")

        ts = get_font(72, bold=True).render(time_str, True, (255, 255, 255))
        self.screen.blit(ts, (30, y))
        ss = get_font(36).render(sec_str, True, (160, 170, 190))
        self.screen.blit(ss, (30 + ts.get_width() + 2, y + 18))
        y += 80

        ds = get_font(24, bold=True).render(date_str, True, (200, 210, 230))
        self.screen.blit(ds, (32, y))
        y += 40

        # 分隔线
        for dx in range(30, pw - 30, 12):
            pygame.draw.line(self.screen, (35, 35, 50), (dx, y), (dx + 6, y), 1)
        y += 20

        # === 天气 ===
        wt = get_font(16, bold=True).render("WEATHER", True, (120, 140, 170))
        self.screen.blit(wt, (32, y))
        y += 24

        # 地点
        if self.weather_location:
            loc_s = get_font(18, bold=True).render(self.weather_location, True, (160, 180, 210))
            self.screen.blit(loc_s, (32, y))
            y += 24

        self._draw_weather_icon(30, y, self.weather_type)
        temp_s = get_font(48, bold=True).render(self.weather_temp, True, (255, 210, 100))
        self.screen.blit(temp_s, (90, y - 5))
        y += 55

        desc_s = get_font(22, bold=True).render(self.weather_desc, True, (220, 230, 245))
        self.screen.blit(desc_s, (32, y))
        y += 30

        detail = f"湿度 {self.weather_humidity}    风 {self.weather_wind}"
        detail_s = get_font(22).render(detail, True, (180, 195, 215))
        self.screen.blit(detail_s, (32, y))
        y += 50

        for dx in range(30, pw - 30, 12):
            pygame.draw.line(self.screen, (35, 35, 50), (dx, y), (dx + 6, y), 1)
        y += 20

        # === 系统 ===
        st = get_font(16, bold=True).render("SYSTEM", True, (120, 140, 170))
        self.screen.blit(st, (32, y))
        y += 28

        temp, load1, load5, load15, mem_pct, disk_pct = self._get_sys_info()

        if temp > 70:
            tc = (255, 80, 80)
        elif temp > 55:
            tc = (255, 200, 80)
        else:
            tc = (100, 220, 150)

        items = [
            ("CPU 温度", f"{temp:.0f}°", tc),
            ("系统负载", f"{load1} / {load5} / {load15}", (180, 200, 220)),
            ("内存使用", f"{mem_pct}%", (180, 200, 220)),
            ("磁盘使用", f"{disk_pct}%", (180, 200, 220)),
        ]

        bar_w = pw - 64
        for label, value, color in items:
            ls = get_font(20, bold=True).render(label, True, (200, 210, 230))
            self.screen.blit(ls, (32, y))
            vs = get_font(20, bold=True).render(value, True, color)
            self.screen.blit(vs, (200, y))
            y += 30
