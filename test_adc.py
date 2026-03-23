#!/usr/bin/env python3
"""MCP3008 三通道测试 - 电位器(AIN0) + 摇杆(AIN1, AIN2, SW)"""
import spidev
import time

spi = spidev.SpiDev()
spi.open(10, 0)  # spidev10.0 = CE0
spi.max_speed_hz = 1350000

def read_adc(channel):
    """读取 MCP3008 指定通道 (0-7)，返回 0-1023"""
    r = spi.xfer2([1, (8 + channel) << 4, 0])
    return ((r[1] & 3) << 8) + r[2]

print("读取中... Ctrl+C 退出")
print(f"{'电位器(0)':>10} {'摇杆X(1)':>10} {'摇杆Y(2)':>10} {'摇杆按键(3)':>12}")
try:
    while True:
        pot = read_adc(0)
        joy_x = read_adc(1)
        joy_y = read_adc(2)
        sw_raw = read_adc(3)
        sw = 1 if sw_raw < 512 else 0  # 按下拉低
        print(f"{pot:>10} {joy_x:>10} {joy_y:>10} {sw:>8} ({sw_raw})", end="\r")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\n退出")
    spi.close()
