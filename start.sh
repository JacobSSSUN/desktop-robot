#!/bin/bash
# 启动机器人
cd /home/jacob/robot

# 清理残留进程
fuser -k /dev/media0 /dev/media1 2>/dev/null
pkill -f "chat_bridge.py" 2>/dev/null
sleep 2

# 音量拉满
amixer -c 2 sset 'PCM' 100% >/dev/null 2>&1
amixer -c 2 sset 'Mic' 100% >/dev/null 2>&1

# 清理对话文件
rm -f chat_in.txt chat_out.txt

# 启动对话桥接
python3 chat_bridge.py > /tmp/chat_bridge.log 2>&1 &
echo "Chat Bridge 已启动 (PID: $!)"

# 启动主程序
export DISPLAY=:0
export SDL_VIDEODRIVER=wayland
export PYTHONUNBUFFERED=1
python3 -u main.py &
echo "机器人已启动 (PID: $!)"
