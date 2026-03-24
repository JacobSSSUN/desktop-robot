"""
briefing.py — 每日早报自动播报模块
PIR 检测到人 + 早上时段 → 播报问候 + 天气
"""
import os
import json
import time
import subprocess
from datetime import datetime

BRIEFING_STATE = os.path.join(os.path.dirname(__file__), "briefing_state.json")


def _load_state():
    if os.path.exists(BRIEFING_STATE):
        with open(BRIEFING_STATE, "r") as f:
            return json.load(f)
    return {"last_date": ""}


def _save_state(state):
    with open(BRIEFING_STATE, "w") as f:
        json.dump(state, f)


def should_brief():
    """判断是否需要播报：6:00-11:00 且今天还没播报过"""
    now = datetime.now()
    if now.hour < 6 or now.hour >= 11:
        return False
    state = _load_state()
    today = now.strftime("%Y-%m-%d")
    return state.get("last_date") != today


def mark_done():
    """标记今日已播报"""
    _save_state({"last_date": datetime.now().strftime("%Y-%m-%d")})


def get_greeting():
    """生成问候语"""
    now = datetime.now()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    date_str = f"{now.month}月{now.day}号{weekdays[now.weekday()]}"
    greetings = [
        f"早上好！今天是{date_str}。",
        f"早安！{date_str}，新的一天开始了。",
        f"早上好呀！今天{date_str}。",
    ]
    # 按日期选一个，保持每天不一样
    return greetings[now.day % len(greetings)]


def get_weather():
    """获取天气播报文本，返回 (text, success)"""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "8", "--noproxy", "*",
             "wttr.in/Shenzhen?format=%C|%t|%f|%h|%w&lang=zh"],
            capture_output=True, text=True, timeout=12
        )
        if result.returncode != 0 or not result.stdout.strip():
            return "天气信息获取失败", False

        parts = result.stdout.strip().split("|")
        if len(parts) < 5:
            return "天气数据格式异常", False

        desc = parts[0].strip()
        temp = parts[1].strip()       # 当前温度
        feels = parts[2].strip()      # 体感温度
        humidity = parts[3].strip()   # 湿度
        wind = parts[4].strip()       # 风力

        # 清理温度（去掉 + 号）
        temp = temp.replace("+", "").replace("°C", "度")
        feels = feels.replace("+", "").replace("°C", "度")
        # 清理风向符号（TTS 念不出来）
        wind = wind.replace("↑", "北").replace("↓", "南").replace("←", "西").replace("→", "东")
        wind = wind.replace("↗", "东北").replace("↘", "东南").replace("↙", "西南").replace("↖", "西北")
        # km/h → 公里每小时，前面加"风"
        wind = wind.replace("km/h", "公里每小时")
        # 如果风向以方向开头且后面跟数字，加"风"字
        import re
        wind = re.sub(r'^(北|南|东|西|东北|东南|西南|西北)(\d)', r'\1风\2', wind)

        text = f"深圳今天{desc}，气温{temp}，体感{feels}，湿度{humidity}，{wind}。"
        return text, True

    except Exception as e:
        print(f"[Briefing] 天气获取异常: {e}")
        return "天气信息获取失败", False


def compose():
    """拼成完整的播报文本"""
    greeting = get_greeting()
    weather_text, weather_ok = get_weather()

    parts = [greeting]
    if weather_ok:
        parts.append(weather_text)
    else:
        parts.append("天气暂时获取不到，出门记得看看窗外哦。")

    return " ".join(parts)
