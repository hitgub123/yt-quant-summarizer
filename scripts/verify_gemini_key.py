#!/usr/bin/env python3
import os
import requests
import json

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    with open(".env") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                api_key = line.strip().split("=", 1)[1].strip("\"'")

print(f"🔑 正在测试 Gemini API Key: {api_key[:10]}...{api_key[-5:]}")

# 1. 测试基础文本生成 API
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
headers = {"Content-Type": "application/json"}
payload = {
    "contents": [{
        "parts": [{"text": "你好！请回复一句：Gemini API 连接成功！"}]
    }]
}

try:
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    print(f"📡 基础 API 响应状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        reply = data["candidates"][0]["content"]["parts"][0]["text"]
        print(f"🎉 【Gemini 基础连接成功】回复: {reply.strip()}")
    else:
        print(f"❌ 响应错误 ({resp.status_code}): {resp.text}")
except Exception as e:
    print(f"❌ 请求异常: {e}")

# 2. 测试 YouTube 视频原生解析能力
print("\n🎬 正在测试 Gemini 2.0 原生解析 YouTube 视频 (ARK Invest TSLA)...")
video_url = "https://www.youtube.com/watch?v=hoi59k5zh1A"
yt_payload = {
    "contents": [{
        "parts": [
            {
                "file_data": {
                    "file_uri": video_url,
                    "mime_type": "video/*"
                }
            },
            {
                "text": "请用一句话总结这个视频的核心投资观点："
            }
        ]
    }]
}

try:
    resp2 = requests.post(url, headers=headers, json=yt_payload, timeout=30)
    print(f"📡 YouTube 多模态 API 响应状态码: {resp2.status_code}")
    if resp2.status_code == 200:
        data2 = resp2.json()
        reply2 = data2["candidates"][0]["content"]["parts"][0]["text"]
        print(f"🎉 【YouTube 视频原生解析成功】回复:\n{reply2.strip()}")
    else:
        print(f"⚠️ YouTube 视频响应 ({resp2.status_code}): {resp2.text}")
except Exception as e:
    print(f"❌ 视频解析请求异常: {e}")
