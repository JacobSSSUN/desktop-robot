#!/usr/bin/env python3
"""
ha_bridge.py — 语音控制 HA 桥接
用 LLM 解析语音指令 → 调用 HA service API
"""
import json
import requests
import re

HA_URL = "http://localhost:8123"
HA_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJiYjRiMWJlNTYwNDI0NGFiOGJjODZhMjNiOTU3N2NlMyIsImlhdCI6MTc3MzkyNTI4MSwiZXhwIjoyMDg5Mjg1MjgxfQ.mLNB24C8iRm33L5WvwIRi14dyS404gLxGizXMcwyv1k"
GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"
GATEWAY_TOKEN = "43043f2491fe85f41e1c6e78c7727f7afa9a30c3fb9056c2"

HEADERS_HA = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

# 所有已知设备（从 TOOLS.md 同步）
DEVICES = """
### 灯
- light.yeelink_mbulb3_bf71_light = 书房灯1 (书房)
- light.yeelink_mbulb3_0b8e_light = 书房灯2 (书房)
- light.yeelink_mbulb3_2e11_light = 书房灯3 (书房)
- light.yeelink_mbulb3_1d18_light = 书房灯4 (书房)
- light.yeelink_mbulb3_fbdb_light = 客厅灯1 (客厅)
- light.yeelink_mbulb3_8bc2_light = 客厅灯2 (客厅)
- light.yeelink_mbulb3_d656_light = 客厅灯3 (客厅)
- light.yeelink_mbulb3_51a4_light = 客厅灯4 (客厅)
- light.yeelink_mbulb3_bcc0_light = 客厅灯5 (客厅)
- light.yeelink_mbulb3_3690_light = 客厅灯6 (客厅)
- light.yeelink_mbulb3_0ba7_light = 卧室灯1 (卧室)
- light.yeelink_mbulb3_e65e_light = 卧室灯2 (卧室)
- light.yeelink_mbulb3_de72_light = 卧室灯3 (卧室)
- light.yeelink_mbulb3_fbe5_light = 卧室灯4 (卧室)
- light.yeelink_mbulb3_3350_light = 餐桌灯 (餐厅)
- light.yeelink_lamp4_f8fe_light = 台灯
- light.mijia_group3_1681_light = 客厅灯组 (客厅)
- light.mijia_group3_7664_light = 书房灯组 (书房)
- light.mijia_group3_1792_light = 卧室灯组 (卧室)

### 空调/暖风机
- climate.lumi_mcn04_78d4_air_conditioner = 卧室空调
- climate.lumi_mcn02_0816_air_conditioner = 书房空调
- climate.xiaomi_ma8_2ba6_heater = 暖风机

### 其他
- vacuum.roborock_a23_8f27_robot_cleaner = 小石头/扫地机
- switch.qmdq88_s1_095c_switch_status = 洗碗机
- switch.chuangmi_m3_3ff1_switch = 除湿机/加湿器
- media_player.xiaomi_mih1_fe90_play_control = 小米电视
- media_player.xiaomi_lx5a_b7d4_play_control = 小爱音箱
- media_player.xiaomi_oh2p_c928_play_control = 智能音箱Pro
"""


# 网易云音乐能力说明
MUSIC_CAPABILITIES = """
### 音乐播放（网易云音乐）
- 播放我喜欢的音乐/播放我喜欢的歌 → {"action": "music_liked", "reply": "好的，播放我喜欢的音乐"}
- 播放音乐/放首歌/来首歌 → {"action": "music_play", "reply": "好的，播放音乐"}
- 播放第N首 → {"action": "music_play", "index": N-1, "reply": "好的，播放第N首"}
- 搜索并播放XXX → {"action": "music_search", "keyword": "XXX", "reply": "好的，播放XXX"}
- 播放/继续播放 → {"action": "music_play", "reply": "好的"}
- 暂停/停止/别放了 → {"action": "music_stop", "reply": "好的，已停止"}
- 下一首/换一首 → {"action": "music_next", "reply": "好的，下一首"}
- 看歌单/有什么歌/歌单 → {"action": "music_list", "reply": "你的歌单有..."}
- 播放XX歌单/切换到XX歌单（XX不是"我喜欢"时） → {"action": "music_switch_playlist", "keyword": "XX", "reply": "好的，切换到XX歌单"}
- 音量调大/音量调小/音量加/音量减 → {"action": "volume", "direction": "up"/"down", "reply": "好的"}
- 音量调到N/音量百分之N → {"action": "volume", "level": N, "reply": "好的，音量调到N%"}
- 静音/取消静音 → {"action": "volume", "direction": "mute"/"unmute", "reply": "好的"}
"""


