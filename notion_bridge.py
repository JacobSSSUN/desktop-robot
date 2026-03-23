#!/usr/bin/env python3
"""
notion_bridge.py — Notion 笔记桥接
识别记录意图 → 写入莓虾笔记数据库
"""
import json
import requests
from datetime import datetime

# Notion 配置
import os
_secrets_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".openclaw", "workspace", "secrets", "notion.json")
with open(_secrets_path) as _f:
    _secrets = json.load(_f)
NOTION_TOKEN = _secrets["token"]
DATABASE_ID = _secrets["database_id"]
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# 记录关键词
RECORD_KEYWORDS = [
    "记一下", "记住", "记下来", "帮我记", "写下来", "记到笔记",
    "记着", "别忘了", "备忘", "写到", "记个", "记一笔",
    "学到了", "发现了", "总结一下",
]

# 标签关键词映射
TAG_RULES = {
    "待办": ["要", "需要", "明天", "计划", "记得", "别忘了", "待办", "做一下", "完成", "买", "去", "约"],
    "灵感": ["好主意", "想法", "灵感", "突然想到", "想到", "可以试试", "脑洞", "试试"],
    "学习": ["学到了", "原来", "笔记", "知识点", "记住", "复习", "概念", "发现", "总结"],
    "资料": ["密码", "账号", "地址", "号码", "电话", "邮箱", "链接", "url", "ip"],
    "生活": ["吃了", "去了", "今天", "昨天", "感觉", "心情"],
}


def detect_record_intent(text):
    """
    检测是否是记录意图。
    返回 (is_record, content, tag)
    - is_record: True/False
    - content: 去掉触发词后的内容
    - tag: 自动判断的标签
    """
    text_lower = text.lower().strip()

    for kw in RECORD_KEYWORDS:
        if kw in text_lower:
            # 提取内容：去掉触发词
            content = text
            idx = text.find(kw)
            if idx >= 0:
                content = text[idx + len(kw):].strip().lstrip("，,：:、.。").strip()

            if not content:
                content = text  # 如果提取后为空，用原文

            # 自动判断标签
            tag = detect_tag(content)
            return True, content, tag

    # 没有显式关键词，检查是否像"想法/灵感"类开头（保守匹配）
    thought_starters = ["突然想到", "想到一个", "有个想法", "有一个想法"]
    for starter in thought_starters:
        if text_lower.startswith(starter):
            return True, text, "灵感"

    return False, text, None


def detect_tag(text):
    """根据关键词自动判断标签"""
    text_lower = text.lower()
    for tag, keywords in TAG_RULES.items():
        for kw in keywords:
            if kw in text_lower:
                return tag
    return "想法"  # 默认


def write_to_notion(title, content, tag="想法"):
    """写入一条笔记到 Notion 莓虾笔记数据库"""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }

    # 标题取前20个字
    title_text = title[:20] if len(title) > 20 else title

    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "标题": {"title": [{"text": {"content": title_text}}]},
            "内容": {"rich_text": [{"text": {"content": content}}]},
            "标签": {"select": {"name": tag}},
            "来源": {"select": {"name": "机器人"}},
            "日期": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
        }
    }

    try:
        resp = requests.post(f"{NOTION_API}/pages", headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("object") == "page":
            return True
        else:
            print(f"[Notion] 意外响应: {result}")
            return False
    except Exception as e:
        print(f"[Notion] 写入失败: {e}")
        return False
