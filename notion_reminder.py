#!/usr/bin/env python3
"""
notion_reminder.py — Notion 定时提醒检查
查询莓虾笔记数据库，找到到期的提醒，通过 robot TTS 播报
"""
import json
import requests
import subprocess
from datetime import datetime, timedelta

# Notion 配置
import os
_secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".openclaw", "workspace", "secrets", "notion.json")
with open(_secrets_path) as _f:
    _secrets = json.load(_f)
NOTION_TOKEN = _secrets["token"]
DATABASE_ID = _secrets["database_id"]
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# 已提醒记录文件（防止重复提醒）
REMINDER_LOG = "/home/jacob/robot/reminder_log.json"

# TTS 脚本
TTS_SCRIPT = "/home/jacob/robot/tts_speak.sh"


def load_reminder_log():
    try:
        with open(REMINDER_LOG, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_reminder_log(log):
    with open(REMINDER_LOG, "w") as f:
        json.dump(log, f, ensure_ascii=False)


def query_due_reminders():
    """查询到期但未播报的提醒"""
    now = datetime.now()
    # 查询窗口：过去5分钟到现在
    window_start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:00")
    window_end = now.strftime("%Y-%m-%dT%H:%M:00")

    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    payload = {
        "filter": {
            "and": [
                {
                    "property": "日期",
                    "date": {"on_or_after": window_start}
                },
                {
                    "property": "日期",
                    "date": {"on_or_before": window_end}
                }
            ]
        },
        "sorts": [{"property": "日期", "direction": "ascending"}]
    }

    try:
        resp = requests.post(
            f"{NOTION_API}/databases/{DATABASE_ID}/query",
            headers=headers,
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"[Reminder] 查询失败: {e}")
        return []


def extract_reminder_info(page):
    """从 Notion 页面提取提醒信息"""
    props = page.get("properties", {})

    # 标题
    title_prop = props.get("标题", {}).get("title", [])
    title = "".join(t.get("plain_text", "") for t in title_prop) if title_prop else "无标题"

    # 日期（带时间）
    date_prop = props.get("日期", {}).get("date", {})
    date_str = date_prop.get("start", "") if date_prop else ""

    # 标签
    tag_prop = props.get("标签", {}).get("select", {})
    tag = tag_prop.get("name", "") if tag_prop else ""

    page_id = page.get("id", "")

    return page_id, title, date_str, tag


def tts_speak(text):
    """通过机器人 TTS 播报"""
    try:
        # 写入 chat_out.txt，让 main.py 的 TTS 播报
        with open("/home/jacob/robot/chat_out.txt", "w", encoding="utf-8") as f:
            f.write(f"⏰ 提醒：{text}")
        import os
        os.utime("/home/jacob/robot/chat_out.txt", None)
        print(f"[Reminder] TTS: ⏰ 提醒：{text}")
        return True
    except Exception as e:
        print(f"[Reminder] TTS 失败: {e}")
        return False


def main():
    reminder_log = load_reminder_log()
    results = query_due_reminders()

    if not results:
        return

    for page in results:
        page_id, title, date_str, tag = extract_reminder_info(page)
        reminder_key = f"{page_id}_{date_str}"

        # 跳过已提醒的
        if reminder_key in reminder_log:
            continue

        print(f"[Reminder] 到期: {title} ({date_str})")
        ok = tts_speak(title)
        if ok:
            reminder_log[reminder_key] = datetime.now().isoformat()
            save_reminder_log(reminder_log)


if __name__ == "__main__":
    main()
