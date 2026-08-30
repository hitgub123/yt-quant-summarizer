import yt_dlp
import os
import time

url = "https://www.youtube.com/watch?v=hoi59k5zh1A"
out_audio = "/tmp/test_audio.m4a"
if os.path.exists(out_audio):
    os.remove(out_audio)

ydl_opts = {
    "format": "ba[ext=m4a]/ba/b",
    "outtmpl": out_audio,
    "quiet": False,
    "no_warnings": False,
}

print("🚀 测试下载极轻量音频流 (Google Video CDN)...")
try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"🎉 成功下载音频！大小: {os.path.getsize(out_audio) / 1024 / 1024:.2f} MB，完全不受 429 影响！")
except Exception as e:
    print("❌ 异常:", e)
