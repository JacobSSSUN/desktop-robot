"""
music_player.py — 屏幕右上角音乐播放器 widget
与语音控制共用 music_request.json 接收指令，统一由本模块管理播放。
"""
import pygame
import json
import subprocess
import os
import time
import random
import signal as sig

ROBOT_DIR = "/home/jacob/robot"
NCM_API = os.path.join(ROBOT_DIR, "ncm_api.js")
LIKED_CACHE = os.path.join(ROBOT_DIR, "ncm_liked.json")
STATUS_FILE = os.path.join(ROBOT_DIR, "music_status.json")
REQUEST_FILE = os.path.join(ROBOT_DIR, "music_request.json")
SHUFFLE_FILE = os.path.join(ROBOT_DIR, "music_shuffle.json")
PLAYER_LOG = os.path.join(ROBOT_DIR, "player.log")


def _plog(msg):
    """写入 player.log 供远程调试"""
    print(msg)
    try:
        with open(PLAYER_LOG, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

BTN_R = 18  # 按钮圆半径


class MusicPlayer:
    def __init__(self, screen, x, y, w, h):
        self.screen = screen
        self.x = x
        self.y = y
        self.w = w
        self.h = h

        self.playlist_name = ""
        self.songs = []
        self.current_index = -1
        self.current_song = None
        self.playing = False
        self.paused_by_voice = False  # 语音输入时暂停标记
        self.shuffle_mode = True

        self._ffplay = None
        self._last_status_mtime = 0
        self._play_start_time = 0    # 当前播放开始的时刻
        self._paused_elapsed = 0     # 暂停时已播放的秒数
        self._paused_song_id = None  # 暂停时的歌曲 ID

        self.font_song = pygame.font.Font(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 15)
        self.font_pl = pygame.font.Font(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 12)
        self.font_btn = pygame.font.Font(
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 16)

        self._load_shuffle()
        self._load_playlist()
        self._kill_old_ffplay()

    # ── 文件读写 ──

    def _load_playlist(self):
        try:
            with open(LIKED_CACHE) as f:
                data = json.load(f)
            self.playlist_name = data.get("playlist_name", "")
            self.songs = data.get("songs", [])
        except Exception:
            pass

    def _load_shuffle(self):
        try:
            with open(SHUFFLE_FILE) as f:
                self.shuffle_mode = json.load(f).get("shuffle", True)
        except Exception:
            self.shuffle_mode = True

    def _save_shuffle(self):
        with open(SHUFFLE_FILE, "w") as f:
            json.dump({"shuffle": self.shuffle_mode}, f)

    def _write_status(self, state, extra=None):
        s = {"state": state}
        if self.current_song:
            s["name"] = self.current_song["name"]
            s["artist"] = self.current_song["artist"]
        if self.playlist_name:
            s["playlist"] = self.playlist_name
        if self.current_index >= 0:
            s["index"] = self.current_index
        if extra:
            s.update(extra)
        with open(STATUS_FILE, "w") as f:
            json.dump(s, f, ensure_ascii=False)

    @staticmethod
    def _ncm_cmd(*args):
        try:
            r = subprocess.run(
                ["node", NCM_API] + list(args),
                capture_output=True, text=True, timeout=15)
            return json.loads(r.stdout)
        except Exception as e:
            return {"success": False, "msg": str(e)}

    @staticmethod
    def _kill_old_ffplay():
        subprocess.run(["pkill", "-9", "ffplay"], capture_output=True)

    # ── 播放控制 ──

    def _get_url(self, song_id):
        r = self._ncm_cmd("url", str(song_id))
        if r.get("success"):
            return r["url"]
        return None

    def _play_index(self, idx, seek=0):
        if not self.songs or idx < 0 or idx >= len(self.songs):
            return
        self._stop()
        # 非续播时重置断点记录
        if seek == 0:
            self._paused_elapsed = 0
            self._paused_song_id = None
        self.current_index = idx
        self.current_song = self.songs[idx]
        url = self._get_url(self.current_song["id"])
        if url:
            name = f"{self.current_song['name']} - {self.current_song['artist']}"
            _plog(f"[Player] ♪ {name}" + (f" (续播 {seek:.0f}s)" if seek else ""))
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]
            if seek > 0:
                cmd += ["-ss", str(int(seek))]
            cmd.append(url)
            self._ffplay = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.playing = True
            self._play_start_time = time.time()
            self._write_status("playing")
        else:
            _plog(f"[Player] 无法播放: {self.current_song['name']}")
            self.playing = False
            self._write_status("stopped")

    def _stop(self):
        if self._ffplay:
            try:
                self._ffplay.terminate()
                self._ffplay.wait(timeout=2)
            except Exception:
                self._ffplay.kill()
            self._ffplay = None
        self.playing = False

    def play_next(self):
        if not self.songs:
            return
        if self.shuffle_mode:
            idx = random.randint(0, len(self.songs) - 1)
        else:
            idx = (self.current_index + 1) % len(self.songs)
        self._play_index(idx)

    def play_prev(self):
        if not self.songs:
            return
        if self.shuffle_mode:
            idx = random.randint(0, len(self.songs) - 1)
        else:
            idx = (self.current_index - 1 + len(self.songs)) % len(self.songs)
        self._play_index(idx)

    def toggle_play(self):
        if self.playing:
            # 暂停：记录已播放秒数
            elapsed = time.time() - self._play_start_time
            self._paused_elapsed = elapsed + self._paused_elapsed  # 当前位置 = seek位置 + 本次播放时长
            self._paused_song_id = self.current_song["id"] if self.current_song else None
            _plog(f"[Player] 暂停 at {self._paused_elapsed:.1f}s (本次{elapsed:.1f}s + 累计{self._paused_elapsed - elapsed:.1f}s), song_id={self._paused_song_id}")
            self._stop()
            self._write_status("paused")
        elif self.current_song:
            # 续播
            _plog(f"[Player] 恢复检查: song_id match={self.current_song['id'] == self._paused_song_id}, _paused_elapsed={self._paused_elapsed:.1f}")
            if self._paused_song_id == self.current_song["id"] and self._paused_elapsed > 0:
                seek = self._paused_elapsed
                _plog(f"[Player] 续播 from {seek:.1f}s")
                self._play_index(self.current_index, seek=seek)
            else:
                _plog(f"[Player] 从头播放")
                self._play_index(self.current_index)
        elif self.songs:
            self.play_next()

    def toggle_shuffle(self):
        self.shuffle_mode = not self.shuffle_mode
        self._save_shuffle()
        mode = "随机" if self.shuffle_mode else "顺序"
        _plog(f"[Player] 播放模式: {mode}")

    # ── 语音指令处理 ──

    def _handle_request(self, req):
        act = req.get("action", "")
        _plog(f"[Player] 收到指令: {act}")

        if act == "play_index":
            idx = req.get("index", -1)
            self._load_playlist()
            if 0 <= idx < len(self.songs):
                self._play_index(idx)

        elif act == "play_search":
            kw = req.get("keyword", "")
            r = self._ncm_cmd("search", kw)
            if r.get("success") and r.get("songs"):
                song = r["songs"][0]
                url = self._get_url(song["id"])
                if url:
                    self._stop()
                    self.current_song = song
                    self.current_index = -1
                    name = f"{song['name']} - {song['artist']}"
                    _plog(f"[Player] ♪ {name}")
                    self._ffplay = subprocess.Popen(
                        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", url],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.playing = True
                    self._write_status("playing")

        elif act == "switch_playlist":
            kw = req.get("keyword", "")
            r = self._ncm_cmd("playlist", kw)
            if r.get("success"):
                self._load_playlist()
                if self.songs:
                    if self.shuffle_mode:
                        idx = random.randint(0, len(self.songs) - 1)
                    else:
                        idx = 0
                    self._play_index(idx)

        elif act == "play_random":
            self._load_playlist()
            if self.songs:
                self.play_next()

        elif act == "play_liked":
            # 专门播放"我喜欢的音乐"，从 API 刷新缓存
            r = self._ncm_cmd("liked")
            if r.get("success"):
                self._load_playlist()
                if self.songs:
                    self.play_next()

        elif act == "stop":
            self._stop()
            self._write_status("stopped")

        elif act == "next":
            self.play_next()

        elif act == "prev":
            self.play_prev()

        elif act == "pause":
            if self.playing and self.current_song:
                elapsed = time.time() - self._play_start_time
                self._paused_elapsed = elapsed + self._paused_elapsed  # 当前位置 = seek位置 + 本次播放时长
                self._paused_song_id = self.current_song["id"]
                self._stop()
                self.paused_by_voice = True
                self._write_status("paused")
                _plog(f"[Player] 暂停 ({self._paused_elapsed:.0f}s)")

        elif act == "resume":
            if self.paused_by_voice and self.current_song:
                if self.current_song["id"] == self._paused_song_id and self._paused_elapsed > 0:
                    _plog(f"[Player] 续播 ({self._paused_elapsed:.0f}s)")
                    self._play_index(self.current_index, seek=self._paused_elapsed)
                else:
                    self._play_index(self.current_index)
            self.paused_by_voice = False

    # ── 每帧调用 ──

    def update(self):
        # 读取语音指令
        try:
            mt = os.path.getmtime(REQUEST_FILE)
            if mt != getattr(self, '_last_req_mtime', 0):
                self._last_req_mtime = mt
                with open(REQUEST_FILE) as f:
                    req = json.load(f)
                self._handle_request(req)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        except Exception:
            pass

        # 检测 ffplay 播放结束
        if self._ffplay and self.playing:
            ret = self._ffplay.poll()
            if ret is not None:
                self._ffplay = None
                self.playing = False
                # 自动下一首
                if self.songs:
                    self.play_next()
                else:
                    self._write_status("stopped")

    # ── 点击处理 ──

    def handle_click(self, mx, my):
        """返回 True 表示点击在播放器按钮上"""
        btn_y = self.y + self.h - BTN_R - 8
        btns = self._button_centers(btn_y)

        for name, cx in btns.items():
            dx, dy = mx - cx, my - btn_y
            if dx * dx + dy * dy <= (BTN_R + 5) ** 2:
                self._on_button(name)
                return True
        # 检查是否点在歌曲信息区域（未来可扩展）
        return False

    def _button_centers(self, cy):
        spacing = 50
        cx = self.x + self.w // 2
        return {
            "prev":      cx - spacing * 2,
            "play":      cx - spacing,
            "next":      cx,
            "shuffle":   cx + spacing,
        }

    def _on_button(self, name):
        if name == "prev":
            self.play_prev()
        elif name == "play":
            self.toggle_play()
        elif name == "next":
            self.play_next()
        elif name == "shuffle":
            self.toggle_shuffle()

    # ── 绘制 ──

    def draw(self):
        # 背景
        pygame.draw.rect(self.screen, (40, 40, 58),
                         (self.x, self.y, self.w, self.h), border_radius=10)
        pygame.draw.rect(self.screen, (90, 90, 120),
                         (self.x, self.y, self.w, self.h), 2, border_radius=10)

        pad = 12

        # 歌单名
        pl_text = self.playlist_name or "未选择歌单"
        pl_surf = self.font_pl.render(pl_text, True, (170, 170, 200))
        self.screen.blit(pl_surf, (self.x + pad, self.y + 8))

        # 当前歌曲
        if self.current_song:
            song_text = self.current_song["name"]
            artist_text = self.current_song["artist"]
            # 截断过长的歌名
            max_w = self.w - pad * 2
            song_surf = self.font_song.render(song_text, True, (255, 255, 255))
            if song_surf.get_width() > max_w:
                # 简单截断
                while len(song_text) > 4 and self.font_song.size(song_text + "...")[0] > max_w:
                    song_text = song_text[:-1]
                song_surf = self.font_song.render(song_text + "...", True, (255, 255, 255))
            self.screen.blit(song_surf, (self.x + pad, self.y + 26))

            artist_surf = self.font_pl.render(artist_text, True, (160, 160, 190))
            if artist_surf.get_width() > max_w:
                while len(artist_text) > 4 and self.font_pl.size(artist_text + "...")[0] > max_w:
                    artist_text = artist_text[:-1]
                artist_surf = self.font_pl.render(artist_text + "...", True, (160, 160, 190))
            self.screen.blit(artist_surf, (self.x + pad, self.y + 44))
        else:
            hint = self.font_pl.render("点击 ▶ 开始播放", True, (140, 140, 170))
            self.screen.blit(hint, (self.x + pad, self.y + 32))

        # 按钮行
        btn_y = self.y + self.h - BTN_R - 8
        btns = self._button_centers(btn_y)

        # 上一曲
        self._draw_btn(btns["prev"], btn_y, "prev")
        # 播放/暂停
        self._draw_btn(btns["play"], btn_y, "play")
        # 下一曲
        self._draw_btn(btns["next"], btn_y, "next")
        # 随机/顺序
        self._draw_btn(btns["shuffle"], btn_y, "shuffle")

    def _draw_btn(self, cx, cy, btn_type):
        # 按钮背景
        pygame.draw.circle(self.screen, (55, 55, 78), (cx, cy), BTN_R)
        pygame.draw.circle(self.screen, (120, 120, 155), (cx, cy), BTN_R, 2)

        color = (230, 230, 250)

        if btn_type == "prev":
            # |<
            pygame.draw.polygon(self.screen, color, [
                (cx - 2, cy - 8), (cx - 2, cy + 8), (cx - 10, cy)
            ])
            pygame.draw.line(self.screen, color, (cx + 4, cy - 8), (cx + 4, cy + 8), 2)

        elif btn_type == "play":
            if self.playing:
                # 暂停 ||
                pygame.draw.rect(self.screen, color, (cx - 7, cy - 8, 4, 16))
                pygame.draw.rect(self.screen, color, (cx + 3, cy - 8, 4, 16))
            else:
                # 播放 ▶
                pygame.draw.polygon(self.screen, color, [
                    (cx - 6, cy - 9), (cx - 6, cy + 9), (cx + 8, cy)
                ])

        elif btn_type == "next":
            # >|
            pygame.draw.polygon(self.screen, color, [
                (cx + 2, cy - 8), (cx + 2, cy + 8), (cx + 10, cy)
            ])
            pygame.draw.line(self.screen, color, (cx - 4, cy - 8), (cx - 4, cy + 8), 2)

        elif btn_type == "shuffle":
            # 随机/顺序图标 — 交叉箭头 vs 直线箭头
            if self.shuffle_mode:
                # 交叉箭头 (随机)
                pygame.draw.line(self.screen, color, (cx - 8, cy - 6), (cx + 4, cy + 6), 2)
                pygame.draw.line(self.screen, color, (cx - 8, cy + 6), (cx + 4, cy - 6), 2)
                # 箭头头
                pygame.draw.polygon(self.screen, color, [
                    (cx + 4, cy + 6), (cx + 4, cy), (cx + 9, cy + 4)
                ])
                pygame.draw.polygon(self.screen, color, [
                    (cx + 4, cy - 6), (cx + 4, cy), (cx + 9, cy - 4)
                ])
                # 底部标签
                lbl = self.font_pl.render("R", True, (80, 230, 80))
            else:
                # 直线箭头 (顺序)
                pygame.draw.line(self.screen, color, (cx - 8, cy), (cx + 6, cy), 2)
                pygame.draw.polygon(self.screen, color, [
                    (cx + 6, cy), (cx + 1, cy - 5), (cx + 1, cy + 5)
                ])
                lbl = self.font_pl.render("S", True, (190, 190, 230))
            self.screen.blit(lbl, (cx - 3, cy + BTN_R - 4))

    def cleanup(self):
        self._stop()
