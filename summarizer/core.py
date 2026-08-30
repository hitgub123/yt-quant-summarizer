from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from summarizer.config import settings
from summarizer.ingestion import VideoIngester
from summarizer.transcriber import HybridTranscriber
from summarizer.analyzer import GeminiAnalyzer
from summarizer.storage import StorageManager
from summarizer.indexer import IndexBuilder
from summarizer.classifier import is_investment_related
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus

logger = logging.getLogger(__name__)


class QuantSummarizer:
    """
    Unified High-Level Quant Video Summarization Pipeline.
    Can be used from Python scripts or CLI.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        proxy: Optional[str] = None,
        output_dir: Optional[Path | str] = None,
        preferred_languages: Optional[List[str]] = None,
    ):
        self.proxy = settings.setup_proxies(proxy)
        self.output_dir = Path(output_dir) if output_dir else settings.OUTPUT_DIR
        self.model = model or settings.GEMINI_MODEL
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.preferred_languages = preferred_languages or settings.language_list

        self.storage = StorageManager(self.output_dir / ".cache" / "records.db")
        self.indexer = IndexBuilder(self.output_dir, self.storage)
        self.ingester = VideoIngester(proxy=self.proxy)

        self.analyzer: Optional[GeminiAnalyzer] = None
        if self.api_key:
            self.analyzer = GeminiAnalyzer(api_key=self.api_key, model=self.model)

        self.transcriber = HybridTranscriber(
            preferred_languages=self.preferred_languages,
            proxy=self.proxy,
            gemini_client=self.analyzer.client if self.analyzer else None,
        )

    def summarize_video(self, url_or_id: str, force: bool = False) -> Tuple[VideoRecord, Path]:
        """Summarize a single video by URL or Video ID."""
        if not self.analyzer:
            raise ValueError("GEMINI_API_KEY is required to generate summaries.")

        # 1. Fetch metadata
        metadata = self.ingester.get_video_metadata(url_or_id)

        # Check cache
        if not force and self.storage.is_processed(metadata.video_id):
            record = self.storage.get_record(metadata.video_id)
            if record and record.report_path and Path(record.report_path).exists():
                return record, Path(record.report_path)

        # 2. Extract transcript
        transcript = self.transcriber.get_transcript(metadata)

        # 3. Analyze with Gemini
        report_md = self.analyzer.analyze(metadata, transcript)

        # 4. Save Markdown report with Frontmatter
        report_file = self.indexer.save_report(metadata, report_md, model_name=self.model)

        # 5. Save record to SQLite
        record = VideoRecord(
            video_id=metadata.video_id,
            channel=metadata.channel,
            title=metadata.title,
            upload_date=metadata.upload_date,
            duration=metadata.duration_formatted,
            status=ProcessingStatus.COMPLETED,
            transcript_source=transcript.source,
            report_path=str(report_file),
        )
        self.storage.save_record(record)

        # 6. Update index
        self.indexer.update_channel_index(metadata.channel)
        self.indexer.update_global_index()

        return record, report_file

    def summarize_channel(
        self,
        channel_url: str,
        limit: Optional[int] = None,
        force: bool = False,
        filter_investment: bool = True,
        on_video_start=None,
        on_video_complete=None,
        on_video_error=None,
    ) -> Dict[str, Any]:
        """
        Batch summarize all investment-related videos from a channel.
        """
        if not self.analyzer:
            raise ValueError("GEMINI_API_KEY is required to generate summaries.")

        # 1. Fetch channel videos
        raw_videos = self.ingester.get_channel_videos(channel_url, limit=limit)
        if not raw_videos:
            return {
                "total_found": 0,
                "investment_videos": [],
                "filtered_out": [],
                "completed": [],
                "skipped": [],
                "failed": [],
            }

        # 2. Classify and filter investment videos
        investment_videos: List[VideoMetadata] = []
        filtered_out: List[Tuple[VideoMetadata, str]] = []

        for v in raw_videos:
            if filter_investment:
                is_rel, reason = is_investment_related(v.title, v.description, v.tags)
                if is_rel:
                    investment_videos.append(v)
                else:
                    filtered_out.append((v, reason))
            else:
                investment_videos.append(v)

        completed_records: List[VideoRecord] = []
        skipped_records: List[VideoRecord] = []
        failed_records: List[Tuple[VideoMetadata, str]] = []

        channel_name = raw_videos[0].channel

        for idx, vid in enumerate(investment_videos, 1):
            if on_video_start:
                on_video_start(vid, idx, len(investment_videos))

            # Check if already processed
            if not force and self.storage.is_processed(vid.video_id):
                record = self.storage.get_record(vid.video_id)
                if record:
                    skipped_records.append(record)
                    if on_video_complete:
                        on_video_complete(vid, record, is_cached=True)
                    continue

            try:
                # Fetch full single metadata if flat playlist lacked details
                try:
                    full_meta = self.ingester.get_video_metadata(vid.video_id)
                    vid = full_meta
                except Exception:
                    pass

                transcript = self.transcriber.get_transcript(vid)
                report_md = self.analyzer.analyze(vid, transcript)
                report_file = self.indexer.save_report(vid, report_md, model_name=self.model)

                record = VideoRecord(
                    video_id=vid.video_id,
                    channel=vid.channel,
                    title=vid.title,
                    upload_date=vid.upload_date,
                    duration=vid.duration_formatted,
                    status=ProcessingStatus.COMPLETED,
                    transcript_source=transcript.source,
                    report_path=str(report_file),
                )
                self.storage.save_record(record)
                completed_records.append(record)

                if on_video_complete:
                    on_video_complete(vid, record, is_cached=False)

            except Exception as e:
                error_msg = str(e)
                failed_record = VideoRecord(
                    video_id=vid.video_id,
                    channel=vid.channel,
                    title=vid.title,
                    upload_date=vid.upload_date,
                    duration=vid.duration_formatted,
                    status=ProcessingStatus.FAILED,
                    error_message=error_msg,
                )
                self.storage.save_record(failed_record)
                failed_records.append((vid, error_msg))

                if on_video_error:
                    on_video_error(vid, error_msg)

        # 3. Update indices
        self.indexer.update_channel_index(channel_name)
        self.indexer.update_global_index()

        return {
            "total_found": len(raw_videos),
            "investment_videos": investment_videos,
            "filtered_out": filtered_out,
            "completed": completed_records,
            "skipped": skipped_records,
            "failed": failed_records,
            "global_index": str(self.output_dir / "INDEX.md"),
        }

    def fetch_video(self, url_or_id: str) -> Tuple[VideoMetadata, TranscriptResult, Path]:
        """Fetch video metadata and transcript without requiring GEMINI_API_KEY. Saves task json."""
        from datetime import datetime
        import json
        from summarizer.utils import sanitize_filename
        from summarizer.models import VideoTask

        metadata = self.ingester.get_video_metadata(url_or_id)
        transcript = self.transcriber.get_transcript(metadata)

        task_dir = self.output_dir / ".transcripts" / sanitize_filename(metadata.channel)
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / f"{metadata.video_id}.json"

        task = VideoTask(
            metadata=metadata,
            transcript=transcript,
            fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        task_file.write_text(task.model_dump_json(indent=2), encoding="utf-8")
        return metadata, transcript, task_file

    def fetch_channel(
        self,
        channel_url: str,
        limit: Optional[int] = None,
        filter_investment: bool = True,
        force: bool = False,
        on_video_start=None,
        on_video_complete=None,
        on_video_error=None,
    ) -> Dict[str, Any]:
        """
        Batch fetch metadata and transcripts for all investment videos from a channel.
        Zero API Key required! Perfect for pairing with Antigravity / Gemini Pro account.
        """
        import json
        from datetime import datetime
        from summarizer.utils import sanitize_filename
        from summarizer.models import VideoTask

        raw_videos = self.ingester.get_channel_videos(channel_url, limit=limit)
        if not raw_videos:
            return {
                "total_found": 0,
                "investment_videos": [],
                "filtered_out": [],
                "fetched": [],
                "cached": [],
                "failed": [],
            }

        investment_videos: List[VideoMetadata] = []
        filtered_out: List[Tuple[VideoMetadata, str]] = []

        for v in raw_videos:
            if filter_investment:
                is_rel, reason = is_investment_related(v.title, v.description, v.tags)
                if is_rel:
                    investment_videos.append(v)
                else:
                    filtered_out.append((v, reason))
            else:
                investment_videos.append(v)

        fetched_tasks: List[Tuple[VideoMetadata, Path]] = []
        cached_tasks: List[VideoMetadata] = []
        failed_tasks: List[Tuple[VideoMetadata, str]] = []

        for idx, vid in enumerate(investment_videos, 1):
            if on_video_start:
                on_video_start(vid, idx, len(investment_videos))

            # Check if report already completed
            if not force and self.storage.is_processed(vid.video_id):
                cached_tasks.append(vid)
                if on_video_complete:
                    on_video_complete(vid, None, is_cached=True)
                continue

            try:
                # Refresh single metadata if needed
                try:
                    full_meta = self.ingester.get_video_metadata(vid.video_id)
                    vid = full_meta
                except Exception:
                    pass

                transcript = self.transcriber.get_transcript(vid)

                channel_dir_name = sanitize_filename(vid.channel)
                task_dir = self.output_dir / ".transcripts" / channel_dir_name
                task_dir.mkdir(parents=True, exist_ok=True)
                task_file = task_dir / f"{vid.video_id}.json"

                task = VideoTask(
                    metadata=vid,
                    transcript=transcript,
                    fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                task_file.write_text(task.model_dump_json(indent=2), encoding="utf-8")
                fetched_tasks.append((vid, task_file))

                if on_video_complete:
                    on_video_complete(vid, task_file, is_cached=False)

            except Exception as e:
                failed_tasks.append((vid, str(e)))
                if on_video_error:
                    on_video_error(vid, str(e))

        return {
            "total_found": len(raw_videos),
            "investment_videos": investment_videos,
            "filtered_out": filtered_out,
            "fetched": fetched_tasks,
            "cached": cached_tasks,
            "failed": failed_tasks,
        }

    def record_report(
        self,
        metadata: VideoMetadata,
        report_markdown: str,
        model_name: str = "antigravity",
        transcript_source: str = "youtube_subtitles",
        tags: Optional[List[str]] = None
    ) -> Tuple[VideoRecord, Path]:
        """Save an externally generated (e.g. Antigravity) report and update all indices."""
        report_file = self.indexer.save_report(metadata, report_markdown, model_name=model_name, tags=tags)

        record = VideoRecord(
            video_id=metadata.video_id,
            channel=metadata.channel,
            title=metadata.title,
            upload_date=metadata.upload_date,
            duration=metadata.duration_formatted,
            status=ProcessingStatus.COMPLETED,
            transcript_source=transcript_source,
            report_path=str(report_file),
        )
        self.storage.save_record(record)
        self.indexer.update_channel_index(metadata.channel)
        self.indexer.update_global_index()
        return record, report_file

    def get_pending_transcripts(self, channel: Optional[str] = None) -> List[Tuple[VideoMetadata, TranscriptResult, Path]]:
        """List all pre-fetched transcripts that haven't been summarized into completed reports yet."""
        import json
        from summarizer.utils import sanitize_filename
        from summarizer.models import VideoTask

        transcripts_dir = self.output_dir / ".transcripts"
        if not transcripts_dir.exists():
            return []

        pending = []
        pattern = f"{sanitize_filename(channel)}/*.json" if channel else "*/*.json"
        for task_file in transcripts_dir.glob(pattern):
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                task = VideoTask(**data)
                if not self.storage.is_processed(task.metadata.video_id):
                    pending.append((task.metadata, task.transcript, task_file))
            except Exception:
                continue

        return pending