from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import List, Optional
import yt_dlp

from summarizer.models import VideoMetadata, TranscriptResult, TranscriptSegment
from summarizer.utils import format_timestamp


class HybridTranscriber:
    def __init__(self, preferred_languages: Optional[List[str]] = None, proxy: Optional[str] = None, gemini_client=None):
        self.preferred_languages = preferred_languages or ["en", "zh-Hans", "zh-Hant", "zh", "ja"]
        self.proxy = proxy
        self.gemini_client = gemini_client

    def get_transcript(self, metadata: VideoMetadata) -> TranscriptResult:
        """
        Hybrid transcript extraction:
        1. Priority 1: YouTube Transcript API (Subtitles, fast & lightweight)
        2. Priority 2: yt-dlp Subtitle Extraction
        3. Priority 3: Fallback Audio extraction + Gemini Audio transcription
        """
        video_id = metadata.video_id

        # Strategy 1: YouTube Transcript API
        try:
            res = self._extract_via_transcript_api(video_id)
            if res and res.full_text.strip():
                return res
        except Exception:
            pass

        # Strategy 2: yt-dlp Subtitle download
        try:
            res = self._extract_via_ytdlp_subtitles(metadata.url)
            if res and res.full_text.strip():
                return res
        except Exception:
            pass

        # Strategy 3: Audio fallback + Gemini Audio understanding
        return self._extract_via_gemini_audio(metadata)

    def _extract_via_transcript_api(self, video_id: str) -> Optional[TranscriptResult]:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Support both new class instance API and legacy static method
        try:
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.list(video_id)
        except AttributeError:
            proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies)

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

        fetched_data = transcript.fetch()
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
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            subs = info.get("subtitles") or info.get("automatic_captions")
            if not subs:
                return None
        return None

    def _extract_via_gemini_audio(self, metadata: VideoMetadata) -> TranscriptResult:
        if not self.gemini_client:
            raise RuntimeError(
                "Gemini Client is required for audio transcription fallback when no subtitles exist. "
                "Please configure GEMINI_API_KEY."
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_template = os.path.join(tmpdir, f"{metadata.video_id}.%(ext)s")
            opts = {
                "format": "ba[ext=m4a]/ba/b",
                "outtmpl": out_template,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "64",
                }],
                "quiet": True,
                "no_warnings": True,
            }
            if self.proxy:
                opts["proxy"] = self.proxy

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([metadata.url])

            audio_files = list(Path(tmpdir).glob("*.mp3")) + list(Path(tmpdir).glob("*.m4a"))
            if not audio_files:
                raise RuntimeError(f"Failed to download audio for video {metadata.video_id}")

            audio_path = str(audio_files[0])
            
            uploaded_file = self.gemini_client.files.upload(file=audio_path)
            try:
                prompt = (
                    "Please transcribe the following audio verbatim into standard text with timestamps. "
                    "Format each paragraph as: [HH:MM:SS] Text content. "
                    "Ensure accurate transcription of quant trading terminology, technical indicators, and numbers."
                )
                response = self.gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[uploaded_file, prompt]
                )
                transcript_text = response.text or ""
                
                return TranscriptResult(
                    video_id=metadata.video_id,
                    source="gemini_audio",
                    language="auto",
                    full_text=transcript_text,
                    formatted_transcript=transcript_text,
                    segments=[]
                )
            finally:
                try:
                    self.gemini_client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass