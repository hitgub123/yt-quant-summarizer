import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import json
import time

channels = [
    ("AlgorithmTradingIn", "https://www.youtube.com/@AlgorithmTradingIn/videos"),
    ("AndreiJikh", "https://www.youtube.com/@AndreiJikh/videos"),
    ("ARKInvest2015", "https://www.youtube.com/@ARKInvest2015/videos"),
    ("MrBoKong", "https://www.youtube.com/@MrBoKong/videos"),
    ("DataTraders", "https://www.youtube.com/@DataTraders/videos"),
    ("EverythingMoney", "https://www.youtube.com/@EverythingMoney/videos"),
    ("ramitsethi", "https://www.youtube.com/@ramitsethi/videos"),
    ("JosephCarlsonShow", "https://www.youtube.com/@JosephCarlsonShow/videos"),
    ("Live.Traders", "https://www.youtube.com/@Live.Traders/videos"),
    ("tradingwithrayner", "https://www.youtube.com/@tradingwithrayner/videos"),
    ("TheStockMarket", "https://www.youtube.com/@TheStockMarket/videos"),
    ("TraderTVLive", "https://www.youtube.com/@TraderTVLive/videos"),
    ("YueChen-x8n9s", "https://www.youtube.com/@YueChen-x8n9s/videos"),
    ("MeiTouJun", "https://www.youtube.com/@MeiTouJun/videos"),
]

ydl_opts = {
    "extract_flat": True,
    "skip_download": True,
    "quiet": True,
    "playlistend": 1,
}

api = YouTubeTranscriptApi()
results = []

print("🚀 开始对 14 个博主进行真实字幕抓取实测...\n")

for name, url in channels:
    video_id = None
    title = ""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", [])
            if entries and len(entries) > 0:
                video_id = entries[0].get("id")
                title = entries[0].get("title", "")
    except Exception as e:
        results.append((name, "None", f"频道解析失败: {e}", "❌ 失败"))
        continue

    if not video_id:
        results.append((name, "None", "无有效视频", "❌ 失败"))
        continue

    # 测试提取字幕
    try:
        tl = api.list(video_id)
        langs = [t.language_code for t in tl]
        
        # 尝试真实 fetch
        fetched = False
        sample_text = ""
        for t in tl:
            try:
                data = t.fetch()
                sample_text = data.snippets[0].text if hasattr(data, "snippets") and data.snippets else str(data)[:60]
                fetched = True
                break
            except Exception as fe:
                sample_text = f"Fetch Error: {fe}"
        
        if fetched:
            results.append((name, video_id, f"成功 ({langs}): {sample_text[:40]}...", "✅ 稳定可用"))
        else:
            results.append((name, video_id, f"有字幕轨但拉取受阻: {sample_text[:50]}", "⚠️ 需代理/受限"))
            
    except Exception as ex:
        err_msg = str(ex).split("\n")[0]
        results.append((name, video_id, f"无字幕或拦截: {err_msg[:50]}", "❌ 无字幕/受限"))
    
    time.sleep(1.0)

print("\n" + "="*85)
print(f"{'Channel Name':<22} | {'Video ID':<12} | {'Status':<14} | {'Details'}")
print("="*85)
for r in results:
    print(f"{r[0]:<22} | {r[1]:<12} | {r[3]:<14} | {r[2]}")
print("="*85)
