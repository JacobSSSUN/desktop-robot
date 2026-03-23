#!/usr/bin/env python3
"""
chat_bridge.py — 语音对话桥接
监听 chat_in.txt → HA 设备控制 / Notion 笔记记录 / OpenClaw 对话 → 写入 chat_out.txt
"""
import os
import json
import time
import sys
import requests

CHAT_IN = "/home/jacob/robot/chat_in.txt"
CHAT_OUT = "/home/jacob/robot/chat_out.txt"
GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
GATEWAY_TOKEN = "43043f2491fe85f41e1c6e78c7727f7afa9a30c3fb9056c2"
SESSION_USER = "robot-voice"
TIMEOUT = 30

# 导入 HA 桥接
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ha_bridge import handle_voice_command
from notion_bridge import detect_record_intent, write_to_notion
from notion_reminder import query_due_reminders, extract_reminder_info, tts_speak

# 提醒检查
_reminder_log = {}  # {page_id_datestr: timestamp}
_reminder_counter = 0
REMINDER_CHECK_INTERVAL = 60  # 每60轮检查一次（约30秒）


def send_to_openclaw(text):
    """发送消息到 OpenClaw，返回回复文本"""
    headers = {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openclaw:main",
        "user": SESSION_USER,
        "messages": [{"role": "user", "content": text + "\n\n（请用简短口语化的中文回复，不要用 markdown 或 emoji）"}],
    }
    try:
        resp = requests.post(GATEWAY_URL, headers=headers, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        print(f"[Bridge] API 错误: {e}")
        return None


def write_reply(text):
    """写入回复文件"""
    with open(CHAT_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    os.utime(CHAT_OUT, None)


def cleanup():
    for f in [CHAT_IN, CHAT_OUT]:
        try:
            os.remove(f)
        except FileNotFoundError:
            pass


def check_reminders():
    """检查到期的 Notion 提醒"""
    global _reminder_log
    try:
        results = query_due_reminders()
        for page in results:
            page_id, title, date_str, tag = extract_reminder_info(page)
            key = f"{page_id}_{date_str}"
            if key not in _reminder_log:
                print(f"[Reminder] 到期: {title}")
                tts_speak(title)
                _reminder_log[key] = time.time()
    except Exception as e:
        print(f"[Reminder] 检查失败: {e}")


def main():
    global _reminder_counter
    print("=== 🌉 Chat Bridge 启动 ===")
    print(f"  监听: {CHAT_IN}")
    print(f"  回复: {CHAT_OUT}")
    print(f"  HA: 已集成")
    print(f"  Notion: 已集成（莓虾笔记）")
    print(f"  OpenClaw: {GATEWAY_URL}")
    print()

    cleanup()
    last_mtime = 0

    try:
        while True:
            try:
                mtime = os.path.getmtime(CHAT_IN)
                if mtime > last_mtime:
                    last_mtime = mtime
                    time.sleep(0.3)

                    with open(CHAT_IN, "r", encoding="utf-8") as f:
                        text = f.read().strip()

                    if text:
                        print(f"[Bridge] 收到: {text}")

                        # 1. 先尝试 HA 设备控制
                        is_cmd, reply = handle_voice_command(text)
                        if is_cmd:
                            print(f"[Bridge] HA 指令: {reply}")
                            write_reply(reply)
                            continue

                        # 2. 检查 Notion 记录意图
                        is_record, content, tag = detect_record_intent(text)
                        if is_record:
                            ok = write_to_notion(content, content, tag)
                            if ok:
                                reply = f"记好了，标签：{tag}"
                            else:
                                reply = "记笔记失败了，稍后再试"
                            print(f"[Bridge] Notion: {reply}")
                            write_reply(reply)
                            continue

                        # 3. 走 OpenClaw 对话
                        reply = send_to_openclaw(text)
                        if reply:
                            print(f"[Bridge] 回复: {reply}")
                            write_reply(reply)
                        else:
                            write_reply("抱歉，我暂时无法回答")
                            print("[Bridge] 超时或错误")
            except FileNotFoundError:
                pass

            # 定期检查 Notion 提醒
            _reminder_counter += 1
            if _reminder_counter >= REMINDER_CHECK_INTERVAL:
                _reminder_counter = 0
                check_reminders()

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[Bridge] 停止")
        cleanup()


if __name__ == "__main__":
    main()
