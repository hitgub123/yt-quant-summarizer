from unittest.mock import MagicMock, patch
from pathlib import Path
from summarizer.core import QuantSummarizer
from summarizer.models import VideoMetadata, TranscriptResult


def test_quant_summarizer_pipeline(tmp_path: Path):
    summarizer = QuantSummarizer(api_key="mock_key", output_dir=tmp_path / "out")
    
    # Mock analyzer and transcriber
    summarizer.analyzer = MagicMock()
    summarizer.analyzer.analyze.return_value = "# Mock Report\n\n## 1. 核心论点\n测试研报"
    
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_video_metadata.return_value = VideoMetadata(
        video_id="mock1234567",
        title="Python Algo Strategy",
        channel="QuantMaster",
        upload_date="2024-05-01",
        duration_seconds=300,
        duration_formatted="05:00",
        url="https://www.youtube.com/watch?v=mock1234567"
    )
    
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id="mock1234567",
        source="mock_sub",
        language="en",
        full_text="This is a test transcript about trading.",
        formatted_transcript="[00:00:00] This is a test transcript about trading."
    )
    
    record, report_file = summarizer.summarize_video("mock1234567")
    
    assert report_file.exists()
    assert record.video_id == "mock1234567"
    assert record.status.value == "completed"
    assert "QuantMaster" in str(report_file)

    # Check cache
    assert summarizer.storage.is_processed("mock1234567")


def test_fetch_video_and_record_report(tmp_path: Path):
    # QuantSummarizer without api_key
    summarizer = QuantSummarizer(api_key=None, output_dir=tmp_path / "out")
    assert summarizer.analyzer is None

    summarizer.ingester = MagicMock()
    summarizer.ingester.get_video_metadata.return_value = VideoMetadata(
        video_id="fetch_test_123",
        title="Mean Reversion Strategy",
        channel="AlgoTradingIn",
        upload_date="2024-06-01",
        duration_seconds=450,
        duration_formatted="07:30",
        url="https://www.youtube.com/watch?v=fetch_test_123"
    )

    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id="fetch_test_123",
        source="youtube_subtitles",
        language="en",
        full_text="Bollinger Bands mean reversion tutorial.",
        formatted_transcript="[00:00:01] Bollinger Bands mean reversion tutorial."
    )

    # 1. Fetch video (No API key needed)
    meta, transcript, task_file = summarizer.fetch_video("fetch_test_123")
    assert task_file.exists()
    assert meta.video_id == "fetch_test_123"

    # 2. Check pending
    pending = summarizer.get_pending_transcripts()
    assert len(pending) == 1
    assert pending[0][0].video_id == "fetch_test_123"

    # 3. Record externally generated report (e.g. from Antigravity)
    mock_md = "# Mean Reversion Strategy\n\n## 1. 核心论点\n布林带均值回归研报"
    record, report_path = summarizer.record_report(meta, mock_md, model_name="antigravity")

    assert report_path.exists()
    assert record.status.value == "completed"
    assert summarizer.storage.is_processed("fetch_test_123")
    assert (tmp_path / "out" / "INDEX.md").exists()
    assert (tmp_path / "out" / "AlgoTradingIn" / "INDEX.md").exists()


def test_fetch_video_reuses_transcript_checkpoint(tmp_path: Path):
    summarizer = QuantSummarizer(api_key=None, output_dir=tmp_path / "out")
    metadata = VideoMetadata(
        video_id="checkpoint1",
        title="Checkpoint video",
        channel="Channel",
        url="https://www.youtube.com/watch?v=checkpoint1",
    )
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_video_metadata.return_value = metadata
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id="checkpoint1",
        source="youtube_subtitles",
        full_text="saved transcript",
        formatted_transcript="saved transcript",
    )

    first = summarizer.fetch_video(metadata.video_id)
    second = summarizer.fetch_video(metadata.video_id)

    assert first[2] == second[2]
    assert summarizer.ingester.get_video_metadata.call_count == 1
    assert summarizer.transcriber.get_transcript.call_count == 1


