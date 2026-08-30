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