def ask_llm_for_action(text):
    """让 LLM 解析语音指令，返回 API 调用信息"""
    prompt = f"""你是一个桌面机器人助手，负责解析用户的语音指令。根据用户的指令，判断要执行什么操作。

可用设备列表：
{DEVICES}

{MUSIC_CAPABILITIES}

用户指令："{text}"

请严格按以下 JSON 格式回复（不要其他内容）：

设备控制：
{{"action": "call_service", "domain": "light", "service": "turn_on", "entity_id": "light.xxx", "reply": "好的，已为你开灯"}}

查询状态：
{{"action": "get_state", "entity_id": "light.xxx", "reply": "查询中"}}

音乐播放（见上面的音乐能力列表）

音量控制（见上面的音乐能力列表）

闲聊（与设备/音乐无关的对话）：
{{"action": "chat", "reply": ""}}

设备控制注意：
- 灯：service_data用 turn_on/turn_off，亮度用 brightness_pct
- 空调：domain=climate，service=turn_on/turn_off/set_temperature
- 扫地机：domain=vacuum，service=start/stop/return_to_base
- 多个设备用数组 entity_id
- "所有灯" 用 light.mijia_group3_1681_light, light.mijia_group3_7664_light, light.mijia_group3_1792_light
- 回复要简短口语化，适合语音播报"""

    headers = {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openrouter/xiaomi/mimo-v2-pro",
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        resp = requests.post(GATEWAY_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # 提取 JSON
        match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"[HA] LLM 解析失败: {e}")
    return None


def call_ha_service(domain, service, entity_id, service_data=None):
    """调用 HA service API"""
    data = {"entity_id": entity_id}
    if service_data:
        data.update(service_data)
    url = f"{HA_URL}/api/services/{domain}/{service}"
    try:
        resp = requests.post(url, headers=HEADERS_HA, json=data, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[HA] Service 调用失败: {e}")
        return False


def get_ha_state(entity_id):
    """查询 HA 设备状态"""
    url = f"{HA_URL}/api/states/{entity_id}"
    try:
        resp = requests.get(url, headers=HEADERS_HA, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[HA] 状态查询失败: {e}")
        return None


def handle_voice_command(text):
    """
    处理语音指令。
    返回: (is_device_command: bool, reply: str)
    """
    action = ask_llm_for_action(text)
    if not action:
        return False, ""

    act = action.get("action", "")

    if act == "chat":
        return False, ""

    if act == "call_service":
        domain = action.get("domain", "")
        service = action.get("service", "")
        entity_id = action.get("entity_id", "")
        service_data = action.get("service_data")
        reply = action.get("reply", "")

        # 处理多个 entity_id
        if isinstance(entity_id, list):
            success = True
            for eid in entity_id:
                if not call_ha_service(domain, service, eid, service_data):
                    success = False
        else:
            success = call_ha_service(domain, service, entity_id, service_data)

        if not success:
            reply = "操作失败了，请检查设备是否在线"
        return True, reply

    if act == "get_state":
        entity_id = action.get("entity_id", "")
        state = get_ha_state(entity_id)
        if state:
            s = state.get("state", "未知")
            attrs = state.get("attributes", {})
            friendly = attrs.get("friendly_name", entity_id)
            return True, f"{friendly}当前状态是{s}"
        return True, "查不到这个设备的状态"

    if act in ("music_play", "music_stop", "music_next", "music_search", "music_switch_playlist", "music_liked"):
        # 播放类操作 → 写入 music_request.json，由 music_player widget 统一管理
        import json as _json
        REQUEST_FILE = "/home/jacob/robot/music_request.json"
        req = {}
        if act == "music_liked":
            req = {"action": "play_liked"}
        elif act == "music_play":
            index = action.get("index")
            keyword = action.get("keyword")
            if keyword:
                req = {"action": "play_search", "keyword": keyword}
            elif index is not None:
                req = {"action": "play_index", "index": index}
            else:
                req = {"action": "play_random"}
        elif act == "music_stop":
            req = {"action": "stop"}
        elif act == "music_next":
            req = {"action": "next"}
        elif act == "music_search":
            req = {"action": "play_search", "keyword": action.get("keyword", "")}
        elif act == "music_switch_playlist":
            req = {"action": "switch_playlist", "keyword": action.get("keyword", "")}
        with open(REQUEST_FILE, "w") as f:
            _json.dump(req, f, ensure_ascii=False)
        return True, action.get("reply", "好的")

    if act == "music_list":
        import subprocess
        result = subprocess.run(
            ["python3", "/home/jacob/robot/ncm_player.py", "--playlist"],
            capture_output=True, text=True, timeout=15)
        lines = result.stdout.strip().split("\n")
        if lines:
            # 只返回前几首
            summary = "\n".join(lines[:8])
            if len(lines) > 8:
                summary += f"\n  ... 共 {len(lines)-2} 首"
            return True, summary
        return True, "歌单为空"

    if act == "volume":
        direction = action.get("direction")
        level = action.get("level")
        import subprocess
        if level is not None:
            level = max(0, min(100, int(level)))
            subprocess.run(["amixer", "-c", "2", "sset", "PCM", f"{level}%"],
                            capture_output=True)
            return True, action.get("reply", f"音量调到{level}%")
        elif direction == "up":
            # 获取当前音量并+10
            out = subprocess.check_output(["amixer", "-c", "2", "sget", "PCM"], text=True)
            m = re.search(r"Playback \d+ \[(\d+)%\]", out)
            if m:
                vol = min(100, int(m.group(1)) + 10)
                subprocess.run(["amixer", "-c", "2", "sset", "PCM", f"{vol}%"],
                                capture_output=True)
                return True, f"音量调到{vol}%"
        elif direction == "down":
            out = subprocess.check_output(["amixer", "-c", "2", "sget", "PCM"], text=True)
            m = re.search(r"Playback \d+ \[(\d+)%\]", out)
            if m:
                vol = max(0, int(m.group(1)) - 10)
                subprocess.run(["amixer", "-c", "2", "sset", "PCM", f"{vol}%"],
                                capture_output=True)
                return True, f"音量调到{vol}%"
        elif direction == "mute":
            subprocess.run(["amixer", "-c", "2", "sset", "PCM", "mute"],
                            capture_output=True)
            return True, "已静音"
        elif direction == "unmute":
            subprocess.run(["amixer", "-c", "2", "sset", "PCM", "unmute"],
                            capture_output=True)
            return True, "已取消静音"
        return True, action.get("reply", "好的")

    return False, ""


if __name__ == "__main__":
    # 测试
    tests = ["打开客厅灯", "关闭所有灯", "客厅灯开着吗", "空调调到26度", "你好"]
    for t in tests:
        print(f"\n=== {t} ===")
        is_cmd, reply = handle_voice_command(t)
        print(f"设备指令: {is_cmd}, 回复: {reply}")
