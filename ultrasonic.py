"""
ultrasonic.py — 超声波测距模块 (HC-SR04)
TRIG=GPIO18, ECHO=GPIO17
"""
import time
import threading
from gpiozero import DistanceSensor


class UltrasonicSensor:
    def __init__(self, trigger_pin=18, echo_pin=17):
        self.sensor = DistanceSensor(echo=echo_pin, trigger=trigger_pin, max_distance=2.0)
        self.distance = 1.0  # 米
        self.lock = threading.Lock()
        self.running = False
        self._thread = None

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Ultrasonic] 超声波启动")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.sensor.close()
        print("[Ultrasonic] 超声波停止")

    def get_distance(self):
        with self.lock:
            return self.distance

    def get_zone(self):
        """返回距离区域: very_close / close / medium / far"""
        d = self.get_distance()
        if d < 0.15:
            return "very_close"
        elif d < 0.30:
            return "close"
        elif d < 0.60:
            return "medium"
        else:
            return "far"

    def _loop(self):
        while self.running:
            try:
                d = self.sensor.distance  # gpiozero 返回的是米
                with self.lock:
                    self.distance = d
            except Exception:
                pass
            time.sleep(0.1)
