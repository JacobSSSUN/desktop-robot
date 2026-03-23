#!/bin/bash
# 机器人启动器 — 从桌面双击运行
cd /home/jacob/robot
export PATH="/home/jacob/.local/bin:$PATH"

LAUNCH_LOG="/tmp/robot_launcher.log"
echo "[$(date)] === launcher 开始 ===" > "$LAUNCH_LOG"

# 检查是否已在运行
if pgrep -f "python3.*main.py" > /dev/null 2>&1; then
    echo "[$(date)] 检测到已有进程，退出" >> "$LAUNCH_LOG"
    notify-send "🦐 机器人" "已经在运行了" 2>/dev/null
    exit 0
fi
echo "[$(date)] 无残留进程" >> "$LAUNCH_LOG"

# 清理残留
fuser -k /dev/media0 /dev/media1 2>/dev/null
pkill -f "chat_bridge.py" 2>/dev/null
pkill -f "ncm_player.py" 2>/dev/null
echo "[$(date)] 清理残留完成" >> "$LAUNCH_LOG"
sleep 2
echo "[$(date)] sleep 结束" >> "$LAUNCH_LOG"

# 音量
amixer -c 2 sset 'PCM' 100% >/dev/null 2>&1
amixer -c 2 sset 'Mic' 100% >/dev/null 2>&1

# 清理对话文件
rm -f chat_in.txt chat_out.txt


# 启动 chat_bridge
python3 chat_bridge.py > /tmp/chat_bridge.log 2>&1 &
echo "[$(date)] chat_bridge 启动" >> "$LAUNCH_LOG"

# 启动主程序
export DISPLAY=:0
export SDL_VIDEODRIVER=wayland
export PYTHONUNBUFFERED=1
export PATH="/home/jacob/.local/bin:$PATH"
echo "[$(date)] 准备启动 main.py" >> "$LAUNCH_LOG"
python3 -u main.py >> /tmp/robot_main.log 2>&1 &
MAIN_PID=$!
echo "[$(date)] main.py PID=$MAIN_PID" >> "$LAUNCH_LOG"

notify-send "🦐 机器人" "启动中..." 2>/dev/null
echo "机器人已启动"

# 等几秒确认进程没立刻挂掉
sleep 3
if kill -0 $MAIN_PID 2>/dev/null; then
    echo "[$(date)] 确认运行中 (PID=$MAIN_PID)" >> "$LAUNCH_LOG"
else
    echo "[$(date)] ⚠️ main.py 已退出!" >> "$LAUNCH_LOG"
fi
