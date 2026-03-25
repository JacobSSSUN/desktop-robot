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
from font_helper import get_font

import threading
import re

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

BTN_R = 20  # 按钮圆半径


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
        self._seeking = False        # seek/快进快退时跳过自动下一首

        self.font_song = get_font(24, bold=True)
        self.font_pl = get_font(16, bold=True)
        self.font_btn = get_font(18, bold=True)
        self.font_lyric_cur = get_font(22, bold=True)   # 当前歌词行
        self.font_lyric_adj = get_font(15)               # 上下歌词行

        # 歌词
        self._lyrics = []           # [(秒数, 文本), ...]
        self._lyrics_song_id = None # 当前歌词对应的 song_id
        self._lyrics_loading = False
        self._song_loading = False  # 歌曲正在加载

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

    # ── 歌词相关 ──

    def get_elapsed(self):
        """获取当前播放位置（秒）"""
        if self.playing:
            return time.time() - self._play_start_time + self._paused_elapsed
        return self._paused_elapsed

    @staticmethod
    def _parse_lrc(lrc_text):
        """解析 LRC 格式 → [(秒数, 文本), ...]"""
        results = []
        for line in lrc_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 匹配 [mm:ss.xx] 或 [mm:ss.xxx] 格式
            parts = re.split(r'\[(\d{2}:\d{2}\.\d{2,3})\]', line)
            # parts: ['', '00:01.38', '歌词文本', '', '00:04.90', '下一歌词', ...]
            i = 1
            while i < len(parts) - 1:
                time_str = parts[i]
                text = parts[i + 1].strip()
                # 解析时间
                try:
                    m, s = time_str.split(':')
                    sec = int(m) * 60 + float(s)
                    if text:  # 跳过空文本行
                        results.append((sec, text))
                except ValueError:
                    pass
                i += 2
        results.sort(key=lambda x: x[0])
        return results

    def _fetch_lyrics(self, song_id):
        """异步获取歌词"""
        if self._lyrics_loading:
            return
        self._lyrics_loading = True

        def _do_fetch():
            try:
                r = self._ncm_cmd("lyric", str(song_id))
                if r.get("success") and r.get("lrc"):
                    lrc_text = r["lrc"]
                    if "暂无歌词" in lrc_text or not lrc_text.strip():
                        self._lyrics = []
                    else:
                        self._lyrics = self._parse_lrc(lrc_text)
                        _plog(f"[Lyrics] 获取到 {len(self._lyrics)} 行歌词")
                else:
                    self._lyrics = []
                self._lyrics_song_id = song_id
            except Exception as e:
                _plog(f"[Lyrics] 获取失败: {e}")
                self._lyrics = []
            finally:
                self._lyrics_loading = False
                self._song_loading = False

        threading.Thread(target=_do_fetch, daemon=True).start()

    def _get_current_lyric_index(self):
        """根据播放时间找到当前歌词行索引"""
        if not self._lyrics:
            return -1
        elapsed = self.get_elapsed()
        idx = -1
        for i, (ts, _) in enumerate(self._lyrics):
            if ts <= elapsed:
                idx = i
            else:
                break
        return idx

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
            # 获取歌词
            self._lyrics = []
            self._song_loading = True
            self._fetch_lyrics(self.current_song["id"])
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

    def fast_forward(self, seconds=10):
        """快进 N 秒"""
        if not self.current_song:
            return
        elapsed = self.get_elapsed()
        new_pos = elapsed + seconds
        _plog(f"[Player] 快进 {seconds}s → {new_pos:.0f}s")
        self._seeking = True
        idx = self.current_index
        self._play_index(idx, seek=new_pos)
        self._seeking = False

    def fast_rewind(self, seconds=10):
        """快退 N 秒"""
        if not self.current_song:
            return
        elapsed = self.get_elapsed()
        new_pos = max(0, elapsed - seconds)
        _plog(f"[Player] 快退 {seconds}s → {new_pos:.0f}s")
        self._seeking = True
        idx = self.current_index
        self._play_index(idx, seek=new_pos)
        self._seeking = False

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
                    self._play_start_time = time.time()
                    self._paused_elapsed = 0
                    self._write_status("playing")
                    self._lyrics = []
                    self._fetch_lyrics(song["id"])

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
                if self._seeking:
                    # 正在 seek 中，不自动下一首
                    return
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
        return False

    def _button_centers(self, cy):
        spacing = 60
        cx = self.x + self.w // 2
        return {
            "prev":      cx - spacing * 1.5,
            "play":      cx - spacing * 0.5,
            "next":      cx + spacing * 0.5,
            "shuffle":   cx + spacing * 1.5,
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

    def _truncate_text(self, font, text, max_w):
        """截断过长文本，加省略号"""
        if font.size(text)[0] <= max_w:
            return text
        while len(text) > 1 and font.size(text + "…")[0] > max_w:
            text = text[:-1]
        return text + "…"

    def _render_lyric_line(self, font, text, color, max_w):
        """渲染歌词行，超长自动换行，返回 surface 列表"""
        if font.size(text)[0] <= max_w:
            return [font.render(text, True, color)]
        # 找到合适的断点
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.size(text[:mid])[0] <= max_w:
                lo = mid
            else:
                hi = mid - 1
        line1 = text[:lo]
        line2 = text[lo:]
        surfs = [font.render(line1, True, color)]
        if line2:
            # 第二行截断
            if font.size(line2)[0] > max_w:
                while len(line2) > 1 and font.size(line2 + "…")[0] > max_w:
                    line2 = line2[:-1]
                line2 += "…"
            surfs.append(font.render(line2, True, color))
        return surfs

    def draw(self):
        # 背景
        pygame.draw.rect(self.screen, (40, 40, 58),
                         (self.x, self.y, self.w, self.h), border_radius=10)
        pygame.draw.rect(self.screen, (130, 130, 170),
                         (self.x, self.y, self.w, self.h), 2, border_radius=10)

        pad = 12
        max_w = self.w - pad * 2
        cx = self.x + self.w // 2

        # ── 歌名区 (y+6 ~ y+70, 有间距) ──

        pl_text = self.playlist_name or "未选择歌单"
        pl_surf = self.font_pl.render(self._truncate_text(self.font_pl, pl_text, max_w), True, (210, 210, 240))
        self.screen.blit(pl_surf, (self.x + pad, self.y + 6))

        if self.current_song:
            song_text = self._truncate_text(self.font_song, self.current_song["name"], max_w)
            song_surf = self.font_song.render(song_text, True, (255, 255, 255))
            self.screen.blit(song_surf, (self.x + pad, self.y + 28))

            artist_text = self._truncate_text(self.font_pl, self.current_song["artist"], max_w)
            artist_surf = self.font_pl.render(artist_text, True, (180, 180, 215))
            self.screen.blit(artist_surf, (self.x + pad, self.y + 56))
        else:
            hint = self.font_pl.render("点击 ▶ 开始播放", True, (180, 180, 210))
            self.screen.blit(hint, (self.x + pad, self.y + 36))

        # ── 歌词区 (y+76 ~ y+178) ──
        lyric_top = self.y + 76
        lyric_bottom = self.y + 170
        lyric_h = lyric_bottom - lyric_top
        cur_idx = self._get_current_lyric_index()

        if getattr(self, '_song_loading', False):
            # 歌曲加载中
            text = "歌曲加载中"
            surf = self.font_lyric_cur.render(text, True, (200, 200, 230))
            sy = lyric_top + (lyric_h - surf.get_height()) // 2
            self.screen.blit(surf, (cx - surf.get_width() // 2, sy))

        elif self._lyrics and cur_idx >= 0:
            # 只显示当前行，支持换行
            cur_surfs = self._render_lyric_line(
                self.font_lyric_cur, self._lyrics[cur_idx][1], (255, 255, 255), max_w)
            # 限制最多 4 行
            cur_surfs = cur_surfs[:4]
            total_h = sum(s.get_height() for s in cur_surfs) + (len(cur_surfs) - 1) * 4
            draw_y = lyric_top + (lyric_h - total_h) // 2
            for surf in cur_surfs:
                self.screen.blit(surf, (cx - surf.get_width() // 2, draw_y))
                draw_y += surf.get_height() + 4

        elif self.current_song and self.playing:
            text = "暂无歌词"
            surf = self.font_lyric_cur.render(text, True, (200, 200, 230))
            sy = lyric_top + (lyric_h - surf.get_height()) // 2
            self.screen.blit(surf, (cx - surf.get_width() // 2, sy))

        elif self._lyrics_loading:
            text = "加载歌词中"
            surf = self.font_lyric_cur.render(text, True, (200, 200, 230))
            sy = lyric_top + (lyric_h - surf.get_height()) // 2
            self.screen.blit(surf, (cx - surf.get_width() // 2, sy))

        else:
            text = "♪ 点击播放，享受音乐 ♪"
            surf = self.font_lyric_cur.render(text, True, (200, 200, 230))
            sy = lyric_top + (lyric_h - surf.get_height()) // 2
            self.screen.blit(surf, (cx - surf.get_width() // 2, sy))

        # ── 进度条 (在按钮上方，不被遮挡) ──
        if self.current_song:
            bar_x = self.x + pad
            bar_w = max_w
            bar_y = self.y + 174
            bar_h = 8
            elapsed = self.get_elapsed()
            prog = min(1.0, elapsed / 240.0)
            # 未播放部分 — 高对比灰色
            pygame.draw.rect(self.screen, (90, 90, 120), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
            # 已播放部分
            if prog > 0:
                pygame.draw.rect(self.screen, (130, 150, 230),
                                 (bar_x, bar_y, int(bar_w * prog), bar_h), border_radius=4)

        # ── 按钮 (底部) ──
        btn_y = self.y + self.h - BTN_R - 8
        btns = self._button_centers(btn_y)

        self._draw_btn(btns["prev"], btn_y, "prev")
        self._draw_btn(btns["play"], btn_y, "play")
        self._draw_btn(btns["next"], btn_y, "next")
        self._draw_btn(btns["shuffle"], btn_y, "shuffle")

    def _draw_btn(self, cx, cy, btn_type):
        # 按钮背景
        pygame.draw.circle(self.screen, (65, 65, 90), (cx, cy), BTN_R)
        pygame.draw.circle(self.screen, (140, 140, 175), (cx, cy), BTN_R, 2)

        color = (240, 240, 255)

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
            else:
                # 直线箭头 (顺序)
                pygame.draw.line(self.screen, color, (cx - 8, cy), (cx + 6, cy), 2)
                pygame.draw.polygon(self.screen, color, [
                    (cx + 6, cy), (cx + 1, cy - 5), (cx + 1, cy + 5)
                ])

    def cleanup(self):
        self._stop()
