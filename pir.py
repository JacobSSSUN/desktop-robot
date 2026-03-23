"""
pir.py — PIR 人体感应模块
GPIO21，检测到人输出 HIGH
"""
import time
import threading
from gpiozero import MotionSensor


class PIRSensor:
    def __init__(self, pin=21):
        self.sensor = MotionSensor(pin, threshold=0.5)
        self.detected = False
        self.lock = threading.Lock()
        self.last_motion_time = 0

        # 回调：检测到人
        self.sensor.when_motion = self._on_motion
        self.sensor.when_no_motion = self._on_no_motion
        print(f"[PIR] PIR启动 (GPIO{pin})")

    def _on_motion(self):
        with self.lock:
            self.detected = True
            self.last_motion_time = time.time()

    def _on_no_motion(self):
        with self.lock:
            self.detected = False

    def is_detected(self):
        with self.lock:
            return self.detected

    def seconds_since_motion(self):
        with self.lock:
            if self.last_motion_time == 0:
                return 999
            return time.time() - self.last_motion_time

    def stop(self):
        self.sensor.close()
        print("[PIR] PIR停止")
