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

# 情绪关键词检测
EMOTION_KEYWORDS = {
    "tired": ["好累", "累了", "困了", "疲惫", "困", "没精神", "不想动", "好困", "疲倦", "累死了", "乏力"],
    "happy": ["好开心", "太棒了", "哈哈", "真好", "开心", "高兴", "快乐", "兴奋", "激动", "太好了", "超开心", "爽"],
    "sad": ["难过", "伤心", "不开心", "沮丧", "失落", "郁闷", "心情不好", "难受", "想哭", "低落"],
    "angry": ["烦死了", "生气", "气死", "烦人", "恼火", "怒", "可恶", "太过分", "气死我了", "烦"],
    "anxious": ["担心", "焦虑", "紧张", "害怕", "不安", "忧虑", "忐忑", "慌", "心慌"],
    "normal": [],
}

# 情绪对应的提示语
EMOTION_HINTS = {
    "tired": "用户看起来很疲惫，回复要简短、温暖，不要啰嗦，可以说关心的话。",
    "happy": "用户心情不错，可以轻松活泼一点回应。",
    "sad": "用户心情不好，回复要温暖体贴，不要说教，安静陪伴就好。",
    "angry": "用户有点烦躁，回复要简短克制，不要火上浇油，可以适当安抚。",
    "anxious": "用户有些焦虑，回复要安慰支持，给出具体建议。",
    "normal": "",
}


def detect_emotion(text):
    """检测用户情绪，返回 (emotion_name, hint_text)"""
    text_lower = text.lower()
    scores = {}
    for emo, keywords in EMOTION_KEYWORDS.items():
        if emo == "normal":
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[emo] = score
    if scores:
        dominant = max(scores, key=scores.get)
        return dominant, EMOTION_HINTS.get(dominant, "")
    return "normal", ""


PREFS_FILE = "/home/jacob/.openclaw/workspace/memory/preferences.json"

def learn_preference(text):
    """从对话中学习用户偏好，自动存入 preferences.json"""
    import json as _json
    try:
        with open(PREFS_FILE, "r", encoding="utf-8") as f:
            prefs = _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        prefs = {}

    changed = False

    # 温度偏好
    m = re.search(r"(?:喜欢|偏好|调到|设置成?)\s*(?:温度\s*)?(\d{1,2})\s*度", text)
    if m:
        temp = int(m.group(1))
        if prefs.get("comfort", {}).get("preferred_temp") != temp:
            prefs.setdefault("comfort", {})["preferred_temp"] = temp
            prefs["comfort"]["notes"] = f"偏好温度 {temp}°C"
            changed = True
            print(f"[Prefs] 学到温度偏好: {temp}°C")

    # 音乐偏好
    for genre in ["流行", "摇滚", "民谣", "古典", "电子", "爵士", "说唱", "嘻哈", "轻音乐", "古风", "R&B"]:
        if f"喜欢{genre}" in text or f"爱听{genre}" in text or f"偏好{genre}" in text:
            genres = prefs.get("music", {}).get("genres", [])
            if genre not in genres:
                genres.append(genre)
                prefs.setdefault("music", {})["genres"] = genres
                changed = True
                print(f"[Prefs] 学到音乐偏好: {genre}")

    # 作息时间
    m = re.search(r"(?:一般|通常|大概)?\s*(\d{1,2})\s*点\s*(?:左右)?\s*(起床|睡觉|睡|起来)", text)
    if m:
        hour = int(m.group(1))
        action = m.group(2)
        sched = prefs.get("schedule", {})
        if "起" in action:
            if sched.get("wake_time") != hour:
                sched["wake_time"] = hour
                changed = True
                print(f"[Prefs] 学到起床时间: {hour}点")
        elif "睡" in action:
            if sched.get("sleep_time") != hour:
                sched["sleep_time"] = hour
                changed = True
                print(f"[Prefs] 学到睡觉时间: {hour}点")
        if changed:
            prefs["schedule"] = sched

    if changed:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            _json.dump(prefs, f, ensure_ascii=False, indent=2)
        print("[Prefs] 偏好已保存")

# 导入 HA 桥接
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ha_bridge import handle_voice_command
from notion_bridge import detect_record_intent, write_to_notion
from notion_reminder import query_due_reminders, extract_reminder_info, tts_speak

# 提醒检查
_reminder_log = {}  # {page_id_datestr: timestamp}
_reminder_counter = 0
REMINDER_CHECK_INTERVAL = 60  # 每60轮检查一次（约30秒）


def send_to_openclaw(text, emotion_hint=""):
    """发送消息到 OpenClaw，返回回复文本"""
    headers = {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "Content-Type": "application/json",
    }
    system_msg = "请用简短口语化的中文回复，不要用 markdown 或 emoji。"
    if emotion_hint:
        system_msg += f"\n\n[情绪提示] {emotion_hint}"
    payload = {
        "model": "openclaw:main",
        "user": SESSION_USER,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": text},
        ],
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

                        # 0. 学习用户偏好
                        learn_preference(text)

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

                        # 3. 走 OpenClaw 对话（带情绪感知）
                        emotion, hint = detect_emotion(text)
                        if emotion != "normal":
                            print(f"[Bridge] 检测到情绪: {emotion}")
                        reply = send_to_openclaw(text, hint)
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
