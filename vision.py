"""
vision.py — 摄像头 + 人脸检测
后台线程持续采集，主线程读取最新结果
"""
import cv2
import numpy as np
from picamera2 import Picamera2
import threading
import time
from config import CAMERA_WIDTH, CAMERA_HEIGHT


class Vision:
    def __init__(self):
        self.cam = Picamera2()
        config = self.cam.create_video_configuration(
            main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"}
        )
        self.cam.configure(config)

        # 加载人脸检测器
        import os
        cascade_path = os.path.join(os.path.dirname(__file__), "haarcascade_frontalface_default.xml")
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        self.faces = []  # [(x, y, w, h), ...]
        self.frame = None  # 最新帧
        self.lock = threading.Lock()
        self.running = False
        self.detect_enabled = False  # 默认关闭人脸检测
        self._thread = None

    def start(self):
        self.cam.start()
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Vision] 摄像头启动")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.cam.stop()
        print("[Vision] 摄像头停止")

    def get_faces(self):
        with self.lock:
            return list(self.faces)

    def get_frame(self):
        with self.lock:
            return self.frame

    def toggle_detection(self):
        self.detect_enabled = not self.detect_enabled
        state = "开启" if self.detect_enabled else "关闭"
        print(f"[Vision] 人脸检测 {state}")
        return self.detect_enabled

    def _loop(self):
        while self.running:
            try:
                frame = self.cam.capture_array()
                with self.lock:
                    self.frame = frame
                if self.detect_enabled:
                    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                    detected = self.face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=3, minSize=(40, 40)
                    )
                    with self.lock:
                        self.faces = [tuple(f) for f in detected]
                else:
                    with self.lock:
                        self.faces = []
            except Exception as e:
                print(f"[Vision] 采集错误: {e}")
            time.sleep(0.1)  # ~10fps 检测
