#!/usr/bin/env python3
"""
send_msg.py — 给机器人屏幕发消息和情绪
用法: python3 send_msg.py "消息内容" [emotion]
emotion: idle, happy, surprised, love, sleepy
"""
import sys

msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
emotion = "idle"

# 检查最后一个参数是否是情绪标签
valid_emotions = ["idle", "happy", "surprised", "love", "sleepy", "sad", "angry", "shy"]
if sys.argv[-1] in valid_emotions and len(sys.argv) > 2:
    emotion = sys.argv[-1]
    msg = " ".join(sys.argv[1:-1])

with open("/home/jacob/robot/message.txt", "w", encoding="utf-8") as f:
    f.write(msg)

with open("/home/jacob/robot/emotion.txt", "w", encoding="utf-8") as f:
    f.write(emotion)

print(f"Sent: {msg} [{emotion}]")
