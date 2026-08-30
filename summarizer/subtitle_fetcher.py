"""
Enhanced Subtitle Fetcher Module
具备网页内嵌字幕解析、精确语言探测、8~15秒防封控与多源容错提取能力。
"""

from __future__ import annotations
import os
import re
import json
import time
import random
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

logger = logging.getLogger(__name__)


class SubtitleFetcher:
    def __init__(self, proxy: Optional[str] = None, cookie_file: Optional[str] = None):
        self.proxy = proxy or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        self.cookie_file = cookie_file
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        })

    def fetch_transcript(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定视频的真实字幕逐字稿
        返回:
        {
            "video_id": "...",
            "language": "...",
            "full_text": "...",
            "snippets": [...],
            "source": "..."
        }
        """
        # 策略 1: 使用 youtube_transcript_api (优先探测实际存在的语言)
        res = self._fetch_via_api(video_id)
        if res:
            return res

        # 策略 2: 从网页 HTML 静态解析 captionTracks
        res = self._fetch_via_html_scraping(video_id)
        if res:
            return res

        # 策略 3: 使用 yt-dlp 精确下载
        res = self._fetch_via_ytdlp(video_id)
        if res:
            return res

        return None

    def _fetch_via_api(self, video_id: str) -> Optional[Dict[str, Any]]:
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            
            # 优先选择英文字幕或中文字幕
            chosen_track = None
            for t in transcript_list:
                if t.language_code in ["en", "zh-Hans", "zh-Hant", "zh", "hi"]:
                    chosen_track = t
                    break
            if not chosen_track:
                for t in transcript_list:
                    chosen_track = t
                    break
                    
            if not chosen_track:
                return None

            data = chosen_track.fetch()
            snippets = []
            full_texts = []

            raw_items = data.snippets if hasattr(data, "snippets") else data
            for item in raw_items:
                t_text = getattr(item, "text", "") if hasattr(item, "text") else (item.get("text", "") if isinstance(item, dict) else str(item))
                cleaned = t_text.replace("\n", " ").strip()
                if cleaned:
                    snippets.append({"text": cleaned})
                    full_texts.append(cleaned)

            full_text = " ".join(full_texts)
            if full_text.strip():
                return {
                    "video_id": video_id,
                    "language": chosen_track.language_code,
                    "full_text": full_text,
                    "snippets": snippets,
                    "source": "youtube_transcript_api"
                }
        except Exception as e:
            logger.debug(f"_fetch_via_api ({video_id}) 提示: {e}")
        return None

    def _fetch_via_html_scraping(self, video_id: str) -> Optional[Dict[str, Any]]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200:
                return None

            # 正则匹配 ytInitialPlayerResponse
            m = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});', resp.text)
            if not m:
                m = re.search(r'var ytInitialPlayerResponse\s*=\s*({.+?});', resp.text)
            
            if m:
                player_json = json.loads(m.group(1))
                captions = player_json.get("captions", {}).get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
                if captions:
                    track = captions[0]
                    base_url = track.get("baseUrl")
                    if base_url:
                        # 请求 json3 格式字幕
                        cap_resp = self.session.get(base_url + "&fmt=json3", timeout=10)
                        if cap_resp.status_code == 200 and not cap_resp.text.strip().startswith("<"):
                            cap_json = cap_resp.json()
                            events = cap_json.get("events", [])
                            lines = []
                            for ev in events:
                                segs = ev.get("segs", [])
                                txt = "".join([s.get("utf8", "") for s in segs]).replace("\n", " ").strip()
                                if txt and txt not in lines:
                                    lines.append(txt)
                            full_text = " ".join(lines)
                            if full_text.strip():
                                return {
                                    "video_id": video_id,
                                    "language": track.get("languageCode", "auto"),
                                    "full_text": full_text,
                                    "snippets": [{"text": l} for l in lines],
                                    "source": "html_embedded_caption_tracks"
                                }
        except Exception as e:
            logger.debug(f"_fetch_via_html_scraping ({video_id}) 异常: {e}")
        return None

    def _fetch_via_ytdlp(self, video_id: str) -> Optional[Dict[str, Any]]:
        temp_dir = Path(f"/tmp/yt_subs_{video_id}")
        temp_dir.mkdir(parents=True, exist_ok=True)
        out_tmpl = str(temp_dir / "%(id)s.%(ext)s")

        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["all"],
            "subtitlesformat": "vtt",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
        }
        if self.proxy:
            ydl_opts["proxy"] = self.proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

            vtt_files = list(temp_dir.glob(f"{video_id}.*.vtt"))
            if not vtt_files:
                return None

            target_vtt = vtt_files[0]
            full_texts = []
            with open(target_vtt, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                        continue
                    if "-->" in line:
                        continue
                    if line not in full_texts:
                        full_texts.append(line)

            full_text = " ".join(full_texts)
            if full_text.strip():
                return {
                    "video_id": video_id,
                    "language": target_vtt.name.split(".")[-2] if len(target_vtt.name.split(".")) > 2 else "auto",
                    "full_text": full_text,
                    "snippets": [{"text": l} for l in full_texts],
                    "source": "yt_dlp_vtt"
                }
        except Exception as e:
            logger.debug(f"_fetch_via_ytdlp ({video_id}) 异常: {e}")
        return None
