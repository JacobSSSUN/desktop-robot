"""
servo.py — PCA9685 舵机控制 + 人脸跟踪
Channel 0 = 水平舵机 (pan)
Channel 1 = 垂直舵机 (tilt)
用直接 I2C 写入代替 adafruit 库的 duty_cycle（有 bug）
"""
import board
import busio
import adafruit_pca9685
import threading
import time

# PCA9685 寄存器
PCA9685_ADDR = 0x40
LED0_ON_L  = 0x06


class ServoController:
    def __init__(self, pan_channel=0, tilt_channel=1):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        pca = adafruit_pca9685.PCA9685(self.i2c)
        pca.frequency = 50
        # 不再用 pca.channels，直接写 I2C
        self.pan_ch = pan_channel
        self.tilt_ch = tilt_channel

        # 舵机参数 (微秒)
        self.min_pulse = 500
        self.max_pulse = 2500

        # 当前角度
        self.pan_angle = 90
        self.tilt_angle = 90

        # 角度限制
        self.pan_min = 20
        self.pan_max = 160
        self.tilt_min = 30
        self.tilt_max = 150

        # PID 参数
        self.kp_pan = 0.015     # 更灵敏
        self.kp_tilt = 0.012
        self.dead_zone = 0.06   # 小死区
        self.settle_time = 0.15 # 等画面稳定

        # 跟踪状态
        self.lock = threading.Lock()
        self.running = False
        self.tracking_enabled = False  # 跟随摄像头开关
        self._thread = None

        self.face_offset_x = 0.0
        self.face_offset_y = 0.0
        self.face_detected = False
        self.last_face_time = 0

        self.CENTER_TIMEOUT = 5.0

    def _set_pwm(self, ch, value):
        """直接 I2C 写入 PCA9685 PWM 值 (0~4095)"""
        # value 对应 0~4095 的 12-bit duty
        # pulse_us = 500 + (value / 4095) * 2000
        # 但我们直接用 12-bit 值
        base = LED0_ON_L + ch * 4
        buf = bytes([base, 0x00, 0x00, value & 0xFF, (value >> 8) & 0x0F])
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.writeto(PCA9685_ADDR, buf)
        finally:
            self.i2c.unlock()

    def _angle_to_pwm(self, angle):
        """角度 → PCA9685 12-bit 值"""
        pulse = self.min_pulse + (angle / 180.0) * (self.max_pulse - self.min_pulse)
        return int(pulse / 20000.0 * 4096)

    def _set_servo(self, ch, angle):
        angle = max(0, min(180, angle))
        pwm = self._angle_to_pwm(angle)
        self._set_pwm(ch, pwm)

    def set_pan(self, angle):
        with self.lock:
            self.pan_angle = max(self.pan_min, min(self.pan_max, angle))
            self._set_servo(self.pan_ch, self.pan_angle)

    def set_tilt(self, angle):
        with self.lock:
            self.tilt_angle = max(self.tilt_min, min(self.tilt_max, angle))
            self._set_servo(self.tilt_ch, self.tilt_angle)

    def center(self):
        self.set_pan(90)
        self.set_tilt(90)
        print("[Servo] 回中")

    def update_face_position(self, offset_x, offset_y, detected=True):
        with self.lock:
            self.face_offset_x = offset_x
            self.face_offset_y = offset_y
            self.face_detected = detected
            if detected:
                self.last_face_time = time.time()

    def start(self):
        self.running = True
        self.center()
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        print("[Servo] 舵机启动，开始跟踪")

    def stop(self):
        if not self.running:
            return
        self.running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._set_pwm(self.pan_ch, 0)
        self._set_pwm(self.tilt_ch, 0)
        print("[Servo] 舵机停止")

    def _tracking_loop(self):
        last_debug = 0
        while self.running:
            time.sleep(0.02)  # 50Hz 更新

            if not self.tracking_enabled:
                continue

            now = time.time()

            with self.lock:
                ox = self.face_offset_x
                oy = self.face_offset_y
                detected = self.face_detected

            if detected and (abs(ox) > self.dead_zone or abs(oy) > self.dead_zone):
                # 目标角度：偏移越大，目标越极端
                target_pan = 90 + ox * 50   # offset ±1 → 目标 40~140
                target_tilt = 90 + oy * 40  # offset ±1 → 目标 50~130
                target_pan = max(self.pan_min, min(self.pan_max, target_pan))
                target_tilt = max(self.tilt_min, min(self.tilt_max, target_tilt))

                with self.lock:
                    # 平滑插值：每帧向目标移动 8%
                    smooth = 0.08
                    new_pan = self.pan_angle + (target_pan - self.pan_angle) * smooth
                    new_tilt = self.tilt_angle + (target_tilt - self.tilt_angle) * smooth
                    self.pan_angle = new_pan
                    self.tilt_angle = new_tilt

                self._set_servo(self.pan_ch, new_pan)
                self._set_servo(self.tilt_ch, new_tilt)

                if now - last_debug > 2:
                    print(f"[Track] offset=({ox:.2f},{oy:.2f}) servo=({new_pan:.0f},{new_tilt:.0f})")
                    last_debug = now

            elif not detected and (now - self.last_face_time) > self.CENTER_TIMEOUT:
                # 回中：平滑回到 90°
                with self.lock:
                    smooth = 0.02  # 回中更慢更柔
                    new_pan = self.pan_angle + (90 - self.pan_angle) * smooth
                    new_tilt = self.tilt_angle + (90 - self.tilt_angle) * smooth
                    self.pan_angle = new_pan
                    self.tilt_angle = new_tilt

                self._set_servo(self.pan_ch, new_pan)
                self._set_servo(self.tilt_ch, new_tilt)
