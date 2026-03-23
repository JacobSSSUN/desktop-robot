"""
touch.py — 从底层 /dev/input 读取触屏事件
绕过 Pygame 的 Xwayland 触屏兼容问题
"""
import struct
import threading
import os

# event 结构：time_sec, time_usec, type, code, value
EVENT_FORMAT = 'llHHi'
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

# 事件类型
EV_ABS = 3
EV_SYN = 0

# 绝对位置代码
ABS_X = 0
ABS_Y = 1
ABS_MT_SLOT = 47
ABS_MT_TRACKING_ID = 57


class TouchReader:
    def __init__(self, device_path="/dev/input/event5", width=1024, height=600):
        self.device_path = device_path
        self.width = width
        self.height = height

        self.x = 0
        self.y = 0
        self.touching = False
        self.lock = threading.Lock()
        self.running = False
        self._thread = None

        # 校准参数（从 sysfs 读取范围）
        self.x_min = 0
        self.x_max = 0
        self.y_min = 0
        self.y_max = 0
        self._read_calibration()

    def _read_calibration(self):
        dev = "/sys/class/input/event5/device"
        try:
            # 读取 ABS_X 范围
            x_range = open(f"{dev}/abs/0x00").read().strip().split()  # ABS_X
            self.x_min, self.x_max = int(x_range[0]), int(x_range[1])
            # 读取 ABS_Y 范围
            y_range = open(f"{dev}/abs/0x01").read().strip().split()  # ABS_Y
            self.y_min, self.y_max = int(y_range[0]), int(y_range[1])
            print(f"[Touch] 校准: X={self.x_min}-{self.x_max}, Y={self.y_min}-{self.y_max}")
        except Exception as e:
            # 使用默认值
            self.x_min, self.x_max = 0, 4095
            self.y_min, self.y_max = 0, 4095
            print(f"[Touch] 使用默认校准: {e}")

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Touch] 触屏监听启动")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)

    def get_pos(self):
        """返回 (x, y, touching)"""
        with self.lock:
            return self.x, self.y, self.touching

    def _loop(self):
        raw_x = 0
        raw_y = 0
        tracking_id = -1

        try:
            fd = os.open(self.device_path, os.O_RDONLY | os.O_NONBLOCK)
        except Exception as e:
            print(f"[Touch] 无法打开设备: {e}")
            return

        while self.running:
            try:
                data = os.read(fd, EVENT_SIZE)
                if len(data) < EVENT_SIZE:
                    continue
                _, _, etype, code, value = struct.unpack(EVENT_FORMAT, data)

                if etype == EV_ABS:
                    if code == ABS_X:
                        raw_x = value
                    elif code == ABS_Y:
                        raw_y = value
                    elif code == ABS_MT_TRACKING_ID:
                        tracking_id = value
                elif etype == EV_SYN:
                    with self.lock:
                        # 映射到屏幕坐标
                        dx = self.x_max - self.x_min
                        dy = self.y_max - self.y_min
                        if dx > 0:
                            self.x = int((raw_x - self.x_min) / dx * self.width)
                        if dy > 0:
                            self.y = int((raw_y - self.y_min) / dy * self.height)
                        self.touching = tracking_id != -1

            except BlockingIOError:
                import time
                time.sleep(0.001)
            except Exception as e:
                if self.running:
                    print(f"[Touch] 读取错误: {e}")
                break

        os.close(fd)
        print("[Touch] 触屏监听停止")
