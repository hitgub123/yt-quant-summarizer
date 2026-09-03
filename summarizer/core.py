from __future__ import annotations
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Literal, Tuple

from summarizer.config import settings
from summarizer.ingestion import VideoIngester
from summarizer.transcriber import HybridTranscriber
from summarizer.analyzer import GeminiAnalyzer
from summarizer.storage import StorageManager
from summarizer.indexer import IndexBuilder
from summarizer.classifier import is_investment_related
from summarizer.models import VideoMetadata, VideoRecord, ProcessingStatus, TranscriptResult

logger = logging.getLogger(__name__)
_UNSET = object()


class QuantSummarizer:
    """
    Unified High-Level Quant Video Summarization Pipeline.
    Can be used from Python scripts or CLI.
    """

    def __init__(
        self,
        api_key: Optional[str] | object = _UNSET,
        model: Optional[str] = None,
        proxy: Optional[str] = None,
        output_dir: Optional[Path | str] = None,
        preferred_languages: Optional[List[str]] = None,
        report_mode: Literal["summary", "research"] = "summary",
        transcript_mode: Literal["auto", "subtitles", "gemini-video"] = "auto",
    ):
        self.proxy = settings.setup_proxies(proxy)
        self.output_dir = (Path(output_dir) if output_dir else settings.OUTPUT_DIR).expanduser().resolve()
        self.model = model or settings.GEMINI_MODEL
        if report_mode not in {"summary", "research"}:
            raise ValueError("report_mode must be 'summary' or 'research'.")
        self.report_mode = report_mode
        if transcript_mode not in {"auto", "subtitles", "gemini-video"}:
            raise ValueError("transcript_mode must be 'auto', 'subtitles', or 'gemini-video'.")
        self.transcript_mode = transcript_mode
        # Omitted means "use settings"; explicit None disables Gemini.
        self.api_key = settings.GEMINI_API_KEY if api_key is _UNSET else api_key
        self.preferred_languages = preferred_languages or settings.language_list

        self.storage = StorageManager(self.output_dir / ".cache" / "records.db")
        self.indexer = IndexBuilder(self.output_dir, self.storage)
        self.ingester = VideoIngester(proxy=self.proxy)

        self.analyzer: Optional[GeminiAnalyzer] = None
        if self.api_key:
            self.analyzer = GeminiAnalyzer(
                api_key=self.api_key,
                model=self.model,
                report_mode=self.report_mode,
            )

        self.transcriber = HybridTranscriber(
            preferred_languages=self.preferred_languages,
            proxy=self.proxy,
            gemini_client=self.analyzer.client if self.analyzer else None,
            model=self.model,
            min_request_interval=settings.SUBTITLE_MIN_REQUEST_INTERVAL,
            max_retries=settings.SUBTITLE_MAX_RETRIES,
            backoff_seconds=settings.SUBTITLE_BACKOFF_SECONDS,
            cooldown_seconds=settings.SUBTITLE_COOLDOWN_SECONDS,
            transcript_mode=self.transcript_mode,
            cooldown_state_file=self.output_dir / ".cache" / "subtitle_cooldown.json",
        )

    @staticmethod
    def _notify(callback, *args, **kwargs) -> None:
        """Callbacks are observers and must not change processing outcomes."""
        if not callback:
            return
        try:
            callback(*args, **kwargs)
        except Exception:
            logger.exception("Pipeline callback failed")

    def _is_cached(self, video_id: str, force: bool) -> bool:
        return not force and self.storage.is_report_available(video_id)

    def _find_transcript_task(self, video_id: str) -> Optional[Path]:
        """Return a valid saved transcript task for a video, if one exists."""
        import json

        transcripts_dir = self.output_dir / ".transcripts"
        if not transcripts_dir.exists():
            return None
        for task_file in transcripts_dir.glob(f"*/{video_id}.json"):
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                if (
                    data.get("metadata", {}).get("video_id") == video_id
                    and data.get("transcript", {}).get("full_text", "").strip()
                ):
                    return task_file
            except (OSError, ValueError, AttributeError):
                continue
        return None

    def is_transcript_available(self, video_id: str) -> bool:
        """Whether a completed transcript checkpoint exists for a video."""
        return self._find_transcript_task(video_id) is not None

    def _refresh_metadata(self, metadata: VideoMetadata) -> VideoMetadata:
        try:
            return self.ingester.get_video_metadata(metadata.video_id)
        except Exception as exc:
            logger.warning("Could not refresh metadata for %s: %s", metadata.video_id, exc)
            return metadata

    def _completed_record(
        self,
        metadata: VideoMetadata,
        transcript: TranscriptResult,
        report_file: Path,
    ) -> VideoRecord:
        return VideoRecord(
            video_id=metadata.video_id,
            channel=metadata.channel,
            title=metadata.title,
            upload_date=metadata.upload_date,
            duration=metadata.duration_formatted,
            status=ProcessingStatus.COMPLETED,
            transcript_source=transcript.source,
            report_path=str(report_file.resolve()),
        )

    def _failed_record(self, metadata: VideoMetadata, error_message: str) -> VideoRecord:
        return VideoRecord(
            video_id=metadata.video_id,
            channel=metadata.channel,
            title=metadata.title,
            upload_date=metadata.upload_date,
            duration=metadata.duration_formatted,
            status=ProcessingStatus.FAILED,
            error_message=error_message,
        )

    def summarize_video(self, url_or_id: str, force: bool = False) -> Tuple[VideoRecord, Path]:
        """Summarize a single video by URL or Video ID."""
        if not self.analyzer:
            raise ValueError("GEMINI_API_KEY is required to generate summaries.")

        # 1. Fetch metadata
        metadata = self.ingester.get_video_metadata(url_or_id)

        # Check cache
        if self._is_cached(metadata.video_id, force):
            record = self.storage.get_record(metadata.video_id)
            if record and record.report_path:
                report_path = self.storage.resolve_report_path(record.report_path)
                if report_path:
                    return record, report_path

        # 2. Extract transcript
        transcript = self.transcriber.get_transcript(metadata)

        # 3. Analyze with Gemini
        report_md = self.analyzer.analyze(metadata, transcript)

        # 4. Save Markdown report with Frontmatter
        report_file = self.indexer.save_report(metadata, report_md, model_name=self.model)

        # 5. Save record to SQLite
        record = self._completed_record(metadata, transcript, report_file)
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

        for idx, vid in enumerate(investment_videos, 1):
            self._notify(on_video_start, vid, idx, len(investment_videos))

            # Check if already processed
            if self._is_cached(vid.video_id, force):
                record = self.storage.get_record(vid.video_id)
                if record:
                    skipped_records.append(record)
                    self._notify(on_video_complete, vid, record, is_cached=True)
                    continue

            try:
                # Fetch full single metadata if flat playlist lacked details
                vid = self._refresh_metadata(vid)
                investment_videos[idx - 1] = vid

                transcript = self.transcriber.get_transcript(vid)
                report_md = self.analyzer.analyze(vid, transcript)
                report_file = self.indexer.save_report(vid, report_md, model_name=self.model)

                record = self._completed_record(vid, transcript, report_file)
                self.storage.save_record(record)
                completed_records.append(record)

                self._notify(on_video_complete, vid, record, is_cached=False)

            except Exception as e:
                error_msg = str(e)
                # Preserve an existing valid report if a forced regeneration
                # fails; a transient API failure must not destroy good data.
                if not self.storage.is_report_available(vid.video_id):
                    self.storage.save_record(self._failed_record(vid, error_msg))
                failed_records.append((vid, error_msg))

                self._notify(on_video_error, vid, error_msg)

        # 3. Update indices
        channels = {v.channel for v in investment_videos}
        for channel in channels:
            self.indexer.update_channel_index(channel)
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

    def fetch_video(self, url_or_id: str, force: bool = False) -> Tuple[VideoMetadata, TranscriptResult, Path]:
        """Fetch video metadata and transcript without requiring GEMINI_API_KEY. Saves task json."""
        from datetime import datetime
        import json
        from summarizer.utils import extract_video_id, sanitize_filename
        from summarizer.models import VideoTask

        # Reuse a valid checkpoint before touching YouTube again. This also
        # makes a previously completed single-video fetch resumable.
        video_id = extract_video_id(url_or_id)
        if video_id and not force:
            task_file = self._find_transcript_task(video_id)
            if task_file:
                task = VideoTask(**json.loads(task_file.read_text(encoding="utf-8")))
                return task.metadata, task.transcript, task_file

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
        stop_on_error: bool = False,
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
            self._notify(on_video_start, vid, idx, len(investment_videos))

            # A transcript task is the checkpoint for this fetch workflow.
            if not force and self.is_transcript_available(vid.video_id):
                cached_tasks.append(vid)
                self._notify(on_video_complete, vid, None, is_cached=True)
                continue

            try:
                # Refresh single metadata if needed
                vid = self._refresh_metadata(vid)
                investment_videos[idx - 1] = vid

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

                self._notify(on_video_complete, vid, task_file, is_cached=False)

            except Exception as e:
                failed_tasks.append((vid, str(e)))
                self._notify(on_video_error, vid, str(e))
                if stop_on_error:
                    logger.warning("Stopping subtitle fetch after failure for %s", vid.video_id)
                    break

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
            report_path=str(report_file.resolve()),
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
                if not self.storage.is_report_available(task.metadata.video_id):
                    pending.append((task.metadata, task.transcript, task_file))
            except Exception as exc:
                logger.warning("Skipping invalid transcript task %s: %s", task_file, exc)
                continue

        return pending
