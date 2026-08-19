from __future__ import annotations
import os
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract 11-character YouTube video ID from various URL formats."""
    text = url_or_id.strip()
    if len(text) == 11 and re.match(r"^[a-zA-Z0-9_-]{11}$", text):
        return text

    patterns = [
        r"(?:v=|/v/|/embed/|/shorts/|/live/)([0-9A-Za-z_-]{11})",
        r"youtu\.be/([0-9A-Za-z_-]{11})",
        r"youtube\.com/watch\?.*v=([0-9A-Za-z_-]{11})",
        r"m\.youtube\.com/watch\?.*v=([0-9A-Za-z_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
            
    try:
        parsed = urlparse(text)
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"] and len(qs["v"][0]) == 11:
            return qs["v"][0]
    except Exception:
        pass

    return None


def is_channel_url(url: str) -> bool:
    """Check if URL points to a YouTube channel, handle, user, or playlist."""
    text = url.strip().lower()
    return any(marker in text for marker in [
        "/@", "/channel/", "/c/", "/user/", "/playlists", "/videos", "/featured", "list="
    ])


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """Sanitize string to be safe for filenames across OSes."""
    clean = re.sub(r'[\x00-\x1f\\/*?:"<>|#&]', "", name)
    clean = re.sub(r"[\s_]+", "_", clean).strip(" ._")
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(" ._")
    return clean or "untitled"


def format_seconds(seconds: int | float) -> str:
    """Format duration in seconds into HH:MM:SS or MM:SS."""
    sec = int(seconds or 0)
    hours = sec // 3600
    minutes = (sec % 3600) // 60
    rem_sec = sec % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{rem_sec:02d}"
    return f"{minutes:02d}:{rem_sec:02d}"


def format_timestamp(seconds: float) -> str:
    """Format timestamp seconds into [HH:MM:SS]."""
    sec = int(seconds or 0)
    hours = sec // 3600
    minutes = (sec % 3600) // 60
    rem_sec = sec % 60
    return f"[{hours:02d}:{minutes:02d}:{rem_sec:02d}]"