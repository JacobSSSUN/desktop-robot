"""字体加载工具"""
import pygame

FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

_cache = {}

def get_font(size, bold=False):
    key = (size, bold)
    if key not in _cache:
        path = FONT_BOLD if bold else FONT_PATH
        _cache[key] = pygame.font.Font(path, size)
    return _cache[key]
