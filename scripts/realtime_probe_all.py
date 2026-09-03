#!/usr/bin/env python3
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from summarizer.channel_catalog import QUANT_CHANNELS

channels = QUANT_CHANNELS

api = YouTubeTranscriptApi()
ydl_opts = {"extract_flat": True, "skip_download": True, "quiet": True, "playlistend": 1}

print("=" * 90, flush=True)
print("🚀 正在探测 13 个频道的最新真实视频并验证字幕可用性...", flush=True)
print("=" * 90, flush=True)

results = []

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    for name, ch_url in channels:
        try:
            info = ydl.extract_info(ch_url, download=False)
            entries = [e for e in info.get("entries", []) if e]
            if not entries:
                results.append((name, "-", "❌ 无视频", "无法获取频道视频列表"))
                continue
            
            top_v = entries[0]
            vid = top_v.get("id")
            v_title = top_v.get("title", "")
            
            # 探测字幕
            try:
                tl = api.list(vid)
                langs = [t.language_code for t in tl]
                # 尝试抓取首句
                fetched_txt = ""
                for t in tl:
                    try:
                        d = t.fetch()
                        if hasattr(d, "snippets") and d.snippets:
                            fetched_txt = d.snippets[0].text
                        elif isinstance(d, list) and d:
                            fetched_txt = d[0].get("text", "")
                        break
                    except Exception as fe:
                        fetched_txt = f"Fetch fail: {fe}"
                
                if fetched_txt and not fetched_txt.startswith("Fetch fail"):
                    status = "✅ 稳定可用"
                    desc = f"语言: {langs} | 预览: {fetched_txt[:30]}..."
                else:
                    status = "⚠️ 存在字幕但受限"
                    desc = f"语言: {langs} | 原因: {fetched_txt[:35]}"
            except Exception as se:
                se_str = str(se).split("\n")[0]
                if "TranscriptsDisabled" in se_str:
                    status = "❌ 博主关闭字幕"
                    desc = "博主未提供字幕且未开启自动字幕"
                elif "NoTranscriptFound" in se_str:
                    status = "❌ 无可用字幕"
                    desc = "YouTube 未为此视频生成字幕"
                elif "IpBlocked" in se_str or "429" in se_str:
                    status = "❌ 429 限制"
                    desc = "接口被暂时频控"
                else:
                    status = "❌ 异常"
                    desc = se_str[:40]
                    
            results.append((name, vid, status, desc))
            print(f"[{name}] ID: {vid} -> {status} ({desc})", flush=True)
            
        except Exception as e:
            results.append((name, "-", "❌ 错误", str(e)[:35]))
            print(f"[{name}] 处理异常: {e}", flush=True)
            
        time.sleep(1.0)

print("\n" + "=" * 95, flush=True)
print(f"{'频道名称':<22} | {'最新视频 ID':<12} | {'字幕状态':<15} | {'实测详情'}", flush=True)
print("=" * 95, flush=True)
for r in results:
    print(f"{r[0]:<22} | {r[1]:<12} | {r[2]:<15} | {r[3]}", flush=True)
print("=" * 95, flush=True)
