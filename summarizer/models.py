from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float
    duration: float
    text: str


class TranscriptResult(BaseModel):
    video_id: str
    source: str  # 'youtube_subtitles', 'gemini_audio', 'whisper'
    language: str = "en"
    full_text: str
    formatted_transcript: str
    segments: List[TranscriptSegment] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    video_id: str
    title: str
    channel: str
    channel_id: Optional[str] = None
    channel_url: Optional[str] = None
    upload_date: Optional[str] = None  # YYYY-MM-DD
    duration_seconds: int = 0
    duration_formatted: str = "00:00"
    url: str
    view_count: Optional[int] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None


class ProcessingStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"


class VideoRecord(BaseModel):
    video_id: str
    channel: str
    title: str
    upload_date: Optional[str] = None
    duration: str = "00:00"
    status: ProcessingStatus = ProcessingStatus.PENDING
    transcript_source: Optional[str] = None
    report_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VideoTask(BaseModel):
    metadata: VideoMetadata
    transcript: TranscriptResult
    fetched_at: str

