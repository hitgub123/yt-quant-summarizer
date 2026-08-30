#!/usr/bin/env python3
import sys
import time
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

TEST_TARGETS = [
    ("Algorithm Trading", "dURysZ2lCLY", "https://www.youtube.com/watch?v=dURysZ2lCLY"),
    ("Andrei Jikh", "Uw84lTiD5C8", "https://www.youtube.com/watch?v=Uw84lTiD5C8"),
    ("ARK Invest", "hoi59k5zh1A", "https://www.youtube.com/watch?v=hoi59k5zh1A"),
    ("MrBoKong", "09V8vB5nC1U", "https://www.youtube.com/watch?v=09V8vB5nC1U"),
    ("DataTraders", "uVqO_J1GjR8", "https://www.youtube.com/watch?v=uVqO_J1GjR8"),
    ("EverythingMoney", "U395oTkpXsE", "https://www.youtube.com/watch?v=U395oTkpXsE"),
    ("Ramit Sethi", "N_aN94m9y5g", "https://www.youtube.com/watch?v=N_aN94m9y5g"),
    ("Joseph Carlson", "6O_4w72-h1k", "https://www.youtube.com/watch?v=6O_4w72-h1k"),
    ("Live Traders", "P77_qX84q9E", "https://www.youtube.com/watch?v=P77_qX84q9E"),
    ("Trading with Rayner", "F0b9F9dJ7c0", "https://www.youtube.com/watch?v=F0b9F9dJ7c0"),
    ("TraderTV Live", "V5w8_L3gK0Y", "https://www.youtube.com/watch?v=V5w8_L3gK0Y"),
    ("Yue Chen", "9DUpG4QbqhY", "https://www.youtube.com/watch?v=9DUpG4QbqhY"),
    ("美投君", "xEkNd6xG1qo", "https://www.youtube.com/watch?v=xEkNd6xG1qo"),
]

api = YouTubeTranscriptApi()
results = []

print("=" * 80, flush=True)
print("🚀 正在对 13 个主流频道视频进行真实字幕抓取实测...", flush=True)
print("=" * 80, flush=True)

for name, vid, url in TEST_TARGETS:
    print(f"🔍 测试 [{name}] (ID: {vid})...", end=" ", flush=True)
    status = "❌ 失败"
    details = ""
    
    try:
        # 1. 尝试 YouTubeTranscriptApi
        tl = api.list(vid)
        langs = [t.language_code for t in tl]
        
        # 尝试拉取第一个字幕轨
        fetched_text = ""
        for t in tl:
            try:
                data = t.fetch()
                if hasattr(data, "snippets") and data.snippets:
                    fetched_text = data.snippets[0].text
                elif isinstance(data, list) and len(data) > 0:
                    fetched_text = data[0].get("text", "")
                break
            except Exception as fe:
                fetched_text = f"Fetch fail: {fe}"
                
        if fetched_text and not fetched_text.startswith("Fetch fail"):
            status = "✅ 稳定可用"
            details = f"语言: {langs} | 预览: {fetched_text[:35]}..."
        else:
            status = "⚠️ 需授权/受限"
            details = f"存在字幕轨 {langs}，但下载受限: {fetched_text[:35]}"
            
    except Exception as e:
        err = str(e).split("\n")[0]
        if "NoTranscriptFound" in err:
            status = "❌ 无公开字幕"
            details = "YouTube 未为此视频生成或提供公开字幕"
        elif "IpBlocked" in err or "RequestBlocked" in err or "429" in err:
            status = "❌ IP 限流 (429)"
            details = "Google 限制了该 IP 的 timedtext 字幕请求"
        elif "VideoUnavailable" in err:
            status = "❌ 视频不可用"
            details = "视频可能已下架或需要特定区域权限"
        else:
            status = "❌ 异常"
            details = f"{err[:45]}"
            
    print(f"[{status}] -> {details}", flush=True)
    results.append((name, vid, status, details))
    time.sleep(1.0)

print("\n" + "=" * 90, flush=True)
print(f"{'频道名称':<20} | {'视频 ID':<12} | {'字幕获取状态':<15} | {'实测详情'}", flush=True)
print("=" * 90, flush=True)
for r in results:
    print(f"{r[0]:<20} | {r[1]:<12} | {r[2]:<15} | {r[3]}", flush=True)
print("=" * 90, flush=True)
