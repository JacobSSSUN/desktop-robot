"""
reminder.py — 定时提醒管理模块
存储、检查、触发提醒
"""
import json
import time
import os
import uuid
import numpy as np


REMINDER_FILE = os.path.join(os.path.dirname(__file__), "reminders.json")


def _load():
    if os.path.exists(REMINDER_FILE):
        with open(REMINDER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(reminders):
    with open(REMINDER_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)


def add_reminder(when_ts, message):
    """添加一个提醒。when_ts: 触发时间戳, message: 提醒内容"""
    reminders = _load()
    r = {
        "id": uuid.uuid4().hex[:8],
        "time": when_ts,
        "message": message,
        "status": "pending",
    }
    reminders.append(r)
    _save(reminders)
    print(f"[Reminder] 添加: {message} @ {time.strftime('%H:%M', time.localtime(when_ts))}")
    return r


def check_due():
    """检查并返回已到期的提醒列表，标记为 triggered"""
    reminders = _load()
    now = time.time()
    due = []
    changed = False
    for r in reminders:
        if r["status"] == "pending" and r["time"] <= now:
            r["status"] = "triggered"
            due.append(r)
            changed = True
    if changed:
        _save(reminders)
    return due


def dismiss(rid):
    """标记提醒为已读"""
    reminders = _load()
    for r in reminders:
        if r["id"] == rid:
            r["status"] = "dismissed"
    _save(reminders)


def dismiss_all_triggered():
    """把所有 triggered 的标记为 dismissed"""
    reminders = _load()
    changed = False
    for r in reminders:
        if r["status"] == "triggered":
            r["status"] = "dismissed"
            changed = True
    if changed:
        _save(reminders)


def snooze(rid, minutes=5):
    """推迟一个提醒"""
    reminders = _load()
    for r in reminders:
        if r["id"] == rid:
            r["time"] = time.time() + minutes * 60
            r["status"] = "pending"
            print(f"[Reminder] 推迟 {minutes}分钟: {r['message']}")
    _save(reminders)


def list_pending():
    """列出所有待触发的提醒"""
    reminders = _load()
    return [r for r in reminders if r["status"] == "pending"]


def cancel_last():
    """取消最近添加的 pending 提醒"""
    reminders = _load()
    for r in reversed(reminders):
        if r["status"] == "pending":
            r["status"] = "cancelled"
            _save(reminders)
            print(f"[Reminder] 取消: {r['message']}")
            return r
    return None


def cleanup_old(max_age_hours=48):
    """清理超过 max_age_hours 的非 pending 提醒"""
    reminders = _load()
    now = time.time()
    cutoff = now - max_age_hours * 3600
    reminders = [r for r in reminders if r["status"] == "pending" or r["time"] > cutoff]
    _save(reminders)


def play_ding():
    """播放叮咚提示音（numpy 合成）"""
    import pygame
    sample_rate = 22050
    duration = 0.15
    # 第一个音 800Hz
    t1 = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    tone1 = np.sin(2 * np.pi * 800 * t1) * 0.5
    # 第二个音 1200Hz
    t2 = np.linspace(0, duration * 1.5, int(sample_rate * duration * 1.5), endpoint=False)
    tone2 = np.sin(2 * np.pi * 1200 * t2) * 0.5
    # 拼接 + 淡出
    sound = np.concatenate([tone1, tone2])
    fade = np.linspace(1, 0, len(sound))
    sound = (sound * fade * 32767).astype(np.int16)
    try:
        snd = pygame.mixer.Sound(buffer=sound)
        snd.play()
    except Exception as e:
        print(f"[Reminder] 播放音效失败: {e}")
