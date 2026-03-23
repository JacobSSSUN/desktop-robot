#!/bin/bash
cd /home/jacob/robot
rm -f chat_in.txt chat_out.txt
amixer -c 2 sset 'PCM' 100% >/dev/null 2>&1
amixer -c 2 sset 'Mic' 100% >/dev/null 2>&1
nohup python3 chat_bridge.py > /tmp/chat_bridge.log 2>&1 &
echo "Chat bridge PID: $!"
nohup python3 -u main.py > /tmp/robot_main.log 2>&1 &
echo "Main PID: $!"
sleep 2
echo "Running processes:"
pgrep -af "main\.py|chat_bridge" | grep -v grep
