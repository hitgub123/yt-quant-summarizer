from __future__ import annotations
import html
import json
import logging
import random
import re
import threading
import time
from pathlib import Path
from typing import List, Literal, Optional
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import yt_dlp

from summarizer.models import VideoMetadata, TranscriptResult, TranscriptSegment
from summarizer.utils import extract_video_id, format_timestamp

logger = logging.getLogger(__name__)


class SubtitleCircuitOpenError(RuntimeError):
    """Raised when subtitle requests are paused after repeated 429 responses."""


class SubtitleRateLimitError(RuntimeError):
    """Raised when YouTube returns 429 and the pipeline must stop immediately."""


class HybridTranscriber:
    def __init__(
        self,
        preferred_languages: Optional[List[str]] = None,
        proxy: Optional[str] = None,
        gemini_client=None,
        model: Optional[str] = None,
        min_request_interval: float = 2.0,
        max_retries: int = 0,
        backoff_seconds: float = 3.0,
        cooldown_seconds: float = 60.0,
        transcript_mode: Literal["auto", "subtitles", "gemini-video"] = "auto",
        cooldown_state_file: Optional[Path | str] = None,
    ):
        self.preferred_languages = preferred_languages or ["en", "zh-Hans", "zh-Hant", "zh", "ja"]
        self.proxy = proxy
        self.gemini_client = gemini_client
        self.model = model or "gemini-2.5-flash"
        self.min_request_interval = max(0.0, min_request_interval)
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        if transcript_mode not in {"auto", "subtitles", "gemini-video"}:
            raise ValueError("transcript_mode must be 'auto', 'subtitles', or 'gemini-video'.")
        self.transcript_mode = transcript_mode
        self.cooldown_state_file = Path(cooldown_state_file) if cooldown_state_file else None
        self._subtitle_request_lock = threading.Lock()
        self._last_subtitle_request_at = 0.0
        self._subtitle_blocked_until = 0.0
        self._load_cooldown_state()

    def get_transcript(self, metadata: VideoMetadata) -> TranscriptResult:
        """
        Hybrid transcript extraction:
        1. Priority 1: YouTube Transcript API (Subtitles, fast & lightweight)
        2. Priority 2: yt-dlp Subtitle Extraction
        3. Priority 3: Fallback Direct Gemini Video URL Multimodal Understanding (Zero local download)
        """
        video_id = metadata.video_id

        # Direct Gemini mode intentionally skips every subtitle endpoint.
        if self.transcript_mode == "gemini-video":
            return self._extract_via_gemini_video_url(metadata)

        # Strategy 1: YouTube Transcript API
        try:
            res = self._extract_via_transcript_api(video_id)
            if res and res.full_text.strip():
                return res
        except Exception as exc:
            if isinstance(exc, (SubtitleRateLimitError, SubtitleCircuitOpenError)):
                raise
            logger.debug("Transcript API extraction failed for %s: %s", video_id, exc)
            pass

        # Strategy 2: yt-dlp Subtitle download
        try:
            res = self._extract_via_ytdlp_subtitles(metadata.url)
            if res and res.full_text.strip():
                return res
        except Exception as exc:
            if isinstance(exc, (SubtitleRateLimitError, SubtitleCircuitOpenError)):
                raise
            logger.debug("yt-dlp subtitle extraction failed for %s: %s", video_id, exc)
            pass

        if self.transcript_mode == "subtitles":
            raise RuntimeError(
                f"No usable YouTube subtitles were found for {video_id}; "
                "subtitles-only mode will not call Gemini video fallback."
            )

        # Strategy 3: Zero-download direct Gemini Video URL understanding
        return self._extract_via_gemini_video_url(metadata)

    def _extract_via_transcript_api(self, video_id: str) -> Optional[TranscriptResult]:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
        except ImportError:
            GenericProxyConfig = None

        proxy_config = (
            GenericProxyConfig(http_url=self.proxy, https_url=self.proxy)
            if self.proxy and GenericProxyConfig
            else None
        )

        # Support both new class instance API and legacy static method. The new
        # API must receive proxy_config at construction time; otherwise a proxy
        # configured for yt-dlp would silently not apply to this request.
        try:
            ytt_api = YouTubeTranscriptApi(**({"proxy_config": proxy_config} if proxy_config else {}))
            transcript_list = self._with_subtitle_retries(
                lambda: ytt_api.list(video_id),
                f"transcript list for {video_id}",
            )
        except (AttributeError, TypeError):
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            transcript_list = self._with_subtitle_retries(
                lambda: YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies),
                f"legacy transcript list for {video_id}",
            )

        transcript = None
        selected_lang = "en"

        # 1. Try manual transcript in preferred languages
        for lang in self.preferred_languages:
            try:
                transcript = transcript_list.find_manually_created_transcript([lang])
                selected_lang = lang
                break
            except Exception:
                continue

        # 2. Try generated transcript in preferred languages
        if not transcript:
            for lang in self.preferred_languages:
                try:
                    transcript = transcript_list.find_generated_transcript([lang])
                    selected_lang = lang
                    break
                except Exception:
                    continue

        # 3. Fallback to any transcript available
        if not transcript:
            for t in transcript_list:
                transcript = t
                selected_lang = getattr(t, "language_code", "unknown")
                break

        if not transcript:
            return None

        fetched_data = self._with_subtitle_retries(
            transcript.fetch,
            f"transcript fetch for {video_id}",
        )
        segments: List[TranscriptSegment] = []
        formatted_lines: List[str] = []
        full_texts: List[str] = []

        for item in fetched_data:
            start = float(getattr(item, "start", 0.0) if hasattr(item, "start") else item.get("start", 0.0))
            duration = float(getattr(item, "duration", 0.0) if hasattr(item, "duration") else item.get("duration", 0.0))
            text = str(getattr(item, "text", "") if hasattr(item, "text") else item.get("text", "")).strip()

            if text:
                segments.append(TranscriptSegment(start=start, duration=duration, text=text))
                ts = format_timestamp(start)
                formatted_lines.append(f"{ts} {text}")
                full_texts.append(text)

        return TranscriptResult(
            video_id=video_id,
            source="youtube_subtitles",
            language=selected_lang,
            full_text=" ".join(full_texts),
            formatted_transcript="\n".join(formatted_lines),
            segments=segments
        )

    def _extract_via_ytdlp_subtitles(self, url: str) -> Optional[TranscriptResult]:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": self.preferred_languages,
            "quiet": True,
            "no_warnings": True,
        }
        if self.proxy:
            opts["proxy"] = self.proxy

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = self._with_subtitle_retries(
                lambda: ydl.extract_info(url, download=False),
                f"yt-dlp metadata for {url}",
            )
            if not info:
                return None
            manual = info.get("subtitles") or {}
            automatic = info.get("automatic_captions") or {}

        # Prefer manually authored captions, then generated captions. Within
        # a language prefer formats that retain timing information.
        for subtitle_groups, source in ((manual, "youtube_subtitles"), (automatic, "youtube_auto_subtitles")):
            selected = self._select_subtitle_track(subtitle_groups)
            if not selected:
                continue
            language, track = selected
            try:
                raw = self._with_subtitle_retries(
                    lambda: self._download_subtitle(
                        track["url"],
                        headers=track.get("http_headers"),
                    ),
                    f"subtitle download for {url}",
                )
                result = self._parse_subtitle(
                    raw,
                    track.get("ext"),
                    extract_video_id(url) or url,
                    language,
                    source,
                )
                if result and result.full_text.strip():
                    return result
            except Exception as exc:
                logger.debug("Could not parse subtitle track for %s: %s", url, exc)

        return None

    def _select_subtitle_track(self, subtitles: dict) -> Optional[tuple[str, dict]]:
        if not subtitles:
            return None

        languages = list(subtitles.keys())
        ordered_languages: List[str] = []
        for preferred in self.preferred_languages:
            preferred_lower = preferred.lower()
            ordered_languages.extend(
                lang for lang in languages
                if lang.lower() == preferred_lower or lang.lower().split("-")[0] == preferred_lower.split("-")[0]
            )
        ordered_languages.extend(lang for lang in languages if lang not in ordered_languages)

        extension_order = {"vtt": 0, "json3": 1, "srv3": 2, "ttml": 3, "xml": 4}
        for language in ordered_languages:
            tracks = subtitles.get(language) or []
            if isinstance(tracks, dict):
                tracks = [tracks]
            tracks = [track for track in tracks if track.get("url")]
            if tracks:
                track = sorted(tracks, key=lambda item: extension_order.get(item.get("ext", ""), 99))[0]
                return language, track
        return None

    def _download_subtitle(self, url: str, headers: Optional[dict] = None) -> str:
        request_headers = {"User-Agent": "yt-quant-summarizer/0.1"}
        if headers:
            request_headers.update(headers)
        request = Request(url, headers=request_headers)
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8-sig")

    def _with_subtitle_retries(self, operation, description: str):
        """Run one YouTube subtitle operation with pacing and 429 backoff."""
        for attempt in range(self.max_retries + 1):
            try:
                self._wait_for_subtitle_request()
                return operation()
            except SubtitleCircuitOpenError:
                raise
            except Exception as exc:
                rate_limited = self._is_rate_limit_error(exc)
                if rate_limited:
                    self._subtitle_blocked_until = time.monotonic() + self.cooldown_seconds
                    self._persist_cooldown_state()
                    logger.warning(
                        "Subtitle endpoint rate-limited; stopping immediately and cooling down for %.1fs: %s",
                        self.cooldown_seconds,
                        description,
                    )
                    raise SubtitleRateLimitError(
                        f"YouTube returned HTTP 429 for {description}; "
                        f"subtitle fetching stopped for {self.cooldown_seconds / 86400:.1f} day(s)."
                    ) from exc

                if not rate_limited or attempt >= self.max_retries:
                    raise

                delay = self.backoff_seconds * (2 ** attempt)
                delay += random.uniform(0.0, max(0.1, delay * 0.25))
                logger.warning(
                    "Subtitle request rate-limited; retrying %d/%d in %.1fs: %s",
                    attempt + 1,
                    self.max_retries,
                    delay,
                    description,
                )
                time.sleep(delay)

    def _wait_for_subtitle_request(self) -> None:
        with self._subtitle_request_lock:
            now = time.monotonic()
            if now < self._subtitle_blocked_until:
                remaining = self._subtitle_blocked_until - now
                raise SubtitleCircuitOpenError(
                    f"Subtitle requests temporarily paused after HTTP 429; retry in {remaining:.0f}s."
                )

            wait = self.min_request_interval - (now - self._last_subtitle_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_subtitle_request_at = time.monotonic()

    def _load_cooldown_state(self) -> None:
        if not self.cooldown_state_file or not self.cooldown_state_file.exists():
            return
        try:
            data = json.loads(self.cooldown_state_file.read_text(encoding="utf-8"))
            blocked_until_epoch = float(data.get("blocked_until_epoch", 0))
            remaining = blocked_until_epoch - time.time()
            if remaining > 0:
                self._subtitle_blocked_until = time.monotonic() + remaining
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.warning("Could not read subtitle cooldown state: %s", exc)

    def _persist_cooldown_state(self) -> None:
        if not self.cooldown_state_file:
            return
        try:
            self.cooldown_state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {"blocked_until_epoch": time.time() + self.cooldown_seconds}
            self.cooldown_state_file.write_text(json.dumps(data), encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not persist subtitle cooldown state: %s", exc)

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        return any(marker in text for marker in ("429", "too many requests", "ipblocked", "requestblocked"))

    def _parse_subtitle(
        self,
        raw: str,
        extension: Optional[str],
        video_id: str,
        language: str,
        source: str,
    ) -> Optional[TranscriptResult]:
        ext = (extension or "").lower()
        if ext == "json3" or raw.lstrip().startswith("{"):
            items = self._parse_json3(raw)
        elif ext in {"srv3", "ttml", "xml"} or raw.lstrip().startswith("<"):
            items = self._parse_xml(raw)
        else:
            items = self._parse_vtt(raw)

        if not items:
            return None
        segments = [TranscriptSegment(start=start, duration=duration, text=text) for start, duration, text in items]
        return TranscriptResult(
            video_id=video_id,
            source=source,
            language=language,
            full_text=" ".join(segment.text for segment in segments),
            formatted_transcript="\n".join(
                f"{format_timestamp(segment.start)} {segment.text}" for segment in segments
            ),
            segments=segments,
        )

    @staticmethod
    def _parse_vtt(raw: str) -> List[tuple[float, float, str]]:
        timestamp = re.compile(
            r"(?P<start>\d{2}:\d{2}:\d{2}(?:\.\d+)?|\d{2}:\d{2}(?:\.\d+)?)\s+-->\s+"
            r"(?P<end>\d{2}:\d{2}:\d{2}(?:\.\d+)?|\d{2}:\d{2}(?:\.\d+)?)"
        )

        def seconds(value: str) -> float:
            parts = [float(part) for part in value.split(":")]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return parts[0] * 3600 + parts[1] * 60 + parts[2]

        items: List[tuple[float, float, str]] = []
        current_start = current_end = None
        text_lines: List[str] = []

        def flush() -> None:
            nonlocal text_lines
            text = re.sub(r"<[^>]+>", "", html.unescape(" ".join(text_lines))).strip()
            if text and current_start is not None and (not items or items[-1][2] != text):
                items.append((current_start, max(0.0, (current_end or current_start) - current_start), text))
            text_lines = []

        for line in raw.splitlines():
            match = timestamp.search(line)
            if match:
                flush()
                current_start = seconds(match.group("start"))
                current_end = seconds(match.group("end"))
            elif not line.strip():
                flush()
                current_start = current_end = None
            elif current_start is not None and not line.strip().isdigit() and not line.startswith(("WEBVTT", "NOTE")):
                text_lines.append(line.strip())
        flush()
        return items

    @staticmethod
    def _parse_json3(raw: str) -> List[tuple[float, float, str]]:
        data = json.loads(raw)
        items = []
        for event in data.get("events", []):
            text = "".join(seg.get("utf8", "") for seg in event.get("segs", []))
            if text.strip():
                start = float(event.get("tStartMs", 0)) / 1000
                duration = float(event.get("dDurationMs", 0)) / 1000
                items.append((start, duration, html.unescape(text).strip()))
        return items

    @staticmethod
    def _parse_xml(raw: str) -> List[tuple[float, float, str]]:
        root = ElementTree.fromstring(raw)
        items = []
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1] != "text":
                continue
            text = "".join(element.itertext()).strip()
            if text:
                items.append((
                    float(element.attrib.get("start", 0)),
                    float(element.attrib.get("dur", 0)),
                    html.unescape(text),
                ))
        return items

    def _extract_via_gemini_video_url(self, metadata: VideoMetadata) -> TranscriptResult:
        """
        Fallback Strategy 3: Directly pass YouTube URL to Gemini as a multimodal Part.
        Zero local download, zero disk I/O, zero ffmpeg dependency.
        """
        if not self.gemini_client:
            raise RuntimeError(
                "Gemini Client is required for video transcript fallback when no subtitles exist. "
                "Please configure GEMINI_API_KEY."
            )

        from google.genai import types

        prompt = (
            "Please listen to and watch the following YouTube video, and extract/transcribe the spoken content "
            "verbatim into standard text with timestamps.\n"
            "Format each segment as: [HH:MM:SS] Text content.\n"
            "Ensure accurate transcription of quantitative trading concepts, math formulas, technical indicators, and code."
        )

        response = self.gemini_client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_uri(
                    file_uri=metadata.url,
                    mime_type="video/*"
                ),
                prompt
            ]
        )
        transcript_text = response.text or ""
        if not transcript_text.strip():
            raise RuntimeError("Gemini returned an empty transcript.")

        return TranscriptResult(
            video_id=metadata.video_id,
            source="gemini_video_url",
            language="auto",
            full_text=transcript_text,
            formatted_transcript=transcript_text,
            segments=[]
        )
