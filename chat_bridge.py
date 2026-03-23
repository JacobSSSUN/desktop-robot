#!/usr/bin/env python3
"""
chat_bridge.py — 语音对话桥接
监听 chat_in.txt → 先尝试 HA 设备控制 → 否则 OpenClaw 对话 → 写入 chat_out.txt
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


def main():
    print("=== 🌉 Chat Bridge 启动 ===")
    print(f"  监听: {CHAT_IN}")
    print(f"  回复: {CHAT_OUT}")
    print(f"  HA: 已集成")
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

                        # 先尝试 HA 设备控制
                        is_cmd, reply = handle_voice_command(text)
                        if is_cmd:
                            print(f"[Bridge] HA 指令: {reply}")
                            write_reply(reply)
                        else:
                            # 非设备指令，走 OpenClaw 对话
                            reply = send_to_openclaw(text)
                            if reply:
                                print(f"[Bridge] 回复: {reply}")
                                write_reply(reply)
                            else:
                                write_reply("抱歉，我暂时无法回答")
                                print("[Bridge] 超时或错误")
            except FileNotFoundError:
                pass

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[Bridge] 停止")
        cleanup()


if __name__ == "__main__":
    main()
