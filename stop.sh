#!/bin/bash
# 关闭机器人
echo "正在关闭机器人..."
pkill -f "python3 main.py" 2>/dev/null
pkill -f "chat_bridge.py" 2>/dev/null
fuser -k /dev/media0 /dev/media1 2>/dev/null
rm -f chat_in.txt chat_out.txt
sleep 1
echo "机器人已关闭"
