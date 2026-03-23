#!/usr/bin/env python3
"""
ncm_player.py — 网易云音乐播放器（VIP 支持）
用法:
  python3 ncm_player.py                     # 随机播放我喜欢的歌
  python3 ncm_player.py <序号>              # 播放第 N 首
  python3 ncm_player.py <搜索关键词>         # 搜索并播放
  python3 ncm_player.py --playlist          # 显示歌单
  python3 ncm_player.py --search <关键词>    # 只搜索
  python3 ncm_player.py --next              # 下一首（随机）
  python3 ncm_player.py --stop              # 停止播放
"""
import sys
import json
import subprocess
import os
import time
import random
import signal

ROBOT_DIR = "/home/jacob/robot"
NCM_API = os.path.join(ROBOT_DIR, "ncm_api.js")
STATUS_FILE = os.path.join(ROBOT_DIR, "music_status.json")
LIKED_CACHE = os.path.join(ROBOT_DIR, "ncm_liked.json")

_current_proc = None


def ncm_cmd(*args):
    """调用 ncm_api.js"""
    try:
        result = subprocess.run(
            ["node", NCM_API] + list(args),
            capture_output=True, text=True, timeout=15,
        )
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[NCM] 命令失败: {e}")
        return {"success": False, "msg": str(e)}


def write_status(status):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False)


def load_liked():
    """加载缓存的歌单"""
    try:
        with open(LIKED_CACHE, "r") as f:
            data = json.load(f)
        if time.time() - data.get("time", 0) < 3600:  # 1小时缓存
            return data.get("songs", [])
    except Exception:
        pass
    return None


def fetch_liked():
    """从 API 获取歌单"""
    result = ncm_cmd("liked")
    if result.get("success"):
        return result.get("songs", [])
    return []


def fetch_playlist(keyword):
    """从 API 获取指定歌单"""
    result = ncm_cmd("playlist", keyword)
    if result.get("success"):
        print(f"[NCM] 歌单: {result.get('name')} ({result.get('count', 0)} 首)")
        return result.get("songs", [])
    else:
        print(f"[NCM] {result.get('msg', '找不到歌单')}")
    return []


def play_song(url, song_info):
    """播放歌曲"""
    global _current_proc
    name = f"{song_info['name']} - {song_info['artist']}"
    print(f"[NCM] ♪ 播放: {name}")
    write_status({"state": "playing", "name": song_info["name"], "artist": song_info["artist"]})

    _current_proc = subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _current_proc.wait()
    except KeyboardInterrupt:
        _current_proc.terminate()
    finally:
        _current_proc = None
        write_status({"state": "stopped"})
        print("[NCM] 播放结束")


def play_by_id(song_id, song_info=None):
    """根据 ID 播放"""
    if song_info is None:
        song_info = {"name": "未知", "artist": "未知"}
    result = ncm_cmd("url", str(song_id))
    if result.get("success"):
        play_song(result["url"], song_info)
    else:
        print(f"[NCM] 无法播放: {song_info.get('name', song_id)}")


def play_liked(index=None):
    """播放我喜欢的歌单"""
    songs = load_liked()
    if not songs:
        print("[NCM] 加载歌单...")
        songs = fetch_liked()
    if not songs:
        print("[NCM] 歌单为空")
        return

    if index is not None:
        if 0 <= index < len(songs):
            song = songs[index]
        else:
            print(f"[NCM] 序号 1-{len(songs)}")
            return
    else:
        song = random.choice(songs)

    play_by_id(song["id"], song)


def play_search(keyword):
    """搜索并播放"""
    result = ncm_cmd("search", keyword)
    if result.get("success") and result.get("songs"):
        song = result["songs"][0]
        print(f"[NCM] 找到: {song['name']} - {song['artist']}")
        play_by_id(song["id"], song)
    else:
        print("[NCM] 没找到")


def show_playlist():
    """显示歌单"""
    songs = load_liked()
    if not songs:
        print("[NCM] 加载歌单...")
        songs = fetch_liked()
    if songs:
        print(f"\n🎵 我喜欢的音乐 ({len(songs)} 首)")
        print("=" * 45)
        for i, s in enumerate(songs[:30]):
            print(f"  {i+1:3d}. {s['name']} - {s['artist']}")
        if len(songs) > 30:
            print(f"  ... 还有 {len(songs)-30} 首")


def stop_play():
    """停止播放"""
    global _current_proc
    if _current_proc:
        _current_proc.terminate()
        _current_proc = None
        write_status({"state": "stopped"})
        print("[NCM] 已停止")


def signal_handler(sig, frame):
    stop_play()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main():
    if len(sys.argv) < 2:
        play_liked()
        return

    cmd = sys.argv[1]
    if cmd == "--playlist":
        show_playlist()
    elif cmd == "--search":
        play_search(" ".join(sys.argv[2:]))
    elif cmd == "--stop":
        stop_play()
    elif cmd == "--next":
        play_liked()
    elif cmd == "--switch":
        keyword = " ".join(sys.argv[2:])
        songs = fetch_playlist(keyword)
        if songs:
            song = random.choice(songs)
            play_by_id(song["id"], song)
        else:
            print(f"[NCM] 找不到歌单: {keyword}")
    elif cmd == "--index":
        # 播放指定索引（0-based）
        try:
            idx = int(sys.argv[2])
            songs = load_liked()
            if not songs:
                songs = fetch_liked()
            if songs and 0 <= idx < len(songs):
                song = songs[idx]
                play_by_id(song["id"], song)
            else:
                print(f"[NCM] 索引超出范围: {idx+1}")
        except (ValueError, IndexError):
            print("[NCM] 用法: ncm_player.py --index <N>")
    elif cmd == "--check":
        result = ncm_cmd("check")
        print(json.dumps(result, ensure_ascii=False))
    else:
        # 尝试作为序号
        try:
            idx = int(cmd) - 1
            play_liked(idx)
        except ValueError:
            # 作为搜索关键词
            play_search(" ".join(sys.argv[1:]))


if __name__ == "__main__":
    main()
