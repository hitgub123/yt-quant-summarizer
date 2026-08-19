from __future__ import annotations
import os
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import yt_dlp

from summarizer.models import VideoMetadata
from summarizer.utils import extract_video_id, format_seconds, sanitize_filename


class VideoIngester:
    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy

    def _get_ydl_opts(self, extra_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        if extra_opts:
            opts.update(extra_opts)
        return opts

    def normalize_channel_url(self, raw_url: str) -> str:
        """Standardize channel URL to fetch videos tab properly."""
        url = raw_url.strip().rstrip("/")
        # Replace m.youtube.com with www.youtube.com for yt-dlp consistency
        url = url.replace("m.youtube.com", "www.youtube.com")

        # If it's a handle like https://www.youtube.com/@AlgorithmTradingIn or /featured
        if "/@" in url:
            if url.endswith("/featured"):
                url = url[:-9] + "/videos"
            elif not any(url.endswith(sub) for sub in ["/videos", "/shorts", "/streams", "/playlists"]):
                url = f"{url}/videos"
        elif "/channel/" in url or "/c/" in url or "/user/" in url:
            if not any(url.endswith(sub) for sub in ["/videos", "/shorts", "/streams", "/playlists"]):
                url = f"{url}/videos"

        return url

    def get_video_metadata(self, url_or_id: str) -> VideoMetadata:
        """Extract rich metadata for a single YouTube video."""
        video_id = extract_video_id(url_or_id)
        target_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else url_or_id

        opts = self._get_ydl_opts({"extract_flat": False})
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(target_url, download=False)
            if not info:
                raise ValueError(f"Could not fetch metadata for video: {url_or_id}")

            vid_id = info.get("id") or (video_id or "unknown")
            title = info.get("title") or "Unknown Title"
            channel = info.get("uploader") or info.get("channel") or "Unknown Channel"
            channel_id = info.get("channel_id") or info.get("uploader_id")
            channel_url = info.get("channel_url") or info.get("uploader_url")
            
            raw_date = info.get("upload_date")  # YYYYMMDD
            upload_date = None
            if raw_date and len(raw_date) == 8:
                upload_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

            duration_seconds = int(info.get("duration") or 0)
            duration_formatted = format_seconds(duration_seconds)
            
            view_count = info.get("view_count")
            description = info.get("description")
            tags = info.get("tags") or []
            thumbnail_url = info.get("thumbnail")

            return VideoMetadata(
                video_id=vid_id,
                title=title,
                channel=channel,
                channel_id=channel_id,
                channel_url=channel_url,
                upload_date=upload_date,
                duration_seconds=duration_seconds,
                duration_formatted=duration_formatted,
                url=f"https://www.youtube.com/watch?v={vid_id}",
                view_count=view_count,
                description=description,
                tags=tags,
                thumbnail_url=thumbnail_url
            )

    def get_channel_videos(self, channel_url: str, limit: Optional[int] = None) -> List[VideoMetadata]:
        """Fetch list of videos from a channel or playlist."""
        fetch_url = self.normalize_channel_url(channel_url)

        opts = self._get_ydl_opts({
            "extract_flat": "in_playlist",
            "playlistend": limit if (limit and limit > 0) else None
        })

        videos: List[VideoMetadata] = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(fetch_url, download=False)
            if not info:
                raise ValueError(f"Could not fetch channel info for: {channel_url}")

            entries = info.get("entries") or []
            channel_name = info.get("uploader") or info.get("channel") or info.get("title") or "Unknown Channel"
            
            for entry in entries:
                if not entry:
                    continue
                vid_id = entry.get("id")
                if not vid_id:
                    continue
                
                vid_title = entry.get("title") or "Untitled Video"
                entry_channel = entry.get("uploader") or entry.get("channel") or channel_name
                raw_date = entry.get("upload_date")
                upload_date = None
                if raw_date and len(raw_date) == 8:
                    upload_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
                
                duration_seconds = int(entry.get("duration") or 0)
                duration_formatted = format_seconds(duration_seconds)

                videos.append(VideoMetadata(
                    video_id=vid_id,
                    title=vid_title,
                    channel=entry_channel,
                    upload_date=upload_date,
                    duration_seconds=duration_seconds,
                    duration_formatted=duration_formatted,
                    url=f"https://www.youtube.com/watch?v={vid_id}",
                    view_count=entry.get("view_count"),
                    description=entry.get("description"),
                    tags=entry.get("tags") or []
                ))

                if limit and limit > 0 and len(videos) >= limit:
                    break

        return videos