def test_channel_refreshes_metadata_and_callback_cannot_fail_item(tmp_path: Path):
    summarizer = QuantSummarizer(api_key="mock_key", output_dir=tmp_path / "out")
    summarizer.analyzer = MagicMock()
    summarizer.analyzer.analyze.return_value = "# Report"

    flat = VideoMetadata(
        video_id="channel12345",
        title="Flat title",
        channel="Flat channel",
        url="https://www.youtube.com/watch?v=channel12345",
    )
    refreshed = flat.model_copy(update={"title": "Full title", "channel": "Full channel"})
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_channel_videos.return_value = [flat]
    summarizer.ingester.get_video_metadata.return_value = refreshed
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id=flat.video_id,
        source="youtube_subtitles",
        full_text="trading transcript",
        formatted_transcript="[00:00:00] trading transcript",
    )

    def broken_callback(*args, **kwargs):
        raise RuntimeError("display failure")

    result = summarizer.summarize_channel(
        "https://www.youtube.com/@channel",
        filter_investment=False,
        on_video_complete=broken_callback,
    )

    assert len(result["completed"]) == 1
    assert result["investment_videos"][0].title == "Full title"
    assert result["investment_videos"][0].channel == "Full channel"
    assert (tmp_path / "out" / "Full_channel" / "INDEX.md").exists()


def test_forced_channel_failure_preserves_existing_report(tmp_path: Path):
    summarizer = QuantSummarizer(api_key="mock_key", output_dir=tmp_path / "out")
    summarizer.analyzer = MagicMock()
    summarizer.analyzer.analyze.return_value = "# First report"
    metadata = VideoMetadata(
        video_id="preserve1234",
        title="Preserve report",
        channel="Quant channel",
        url="https://www.youtube.com/watch?v=preserve1234",
    )
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_channel_videos.return_value = [metadata]
    summarizer.ingester.get_video_metadata.return_value = metadata
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.return_value = TranscriptResult(
        video_id=metadata.video_id,
        source="youtube_subtitles",
        full_text="trading transcript",
        formatted_transcript="[00:00:00] trading transcript",
    )
    summarizer.summarize_channel("channel", filter_investment=False)
    original = summarizer.storage.get_record(metadata.video_id)

    summarizer.analyzer.analyze.side_effect = RuntimeError("temporary API failure")
    result = summarizer.summarize_channel("channel", filter_investment=False, force=True)
    current = summarizer.storage.get_record(metadata.video_id)

    assert len(result["failed"]) == 1
    assert current is not None
    assert current.status.value == "completed"
    assert current.report_path == original.report_path


def test_fetch_channel_stops_and_checkpoints_for_resume(tmp_path: Path):
    summarizer = QuantSummarizer(api_key=None, output_dir=tmp_path / "out")
    videos = [
        VideoMetadata(video_id="resume_one", title="One", channel="Channel", url="https://youtu.be/resume_one"),
        VideoMetadata(video_id="resume_two", title="Two", channel="Channel", url="https://youtu.be/resume_two"),
        VideoMetadata(video_id="resume_three", title="Three", channel="Channel", url="https://youtu.be/resume_three"),
    ]
    summarizer.ingester = MagicMock()
    summarizer.ingester.get_channel_videos.return_value = videos
    summarizer.ingester.get_video_metadata.side_effect = lambda video_id: next(
        video for video in videos if video.video_id == video_id
    )
    summarizer.transcriber = MagicMock()
    summarizer.transcriber.get_transcript.side_effect = [
        TranscriptResult(video_id="resume_one", source="youtube_subtitles", full_text="one", formatted_transcript="one"),
        RuntimeError("HTTP 429"),
        TranscriptResult(video_id="resume_three", source="youtube_subtitles", full_text="three", formatted_transcript="three"),
    ]

    result = summarizer.fetch_channel(
        "https://www.youtube.com/@channel",
        filter_investment=False,
        stop_on_error=True,
    )

    assert len(result["fetched"]) == 1
    assert len(result["failed"]) == 1
    assert summarizer.is_transcript_available("resume_one")
    assert not summarizer.is_transcript_available("resume_three")
    assert summarizer.transcriber.get_transcript.call_count == 2

    summarizer.transcriber.get_transcript.side_effect = [
        TranscriptResult(video_id="resume_two", source="youtube_subtitles", full_text="two", formatted_transcript="two"),
        TranscriptResult(video_id="resume_three", source="youtube_subtitles", full_text="three", formatted_transcript="three"),
    ]
    resumed = summarizer.fetch_channel(
        "https://www.youtube.com/@channel",
        filter_investment=False,
        stop_on_error=True,
    )

    assert len(resumed["cached"]) == 1
    assert len(resumed["fetched"]) == 2
    assert summarizer.transcriber.get_transcript.call_count == 4
